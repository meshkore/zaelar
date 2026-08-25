"""nucleo/worker_api.py — plano REQUEST/RESPONSE de los Brain Workers (V2-038, §v2·B + §v3·I/J/K).

Un worker (subproceso, cualquier backend) habla con el server vivo por HTTP para PEDIR cosas que solo el host/
FlashBrain puede hacer o que espera respuesta:
  · `ask_user`  — preguntar al operador y ESPERAR ("¿enduro o cross?").
  · `use_tool`  — usar una TOOL del FlashBrain (web_search hoy; catálogo FILTRADO §v3·J) → el brain la ejecuta y
                  devuelve el resultado (el operador pidió: "el brain ejecuta búsquedas y se las devuelve al worker").
  · `read_widget`/`show_widget`/`close_widget` — leer/mostrar/cerrar un widget del canvas.
  · `push_channel` — empujar a un canal externo (CONFIRM + scan_outbound).
  · `spawn` — encadenar otro Brain Worker (dentro de cuota/profundidad).

UN solo endpoint (`ask` = `act action=ask_user`), política ALLOW/CONFIRM/DENY evaluada AQUÍ (server, no en el
prompt del worker), CONFIRM = un `ask_user` auto-generado (§v3·K), re-poll idempotente (§v3·I), y **piggyback**: toda
respuesta arrastra las inyecciones pendientes del FlashBrain para ese task (§v3·H). Auth por token por-tarea (§v2·D).
"""
from __future__ import annotations

import asyncio
import secrets
import time

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter()


# ── política por acción (§v3·J) ────────────────────────────────────────────────────────────────────────────
# ALLOW/CONFIRM/DENY vocab, the prestable/deny tool sets, _KNOWN_ACTS, deny_reason(), classify_act() and
# _confirm_question() moved to nucleo/worker_policy.py (2026-08-17 modularization pass) — pure decision
# logic, no I/O. Re-exported here so every existing call site (worker_api.classify_act(...), direct
# `from nucleo.worker_api import deny_reason` in tests, etc.) keeps working unchanged.
from nucleo.worker_policy import (  # noqa: F401 — re-export
    ALLOW, CONFIRM, DENY, _PRESTABLE_TOOLS, _DENY_TOOLS, _KNOWN_ACTS, deny_reason, classify_act,
    _confirm_question,
)
_MAX_DEPTH = 2



# ── registro de peticiones en vuelo (corr_id → estado) ──────────────────────────────────────────────────────
_ACTS: dict[str, dict] = {}

from nucleo.runtime_ids import next_seq as _next_seq


def _new_corr(task_id: str, action: str) -> str:
    """corr_id IMPREDECIBLE: el re-poll (`GET /act/{corr_id}`) no lleva token — el corr ES la capability. Uno
    secuencial sería adivinable (leer la respuesta del operador + robar el piggyback de inyecciones, §v2·D)."""
    return f"{task_id}:{action}:{_next_seq('worker_api.corr')}:{secrets.token_urlsafe(8)}"


def _piggyback(task_id: str) -> list[str]:
    """Inyecciones pendientes del FlashBrain para este worker (§v3·H) — se sirven en CUALQUIER respuesta de bridge."""
    try:
        from nucleo import dispatch
        return dispatch.take_pending_injects(task_id)
    except Exception:
        return []


def _verify(task_id: str, token: str):
    """Devuelve el SessionRecord si el token casa; None si no (auth por-tarea, §v2·D)."""
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(task_id)
        if rec is None:
            return None
        if dispatch.rec_token(rec) != (token or ""):
            return None
        return rec
    except Exception:
        return None


# ── ejecución inmediata de acciones ALLOW ────────────────────────────────────────────────────────────────
#: Cuántos avisos puede programar UNA tarea de fondo. Es el filtro de la capacidad, no un número decorativo: sin
#: tope, un worker en bucle le llena la agenda al operador y cada entrada dispara luego un turno.
_SCHEDULE_CAP = 3

#: Las formas que el parser acepta DE VERDAD, en una frase. Escrito aquí una vez porque va en los tres errores, y
#: porque una lista de ejemplos que no parsean es peor que ninguna: manda al worker a reintentar lo mismo.
_CUANDO_VALE = ('Vale «mañana a las 9», «el miércoles a las 18:00», un día del mes («el 3 a las 10»), '
                '«every 30m» para algo que se repite, o un cron de 5 campos «0 9 * * 3».')


