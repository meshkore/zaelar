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
ALLOW, CONFIRM, DENY = "allow", "confirm", "deny"
# Tools del FlashBrain PRESTABLES a los workers (catálogo FILTRADO, no todo router.TOOLS — anti prompt-injection
# desde contenido web hostil, §v3·B/J). Crece con marca explícita, nunca por accidente.
_PRESTABLE_TOOLS = {"web_search"}
# Nunca prestables (operator-only por semántica).
_DENY_TOOLS = {"authenticate_web", "login_done", "confirm_widget_delete", "set_style_directive", "delete_widget"}
_MAX_DEPTH = 2


def classify_act(action: str, payload: dict) -> str:
    a = (action or "").strip()
    if a == "ask_user":
        return ALLOW
    if a == "use_tool":
        tool = (payload or {}).get("tool", "")
        if tool in _DENY_TOOLS:
            return DENY
        return ALLOW if tool in _PRESTABLE_TOOLS else DENY
    if a in ("read_widget", "show_widget", "close_widget"):
        return ALLOW
    if a == "widget_data":
        # V2-061: DATA-OP sobre un widget (reflejar en el ESPEJO local lo hecho en la realidad — p.ej. borrar de la
        # agenda una cita ya cancelada en la web). El gate es el CATÁLOGO CANÓNICO (widgets/actions.py vía
        # frontend.action_mode), MISMO que el FlashBrain: FAST→ALLOW, CONFIRM(irreversible)→CONFIRM. ESCALATE/None
        # (acción no declarada) → DENY: un worker no escala una data-op ni inventa acciones — que LEA el widget antes.
        try:
            from nucleo.flash.frontend import action_mode
            from widgets import actions as _wa
            m = action_mode(str((payload or {}).get("widget_id") or (payload or {}).get("id") or ""),
                            str((payload or {}).get("action") or ""))
        except Exception:
            m = None
        if m == _wa.FAST:
            return ALLOW
        if m == _wa.CONFIRM:
            return CONFIRM
        return DENY
    if a == "spawn":
        return ALLOW           # la cuota/profundidad se comprueba aparte
    if a == "push_channel":
        return CONFIRM
    return DENY                # desconocido → denegar (fail-safe)


# ── registro de peticiones en vuelo (corr_id → estado) ──────────────────────────────────────────────────────
_ACTS: dict[str, dict] = {}
_seq = 0


def _new_corr(task_id: str, action: str) -> str:
    """corr_id IMPREDECIBLE: el re-poll (`GET /act/{corr_id}`) no lleva token — el corr ES la capability. Uno
    secuencial sería adivinable (leer la respuesta del operador + robar el piggyback de inyecciones, §v2·D)."""
    global _seq
    _seq += 1
    return f"{task_id}:{action}:{_seq}:{secrets.token_urlsafe(8)}"


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
async def _exec_allow(action: str, payload: dict, rec) -> dict:
    payload = payload or {}
    if action == "use_tool" and payload.get("tool") == "web_search":
        q = (payload.get("args") or {}).get("query") or payload.get("query") or ""
        try:
            from nucleo import websearch
            res = await asyncio.to_thread(websearch.search, str(q))
            return {"ok": True, "result": res}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"web_search falló: {e}"}
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
                             "error": "acción no permitida para un worker", "injections": inj})

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


def _confirm_question(action: str, payload: dict) -> str:
    if action == "push_channel":
        ch = (payload or {}).get("channel", "")
        return f"El worker quiere enviar algo al canal «{ch}». ¿Lo hago?"
    if action == "widget_data":
        wid = (payload or {}).get("widget_id") or (payload or {}).get("id") or ""
        act = (payload or {}).get("action") or ""
        return f"El worker quiere hacer «{act}» en el widget «{wid}» (acción irreversible). ¿Lo autorizas?"
    return f"El worker quiere ejecutar «{action}». ¿Lo autorizas?"


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