async def _exec_allow(action: str, payload: dict, rec) -> dict:
    payload = payload or {}
    if action == "use_tool" and payload.get("tool") == "web_search":
        q = (payload.get("args") or {}).get("query") or payload.get("query") or ""
        try:
            from nucleo import websearch
            res = await asyncio.to_thread(websearch.search, str(q))
            # V2-236: y lo que la búsqueda trae va A LA CONVERSACIÓN en el momento, no cuando el worker entregue
            # — que en 5 de cada 8 sesiones medidas no llegó a pasar. Mismo remedio que V2-223 dio a lo que
            # extrae el navegador, por la otra puerta: ésta es NUESTRA búsqueda, prestada al worker.
            try:
                from nucleo.workers import findings
                findings.hand_web_finding(getattr(rec, "task_id", ""), findings.render_search(res),
                                          getattr(rec, "goal", ""))
                # V2-320 — …y a la HOJA, que es donde el operador mira. Un worker que resuelve buscando (sin
                # navegador) dejaba la hoja vacía SIEMPRE: el return solo tenía camino a la nota. Misma puerta
                # que el navegador (V2-257) y las mismas filas que lleva la nota.
                findings.hand_search_rows(rec, res)
            except Exception:  # noqa: BLE001
                pass
            return {"ok": True, "result": res}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"web_search falló: {e}"}
    if action == "schedule":
        # V2-249 — el aviso PROGRAMADO existe de verdad, o no se dice. Un worker al que se le encargaba
        # «recuérdaselo el miércoles» no podía hacerlo (la capacidad no existía) y escribía en memoria, de forma
        # durable, que lo había programado. El arnés puso el listón: **que la entrada exista, o que la píldora no
        # diga «programado»**. Esto hace lo primero.
        when = str(payload.get("when") or payload.get("schedule") or "").strip()
        what = str(payload.get("prompt") or payload.get("text") or payload.get("what") or "").strip()
        tid = str(getattr(rec, "task_id", "") or "")
        if not what:
            return {"ok": False, "error": "falta `prompt`: qué tiene que decir o hacer zaelar cuando llegue el "
                                          "momento, escrito como se lo dirías a él."}
        if not when:
            return {"ok": False, "error": "falta `when`: cuándo. " + _CUANDO_VALE}
        try:
            from nucleo import scheduler
            # DOS parsers, y en este orden: `parse_schedule` entiende las formas de máquina («every 30m», un cron
            # de 5 campos, `YYYY-MM-DD HH:MM`) y `parse_when` traduce las habladas («mañana a las 9», «el
            # miércoles a las 18:00»). El worker escribe como habla, así que sin el segundo casi todo lo suyo se
            # rechazaría; y sin el primero se perdería la recurrencia.
            spec = when if scheduler.parse_schedule(when) else (scheduler.parse_when(when) or "")
            if not spec:
                # `parse_when` devuelve "" ADREDE ante lo ambiguo («esta tarde», «pronto»): un aviso puesto sobre
                # una fecha adivinada es peor que ninguno, porque el operador se queda creyendo que está puesto.
                return {"ok": False, "error": f"«{when}» no me dice un momento exacto y no lo adivino: un aviso "
                                              f"sobre una fecha inventada es peor que ninguno. " + _CUANDO_VALE}
            # EL TOPE, que es el filtro de esta capacidad (mismo patrón que la cuota de `spawn`): un worker en
            # bucle no puede llenarle la agenda al operador. Se cuenta sobre las tareas VIVAS y por atribución,
            # así que no hace falta estado nuevo ni sobrevive a un reinicio como una cifra rancia.
            mias = [j for j in scheduler.list_jobs() if f"[worker:{tid}]" in str(j.get("name") or "")]
            if len(mias) >= _SCHEDULE_CAP:
                return {"ok": False, "error": f"ya has programado {len(mias)} avisos en esta tarea, que es el "
                                              f"tope. Si necesitas otro, cancela uno o dilo en tu entrega."}
            name = f"{(payload.get('name') or what)[:80]} [worker:{tid}]"
            out = await asyncio.to_thread(scheduler.create, what, spec, name)
            if not out.get("ok"):
                # La forma la sabe él; que la diga (mismo contrato que V2-203).
                return {"ok": False, "error": f"{out.get('error') or 'no se pudo programar'}. " + _CUANDO_VALE}
            # V2-249 — Y QUE SE VEA. Un aviso que va a sonar dentro de tres días lo puso una tarea de fondo que
            # para entonces ya no existe: sin fila, el operador se lo encuentra sin saber de dónde salió. La fila
            # lleva el ID REAL, que es lo que permite comprobar una píldora contra el scheduler — memoria-dev
            # señaló que hoy nada verifica una afirmación del sistema sobre sus propios efectos, y esto es la
            # mitad que puede aportar quien ejecuta la acción: dejar la prueba.
            try:
                from voice.observer import emit
                emit("task", "⏰ aviso programado",
                     text=f"{out.get('display') or when} — {what[:120]}",
                     extra={"id": tid, "src": f"worker:{tid}", "cron_id": out.get("id"),
                            "when": out.get("display") or when})
            except Exception:  # noqa: BLE001
                pass
            return {"ok": True, "result": {"id": out.get("id"), "cuando": out.get("display") or when,
                                           "que": what,
                                           "ref": f"cron:{out.get('id')}"}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"no pude programarlo: {e}"}
    if action == "read_widget":
        wid = str(payload.get("id") or payload.get("widget_id") or "")
        try:
            from widgets import runtime
            from widgets.server_api import MISSING, run_widget_hook
            man = runtime.get(wid)
            if not man:
                return {"ok": False, "error": f"el widget «{wid}» no existe"}

            def _call(view_data):
                try:
                    return view_data(q="")
                except TypeError:            # widgets antiguos sin argumento de query
                    return view_data()

            # los DATOS del widget (§7.3: view_data), off-loop y con timeout — no solo el manifest.
            data = await run_widget_hook(wid, "view_data", _call)
            return {"ok": True, "result": {"manifest": man,
                                           "data": None if data is MISSING else data}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"read_widget falló: {e}"}
    if action in ("show_widget", "close_widget"):
        wid = payload.get("id") or payload.get("widget_id") or ""
        try:
            from voice.observer import emit
            _src = f"worker:{getattr(rec, 'task_id', '')}"        # V2-039: procedencia — orden de un Brain Worker
            extra = {"id": str(wid), "src": _src} if action == "show_widget" else {"src": _src}
            _tid = getattr(rec, "trace_id", "")                   # V2-044: handler HTTP sin contexto → trace de la sesión
            if _tid:
                extra["trace"] = _tid
                extra["span"] = f"worker:{getattr(rec, 'task_id', '')}"
            emit("widget", "show" if action == "show_widget" else "close", extra=extra)
            return {"ok": True, "result": {"widget": wid}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
    if action == "widget_data":
        # V2-061 puente worker→widget: aplica la data-op por el MISMO camino que el tag [[widget.data]] del
        # FlashBrain (widgets.brain_action → apply_action del widget, off-loop, aislado, nunca revienta). La
        # PROCEDENCIA se sella como worker:<id> (V2-039) para que el evento widget/data no se atribuya a "user".
        wid = str(payload.get("widget_id") or payload.get("id") or "").strip().lower()
        act = str(payload.get("action") or "").strip()
        data_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        if not wid or not act:
            return {"ok": False, "error": "widget_data requiere widget_id y action"}
        # V2-259 — A QUÉ HOJA. El prompt del worker le dice «entrega en la hoja `results`» (V2-257) y con
        # instancias ese nombre pelado deja de ser una dirección: escribiría en la caja que no mira nadie
        # mientras el operador tiene delante la de SU encargo. Lo resuelve el PUENTE y no el worker, a propósito:
        # un worker no debería conocer ids de instancia, y pedírselos sería una forma nueva de equivocarse. Se
        # respeta un `sheet` explícito por si algún día hace falta, pero nadie se lo enseña.
        if wid == "results" and not str(data_payload.get("sheet") or "").strip():
            try:
                from nucleo.dispatch import sheet_of as _sheet_of_rec
                _own = _sheet_of_rec(rec)
            except Exception:  # noqa: BLE001
                _own = ""
            if _own:
                data_payload = {**data_payload, "sheet": _own}
        try:
            from widgets import runtime
            if runtime.get(wid) is None:
                return {"ok": False, "error": f"el widget «{wid}» no existe"}
            try:
                from widgets import provenance as _prov
                _prov.note(wid, f"worker:{getattr(rec, 'task_id', '')}")
            except Exception:
                pass
            from widgets.server_api import brain_action
            res = await brain_action(wid, act, data_payload)
            if isinstance(res, dict) and res.get("error"):
                return {"ok": False, "error": str(res.get("error"))}
            return {"ok": True, "result": {"widget": wid, "action": act, "data": res}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"widget_data falló: {e}"}
    if action == "spawn":
        return await _spawn_child(payload, rec)
    return {"ok": False, "error": "acción ALLOW no ejecutable"}


async def _spawn_child(payload: dict, rec) -> dict:
    """Encadena otro Brain Worker dentro de cuota/profundidad (§v3·J: DENY al exceder)."""
    depth = int(getattr(rec, "depth", 0) or 0)
    if depth + 1 > _MAX_DEPTH:
        return {"ok": False, "error": "límite de profundidad de cadena alcanzado"}
    req = (payload or {}).get("request") or ""
    if not req:
        return {"ok": False, "error": "spawn sin request"}
    try:
        from nucleo.flash import escalate
        cid = escalate.escalate_to_slowbrain(str(req), context={
            "src": "worker", "kind": (payload.get("kind") or "generic"),
            "parent_task_id": rec.task_id, "depth": depth + 1})
        return {"ok": True, "result": {"child_id": cid}}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"spawn falló: {e}"}


def purge_task(task_id: str) -> int:
    """§v3·L: al morir/matarse una sesión se purgan sus peticiones PENDIENTES — el loop no debe relatar la pregunta
    de un muerto. Las respondidas se conservan (un `hbask wait` tardío del grupo aún vivo recibe error limpio 404).
    La llama dispatch (cancel_session / fin de sesión)."""
    n = 0
    for corr, e in list(_ACTS.items()):
        if e.get("task_id") == str(task_id) and e.get("state") == "pending":
            _ACTS.pop(corr, None)
            n += 1
    return n


_ANSWERED_TTL_S = 600.0


def _prune() -> None:
    """Poda entradas RESPONDIDAS viejas (el worker ya reclamó o murió) — el registro nunca crece sin límite."""
    cut = time.time() - _ANSWERED_TTL_S
    for corr, e in list(_ACTS.items()):
        if e.get("state") == "answered" and float(e.get("created") or 0) < cut:
            _ACTS.pop(corr, None)


def _register_ask(rec, question: str, action: str = "ask_user", retained: dict | None = None) -> str:
    """Aparca una pregunta pendiente (ask_user o el CONFIRM de un act, §v3·K) → waiting_on=user + bus worker.ask."""
    _prune()
    corr = _new_corr(rec.task_id, action)
    _ACTS[corr] = {"corr_id": corr, "task_id": rec.task_id, "action": action, "question": question,
                   "state": "pending", "answer": "", "result": None, "retained": retained or {},
                   "created": time.time()}
    rec.waiting_on = "user"
    rec.ask = question
    rec.ask_corr = corr
    try:
        import bus
        bus.emit_sync("worker.ask", {"id": rec.task_id, "question": question, "corr_id": corr})
    except Exception:
        pass
    return corr


# ── endpoints ────────────────────────────────────────────────────────────────────────────────────────────
@router.post("/api/worker/act")
async def worker_act(task_id: str = Body(..., embed=True), token: str = Body("", embed=True),
                     action: str = Body(..., embed=True), payload: dict = Body(default={}, embed=True)):
    """El worker pide una acción. Verifica token → política → ejecuta (ALLOW inmediato), aparca (ask/CONFIRM) o
    deniega. Siempre arrastra piggyback de inyecciones."""
    rec = _verify(task_id, token)
    inj = _piggyback(task_id)
    if rec is None:
        return JSONResponse({"ok": False, "error": "task/token no válido", "injections": inj}, status_code=403)

    pol = classify_act(action, payload)
    if pol == DENY:
        return JSONResponse({"ok": False, "denied": True,
                             "error": deny_reason(action, payload), "injections": inj})

    if action == "ask_user":
        q = (payload or {}).get("question") or (payload or {}).get("text") or ""
        corr = _register_ask(rec, str(q))
        return JSONResponse({"ok": True, "status": "pending", "corr_id": corr, "injections": inj})

    if pol == CONFIRM:
        # §v3·K: un act irreversible se convierte en un ask_user auto-generado con la acción RETENIDA.
        q = _confirm_question(action, payload)
        corr = _register_ask(rec, q, action=action, retained={"action": action, "payload": payload})
        return JSONResponse({"ok": True, "status": "pending", "corr_id": corr, "injections": inj})

    # ALLOW inmediato
    res = await _exec_allow(action, payload or {}, rec)
    res["injections"] = inj
    return JSONResponse(res)


@router.post("/api/worker/say")
async def worker_say(task_id: str = Body(..., embed=True), token: str = Body("", embed=True),
                     text: str = Body("", embed=True)):
    """El worker DICE algo al usuario (say EXPLÍCITO, §v2·E·Q3) — se relata por voz+UI con atribución. Piggyback."""
    rec = _verify(task_id, token)
    inj = _piggyback(task_id)
    if rec is None:
        return JSONResponse({"ok": False, "error": "task/token no válido", "injections": inj}, status_code=403)
    msg = (text or "").strip()
    if msg:
        try:
            import bus
            bus.emit_sync("worker.say", {"id": task_id, "text": msg[:400]})
        except Exception:
            pass
        try:
            from voice import proactive
            await proactive.notify("zaelar", msg, speak=True)
        except Exception:
            pass
    return JSONResponse({"ok": True, "injections": inj})


@router.get("/api/worker/act/{corr_id}")
async def worker_act_poll(corr_id: str):
    """Re-poll idempotente (§v3·I): estado de una petición aparcada. La respuesta se guarda hasta reclamarse."""
    e = _ACTS.get(corr_id)
    tid = (e or {}).get("task_id", "")
    inj = _piggyback(tid) if tid else []
    if not e:
        return JSONResponse({"ok": False, "error": "corr_id desconocido", "injections": inj}, status_code=404)
    if e["state"] == "answered":
        return JSONResponse({"ok": True, "status": "answered", "answer": e.get("answer", ""),
                             "result": e.get("result"), "injections": inj})
    return JSONResponse({"ok": True, "status": "pending", "injections": inj})




# ── resolución de un ask (la llama el FlashBrain/provider cuando el operador responde) ───────────────────────
def has_pending_ask() -> bool:
    return any(e["state"] == "pending" for e in _ACTS.values())


def pending_asks() -> list[dict]:
    """Preguntas pendientes (para el loop supervisor: relatarlas por voz, una a una, FIFO)."""
    out = [e for e in _ACTS.values() if e["state"] == "pending"]
    out.sort(key=lambda e: e["created"])
    return [{"corr_id": e["corr_id"], "task_id": e["task_id"], "question": e["question"],
             "action": e["action"]} for e in out]


def active_ask() -> dict | None:
    """El ask pendiente MÁS ANTIGUO (el 'activo' que se relata, §v3·M/Q5)."""
    p = pending_asks()
    return p[0] if p else None


async def answer(corr_id: str, text: str) -> bool:
    """Resuelve un ask por corr_id: guarda la respuesta y, si era un CONFIRM de act, EJECUTA la acción retenida
    (§v3·K). Limpia waiting_on del record. Devuelve True si resolvió algo."""
    e = _ACTS.get(corr_id)
    if not e or e["state"] != "pending":
        return False
    e["answer"] = text or ""
    e["state"] = "answered"
    # CONFIRM retenido: "sí" → ejecuta la acción; cualquier otra cosa → no.
    retained = e.get("retained") or {}
    if retained.get("action") and _is_yes(text):
        try:
            from nucleo import dispatch
            rec = dispatch.get_record(e["task_id"])
            if rec is not None:
                e["result"] = await _exec_allow(retained["action"], retained.get("payload") or {}, rec)
        except Exception:
            pass
    _clear_waiting(e["task_id"], corr_id)
    return True


async def answer_active(text: str) -> bool:
    """Resuelve el ask ACTIVO (más antiguo) — camino determinista cuando el operador responde por voz (§v3·M)."""
    a = active_ask()
    if not a:
        return False
    return await answer(a["corr_id"], text)


def answer_active_soon(text: str) -> bool:
    """Fire-and-forget marshalado al loop del server (§v3·D/O): resuelve el ask activo. Lo llama el FlashBrain desde
    el job-thread. Devuelve True si HABÍA un ask que responder (para que la voz confirme)."""
    if not has_pending_ask():
        return False
    try:
        import asyncio

        from nucleo import dispatch
        loop = getattr(dispatch, "_LOOP", None)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(answer_active(text), loop)
        else:
            asyncio.ensure_future(answer_active(text))
        return True
    except Exception:
        return False


def match_by_options(text: str) -> str | None:
    """§v3·M/Q5: si la respuesta corta casa claramente con las `options` de ALGÚN ask pendiente, devuelve su
    corr_id (para enrutar a ese, no al activo). Placeholder conservador: sin options declaradas, None."""
    return None


def _clear_waiting(task_id: str, corr_id: str) -> None:
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(task_id)
        if rec is not None and getattr(rec, "ask_corr", "") == corr_id:
            rec.waiting_on = ""
            rec.ask = ""
            rec.ask_corr = ""
    except Exception:
        pass


def _is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(w in t for w in ("sí", "si", "vale", "adelante", "hazlo", "ok", "yes", "dale", "confirmo"))
