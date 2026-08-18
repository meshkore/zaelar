"""nucleo/flash/probe.py — CANAL DE PRUEBA HEADLESS del FlashBrain (V2-032, 3ª forma de testing).

El PROBLEMA que resuelve: para arreglar la conversación del FlashBrain hacía falta una forma SÚPER RÁPIDA de
inyectarle texto y leer su respuesta SIN la voz, la interfaz ni una sala LiveKit — para poder iterar desde Claude
Code con ejemplos reales y evaluarlos al instante. Los otros dos canales (tests de memoria; tester de voz e2e
INI-013) son más lentos y con ruido de STT.

Este canal corre DENTRO del proceso vivo del server (que ya tiene memoria/bus/estado/widgets inicializados por el
lifespan), así que la fidelidad es máxima: reproduce el NÚCLEO del turno del FlashBrain — el MISMO prompt
(`build_flash_system` con estado+memoria+recall), el MISMO modelo (`FastClient`), las MISMAS tools (`router.TOOLS`)
y las MISMAS defensas de diálogo (`dialog.py`) que el turno de voz (`nucleo.py::_run`) — pero sin transporte de
audio ni ejecución real de widgets: en vez de ACTUAR, REPORTA qué haría (tool/tag elegido) + el texto + latencias.
Con eso se evalúan los fallos del informe (bucles, degeneración, pérdida de hilo, qué estado/memoria vio el modelo).

Uso (con el server arrancado, memoria reseteada con `make reset`):
    curl -s localhost:43917/api/flash/say -H 'content-type: application/json' -d '{"text":"hola, ¿cómo te llamas?"}'
    python -m nucleo.flash.probe "hola"          # one-shot
    python -m nucleo.flash.probe                 # REPL interactivo
    python -m nucleo.flash.probe --reset          # limpia la ventana de conversación del probe
    make flash T="me llamo Alex"                  # atajo one-shot
    make flash-repl                               # atajo REPL

NO toca la sesión de voz (usa su propia ventana `_SESSIONS`). Por defecto INGIERE a memoria como el turno real
(`ingest=true`) para que las pruebas de estado/memoria sean fidedignas; pásalo a false para charla aislada.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

_WINDOW_MAX = 10


@dataclass
class ProbeSession:
    """Estado conversacional de UNA sesión de prueba (aislado de la voz)."""
    window: list[dict] = field(default_factory=list)
    directive: str = ""
    seeded: bool = False   # ¿ventana sembrada desde memoria? (circuito de corto plazo, espejo de nucleo.py::_run)
    last_action: str = ""  # surface/action produced by the preceding turn (for deictic continuity)


_SESSIONS: dict[str, ProbeSession] = {}


def _session(sid: str) -> ProbeSession:
    return _SESSIONS.setdefault(sid or "default", ProbeSession())


def _ctx_ids() -> tuple[list, list]:
    """(open_ids, recent_ids) del ESTADO para acotar `runtime.identify` (V2-078) — ESPEJO de `providers/nucleo.py::
    _identify`. Ante un empate el que está en pantalla / se usó hace poco gana. Best-effort (estado ausente → ([],[]))."""
    try:
        from memory import api as _memapi
        _st = _memapi.state() or {}
        return (_st.get("open_widgets") or []), (_st.get("recent_widgets") or [])
    except Exception:
        return [], []


def _identify_ctx(rt, query: str) -> str | None:
    """`rt.identify(query, open_ids, recent_ids)['match']` con el contexto del estado — el resolvedor con la misma
    acotación open>reciente>catálogo que usa la voz. `rt` = módulo widgets.runtime ya importado por el llamante."""
    _o, _r = _ctx_ids()
    return (rt.identify(query, open_ids=_o, recent_ids=_r) or {}).get("match")


def _show_target(text: str, context: list[dict] | None = None, last_action: str = "") -> str | None:
    """Mismo criterio que `providers/nucleo.py::_show_guard_target` (impl PARALELA — mantener en sync): verbo de
    MOSTRAR + NO crear + `runtime.identify` resuelve un widget existente → el turno real lo convierte en show."""
    import re
    import unicodedata
    n = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()
    if re.search(r"\b(no|sin|tampoco|nunca|ni)\b[^.?!]{0,18}\b(abr|muestr|ensen|pon|saca|sube|ver)", n):
        return None
    if re.search(r"\b(crea|crear|cree|haz|hacer|genera|generar|nuev|construy|dise|monta|make|create|build|new)", n):
        return None
    if not re.search(r"\b(abr|muestr|ensen|pon|saca|sube)|quiero ver|ver mi|ense", n):
        return None
    try:
        from widgets import runtime
        # A deictic show request ("muéstramelo") gets its noun from the recent dialogue. Resolve the most recent
        # topical utterance against the same real widget catalogue instead of forcing the model to repeat a noun.
        # This is generic: weather, agenda, messages, music… are all resolved by runtime.identify, not a keyword map.
        from . import router as _router
        tail = (text or "").strip().lower().strip("¿?¡!.,;:")
        deictic = (bool(re.search(r"\b(?:muestr|ensen|abre|saca)\w*(?:lo|la|los|las)\b", n))
                    or any(_router.looks_like_bare_ref(token) for token in tail.split() if token))
        if deictic:
            for message in reversed(context or []):
                if message.get("role") != "user":
                    continue
                prior = str(message.get("content") or "").strip()
                if prior:
                    match = _identify_ctx(runtime, prior)
                    if match:
                        return match
                    break  # the grammatical antecedent is the immediately preceding user topic, never older history
            # The preceding route is stronger than fuzzy words: a LIGHT search is rendered in the built-in
            # `search` (Búsqueda / Tiempo) surface. This is action→surface continuity, not a topic keyword table.
            if last_action == "search" and runtime.get("search") is not None:
                return "search"
        return _identify_ctx(runtime, text)
    except Exception:
        return None


async def run_turn(text: str, *, sid: str = "default", ingest: bool = True, model: str = "",
                   execute: bool = False) -> dict:
    """Corre UN turno del FlashBrain headless y devuelve un dict evaluable. Reproduce el núcleo de
    `nucleo.py::_run` (prompt real + modelo real + tools reales + defensas de diálogo) sin voz ni ejecución.
    `model` (opcional) fuerza otro modelo rápido para el turno (A/B de modelos, mismo proveedor/base/key).
    `execute` (V2-049, canal de PRUEBA e2e de tareas web): ADEMÁS de reportar, EJECUTA de verdad las acciones de
    worker (escalada→Brain Worker real que conduce el navegador; inyección/respuesta/stop a un worker vivo) — así
    se puede conducir por TEXTO todo el ciclo de una gestión (reservar una cita) sin voz ni ruido de STT."""
    from voice import speech
    from voice.tag_protocol import strip_tags

    from . import dialog
    from . import router as _router
    from .fast_client import FastClient, spec_from_config
    from .prompt import build_flash_system, compose_recent_block, needs_recall, needs_recent

    sess = _session(sid)
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "texto vacío"}

    # COMANDO DE CONFIG DE SEGURIDAD (V2-060 F2, espejo del provider — impl PARALELA): «no me digas los secretos
    # por voz» / «modo máxima seguridad» = user rule DURA aplicada DETERMINISTA (sin modelo). Short-circuit.
    try:
        from . import vault_rules as _vr
        _cfg = _vr.detect(text)
    except Exception:
        _cfg = None
    if _cfg is not None:
        _line = _vr.apply(_cfg) if ingest else "(config no aplicada: ingest=false)"
        return {"ok": True, "reply": [_line], "action": "vault_config", "tool_calls": [], "tags": [],
                "security": {_cfg[0]: _cfg[1]}}

    # GUARDAR UN SECRETO (V2-060, fix 2026-07-21, espejo del provider — impl PARALELA): el operador DICE un secreto
    # → se intercepta DETERMINISTA (el valor no pasa por el modelo). Se cifra si hay bóveda; si no, se pide crearla.
    try:
        from memory import secrets as _secrets0
        _sec_found = _secrets0.detect(text)
    except Exception:
        _sec_found = []
    if _sec_found:
        from memory import vault as _vault0
        _has_vault = False
        try:
            _has_vault = _vault0.exists()
        except Exception:
            pass
        if _has_vault and ingest:
            for _d in _sec_found:
                try:
                    await asyncio.to_thread(_vault0.store_secret, _d.label, _d.value,
                                            slot=_d.slot, sensitivity=_d.sensitivity)
                except Exception:
                    pass
        return {"ok": True, "reply": ["(secreto cifrado)" if _has_vault else "(hace falta crear la bóveda)"],
                "action": "vault_save" if _has_vault else "vault_need_create", "tool_calls": [], "tags": [],
                "secret": {"n": len(_sec_found), "labels": [d.label for d in _sec_found], "vault": _has_vault}}

    # TRAZABILIDAD (V2-044, espejo de nucleo.py::_run): el turno del probe también nace con trace id — el canal
    # de PRUEBA valida la cadena texto→acción→eventos igual que la voz. El id vuelve en la respuesta (evaluable).
    _trace_id = ""
    try:
        from voice import trace as _trace
        _trace_id = _trace.begin(text, origin="probe")
    except Exception:
        pass

    # CIRCUITO DE CORTO PLAZO (B, espejo de nucleo.py::_run): siembra la ventana desde el buffer conversacional
    # persistente la primera vez — así el probe reproduce FIEL el arranque tras reconectar (ventana sembrada), no
    # una sesión artificialmente vacía. Best-effort.
    if not sess.seeded:
        sess.seeded = True
        if not sess.window:
            try:
                from memory import api as _memory
                _seed = _memory.recent_window(limit=int(os.getenv("ZAELAR_WINDOW_SEED", "6")))
                if _seed:
                    sess.window[:0] = _seed
            except Exception:
                pass

    t0 = time.time()
    timings: dict = {}

    # (a) INGESTA a memoria como el turno real (el CORAZÓN clasifica en background) — así el probe reproduce la
    # polución/actualización de estado que denuncia el informe. Desactivable para charla aislada.
    # ESPEJO del provider (nucleo.py:205, impl PARALELA): fire-and-forget vía create_task, NUNCA await directo —
    # ingest_utterance llama al CORAZÓN (LLM síncrono, cientos de ms a varios s según el proveedor) y un await aquí
    # bloqueaba el turno ENTERO del probe hasta que esa clasificación terminaba (bug real 2026-07-22: el canal
    # pensado para iterar RÁPIDO se volvía el más LENTO de los tres, con ingest=True por defecto).
    if ingest:
        try:
            from nucleo import memory_agent as _mem
            asyncio.create_task(_mem.ingest_utterance(text, role="operator"))
        except Exception:
            pass

    # V2-1xx: la petición REAL, ANTES de anteponer notas del sistema — ESPEJO del mismo fix en el provider de
    # voz (nucleo.py). El recall busca por esto, nunca por el turno con la nota pegada delante.
    operator_text = text

    # (a2) DRENA brain_notes como el provider (paridad voz/probe, V2-053): las notas [SISTEMA] pendientes
    # (SlowBrain, proactive, Susurro repair_say) se anteponen al turno — sin esto el canal de prueba no podía
    # verificar el circuito nota→respuesta y las notas se quedaban esperando a un turno de VOZ.
    try:
        from voice import brain_notes as _bn
        from voice.observer import emit as _emit_note
        _notes = _bn.drain()
        if _notes:
            for _n in _notes:
                _emit_note("brain", "📩 system note → FlashBrain (probe)", text=_n, role="system")
            text = "\n".join(_notes) + "\n\n" + text
    except Exception:
        pass

    # (b) PROMPT real: estado+memoria+recall (bajo demanda) + 2º pase de CORTO (contexto reciente ampliado si el
    #     turno lo referencia) + BREAK-LOOP si el asistente se estaba repitiendo.
    recall_q = operator_text if needs_recall(operator_text) else ""
    recent_block = compose_recent_block() if needs_recent(text) else ""
    timings["recent_fired"] = bool(recent_block)
    system, _used = build_flash_system(directive=sess.directive, recall_query=recall_q,
                                       recent_block=recent_block, timings=timings, turn_text=text)
    nudge = dialog.loop_nudge(sess.window)
    if nudge:
        system += nudge

    messages = [{"role": "system", "content": system}]
    messages += dialog.prune_window(sess.window)[-_WINDOW_MAX:]
    messages.append({"role": "user", "content": text})

    # (c) captura de tool calls y tags (en vez de ejecutarlos)
    tool_calls: list[dict] = []
    tags: list[dict] = []

    def _on_tool_call(name: str, args: dict) -> None:
        tool_calls.append({"name": name, "args": args})

    def _tag_emit(action: str, extra: dict) -> None:
        if action == "show":
            contextual = _show_target(text, sess.window, sess.last_action)
            if contextual:
                extra = {**(extra or {}), "id": contextual}
        tags.append({"action": action, "extra": {k: v for k, v in (extra or {}).items() if k != "data"}
                     or (extra or {})})

    # (d) stream del modelo real
    buf = ""
    raw = ""
    spec = spec_from_config()
    if model:
        import dataclasses
        spec = dataclasses.replace(spec, model=model)   # A/B de modelos: mismo proveedor/base/key, otro modelo
    llm_metrics: dict = {}   # totalizadores de tamaño/tokens/latencia (observabilidad, FASE 0) — igual que la voz
    _ttft = None
    # set CONTEXTUAL de tools, igual que la voz (V2-035): situacionales fuera si no aplican
    _cpend = _apend = False
    try:
        from widgets import confirm as _cf
        _cpend = bool(_cf.pending())
    except Exception:
        pass
    try:
        from widgets.navegador import tasks as _nt
        _apend = bool(_nt.login_waiting_id())
    except Exception:
        pass
    # V2-038: mismas señales que la voz (impl PARALELA — cablear en AMBOS): workers vivos / ask pendiente.
    _hw = _akp = False
    try:
        from nucleo import dispatch as _disp_p, worker_api as _wapi_p
        _hw = _disp_p.has_active()
        _akp = _wapi_p.has_pending_ask()
    except Exception:
        pass
    # V2-086: espejo de la voz (impl PARALELA — cablear en AMBOS). El gate por widget desapareció con el propio
    # widget: las tools de cluster se ofrecen siempre y la protección es el confirm Sí/No determinista.
    try:
        from connectors import meshkore as _mk_p
        _cl_conn_p = any(c.get("connected") for c in _mk_p.get_manager().clusters())
    except Exception:
        _cl_conn_p = False
    _turn_tools = _router.tools(_router.tool_context(confirm_pending=_cpend, auth_pending=_apend,
                                                     has_workers=_hw, ask_pending=_akp,
                                                     cluster_widget_open=True, cluster_connected=_cl_conn_p))
    llm_metrics["n_tools_offered"] = len(_turn_tools)
    try:
        async for delta in FastClient().stream(messages, spec=spec, tools=_turn_tools,
                                                on_tool_call=_on_tool_call, metrics=llm_metrics):
            if _ttft is None:
                _ttft = round((time.time() - t0) * 1000, 1)
            buf += delta
            raw += delta
            out, buf = strip_tags(buf, _tag_emit, False)
            _ = out
        out, buf = strip_tags(buf, _tag_emit, True)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"modelo: {str(e).splitlines()[0][:200]}", "spec": f"{spec.provider}/{spec.model}"}

    spoken = speech.sanitize(strip_tags(raw, lambda *a: None, True)[0], drop_metadata=False)
    degenerate = dialog.looks_degenerate(spoken)
    spoken = dialog.sanitize_reply(spoken)

    # (e) acción derivada (qué HARÍA el turno real)
    names = [t["name"] for t in tool_calls]
    reveal_out = None                       # V2-060: desenlace de reveal_secret (sin el valor — lo sirve la API)
    # hard-interrupt DETERMINISTA (V2-015) — ESPEJO del provider (nucleo.py:122): 'cierra todo'/'quita todo' →
    # [[close]] TODO; 'para'/'silencio'/'basta' → corta sin acción. En voz/chat se resuelve ANTES que el LLM; sin
    # este espejo el probe daba veredictos FALSOS ('cierra todo' caía en widget_data ~60% de las veces, 2026-07-21).
    try:
        from voice import attention as _att_p
        _hard = _att_p.hard_interrupt(text)
    except Exception:
        _hard = None
    if _hard == "close":
        action = "canvas:close"
    elif _hard == "stop":
        action = "chat"
    elif "stop_worker" in names:
        action = "stop_worker"
    elif "send_to_worker" in names:
        action = "send_to_worker"
    elif "answer_worker" in names:
        action = "answer_worker"
    elif "escalate_to_slowbrain" in names:
        action = "escalate"
    elif "web_search" in names:
        action = "search"
    elif "reveal_secret" in names:
        # V2-060 (espejo del provider — impl PARALELA, cablear en AMBOS): el operador pide un secreto guardado.
        # Resolvemos el DESENLACE (no_vault/empty/locked/not_found/ok) SIN exponer el valor en la respuesta del
        # probe (invariante). El valor lo sirve /api/vault/reveal; el tester lo conduce con la passphrase.
        action = "reveal_secret"
        _rl = next((t["args"].get("label") for t in tool_calls if t["name"] == "reveal_secret"), "") or text
        try:
            from . import vault_flow as _vf
            _rv = await asyncio.to_thread(_vf.reveal, str(_rl))
        except Exception:
            _rv = {"status": "error"}
        reveal_out = {"status": _rv.get("status"), "label": _rv.get("label"),
                      "memory_id": _rv.get("memory_id"), "candidates": _rv.get("candidates")}
    elif "play_music" in names:
        action = "music"                     # V2-041: ruta ligera; el turno real lo resuelve por el conector activo
    elif "play_video" in names:
        action = "canvas:show:youtube"       # V2-045: VER → widget youtube (show + data-op load); espejo del provider
    elif "show_panel" in names:
        # V2-079: abre el PANEL nativo lateral (chat/procesos/crons) por voz — espejo del provider (emite `panel`).
        _sp = next(t for t in tool_calls if t["name"] == "show_panel")
        action = "panel:" + _router._canon_panel(_sp["args"].get("panel"))
    elif "manage_widget_alias" in names:
        # V2-082: añadir/quitar un alias de un widget — espejo del provider (que SÍ escribe el manifest). El probe
        # solo CLASIFICA el routing (no muta manifests en pruebas): resuelve el widget y reporta alias:add|remove:id,
        # o 'clarify' si no se localiza el widget.
        _ma = next(t for t in tool_calls if t["name"] == "manage_widget_alias")
        _op = "remove" if str(_ma["args"].get("op") or "add").lower().startswith(("rem", "quit", "borr")) else "add"
        try:
            from widgets import runtime as _rta
            _awid = (_ma["args"].get("widget_id") or "").strip()
            _rid = _awid if (_awid and _rta.get(_awid) is not None) else (_identify_ctx(_rta, _awid or text) or "")
        except Exception:
            _rid = ""
        action = f"alias:{_op}:{_rid}" if _rid else "clarify"
    elif "show_widget" in names:
        # MOSTRAR una pieza por NOMBRE/ALIAS con CERTEZA (V2-082) — espejo del provider: CREATE→escala; si hay match
        # de widget → [[show:id]]; si nombró el CHAT (superficie) → panel; sin match → PREGUNTA (clarify), NUNCA
        # fabrica un widget ("no se abre el más parecido").
        _sw = next(t for t in tool_calls if t["name"] == "show_widget")
        _swid = (_sw["args"].get("widget_id") or "").strip()
        if _router.looks_like_create_widget(text):
            action = "escalate"
        else:
            from widgets import runtime as _rt
            _res = {}
            try:
                _contextual = _show_target(text, sess.window, sess.last_action)
                if _contextual:
                    _res = {"match": _contextual, "system": None}
                elif _swid and _rt.get(_swid) is not None:
                    _res = {"match": _swid, "system": None}
                else:
                    _o, _r = _ctx_ids()
                    _res = _rt.identify(_swid or text, open_ids=_o, recent_ids=_r) or {}
            except Exception:
                _res = {}
            _rid = _res.get("match") or ""
            _rid = _rid if (_rid and _rt.get(_rid) is not None) else ""
            _sys = _res.get("system")
            action = (f"canvas:show:{_rid}" if _rid else
                      "panel:chat" if _sys == "chat" else "clarify")
    elif "fullscreen_widget" in names:
        # BUG real 2026-07-23 — espejo del provider: pone/quita pantalla completa de verdad. Resuelve el id por
        # nombre/alias con certeza (V2-082); sin match → pregunta (no fabrica).
        _fw = next(t for t in tool_calls if t["name"] == "fullscreen_widget")
        _fwid = (_fw["args"].get("widget_id") or "").strip()
        try:
            from widgets import runtime as _rtf
            if _fwid and _rtf.get(_fwid) is not None:
                _frid = _fwid
            else:
                _m = _identify_ctx(_rtf, _fwid or text) or ""
                _frid = _m if (_m and _rtf.get(_m) is not None) else ""
        except Exception:
            _frid = ""
        action = f"canvas:fullscreen:{_frid}" if _frid else "clarify"
    elif "widget_data" in names:
        # ESPEJO de la voz (`_handle_widget_data_tool`, impl PARALELA — cablear en AMBOS): la voz NO ejecuta a
        # ciegas el nombre de la tool — resuelve el widget, consulta `action_mode` y (diag sesiones-largas
        # 2026-07-15) mapea un VERBO DE CANVAS no declarado ("show"/"close") a la tag directa, o escala si la
        # acción no existe. Sin este espejo el probe reporta "widget_data ✗" donde la voz real hace show.
        action = "widget_data"
        try:
            from widgets import runtime as _rt

            from . import frontend as _fe
            _wd = next(t for t in tool_calls if t["name"] == "widget_data")
            _wid = str(_wd["args"].get("widget_id") or "").strip().lower()
            _act = str(_wd["args"].get("action") or "").strip()
            if _wid and _rt.get(_wid) is None:   # id flojito → resuélvelo contra el catálogo, como la voz
                _wid = (_identify_ctx(_rt, _wid) or _identify_ctx(_rt, text) or _wid)
            if _fe.action_mode(_wid, _act) is None:
                _cv = _fe.canvas_verb(_act)
                if _cv and _rt.get(_wid) is not None:
                    action = f"canvas:{_cv}:{_wid}"
                else:
                    action = "escalate"          # acción inventada sin verbo de canvas → la voz escala
            # ESPEJO del guard del provider (2026-07-21, caso «hay que cancelarlo»): un PRONOMBRE SUELTO como item
            # ("lo/eso") sobre un widget que NO está abierto NI se nombra en el turno = mis-ruteo por verbo (el
            # antecedente vive en la conversación) → escala con contexto en vez de operar un widget cerrado.
            # BUG real (maratón 2026-07-22, mismo fix que nucleo.py): `looks_like_bare_ref("")` es True por
            # diseño → disparaba en TODA acción de CREAR (add_meeting…) que nunca lleva `item`. Solo aplica
            # cuando la acción REALMENTE referencia un item existente (tiene un campo `*Id` declarado).
            from widgets import refs as _refs
            _needs_item = bool(_refs.id_field_for_action(_wid, _act))
            if action == "widget_data" and _needs_item and _router.looks_like_bare_ref(str(_wd["args"].get("item") or "")):
                try:
                    from memory import api as _memapi
                    _ow = set((_memapi.state() or {}).get("open_widgets") or [])
                except Exception:
                    _ow = set()
                _named = _identify_ctx(_rt, text)
                if _wid not in _ow and _named != _wid:
                    action = "escalate"
        except Exception:
            pass
    elif "delete_widget" in names:
        # espejo del provider (V2-045): 'cierra el widget de X' → delete_widget se redirige a CLOSE (cerrar≠borrar).
        action = "canvas:close" if _router.looks_like_close(text) else "delete_widget"
    elif "authenticate_web" in names:
        action = "authenticate_web"
    elif "connect_cluster" in names:
        # espejo del provider (V2-064) — dry, como authenticate_web: reporta la acción, no abre una conexión real
        # de red desde el canal de prueba.
        action = "connect_cluster"
    elif any(n in names for n in ("confirm_widget_delete", "login_done")):
        action = names[0]
    elif "set_style_directive" in names:
        action = "style"
        _sd = next(t for t in tool_calls if t["name"] == "set_style_directive")
        d = (_sd["args"].get("directive") or "").strip()
        if d:
            # ESPEJO del provider (V2-046 A1, impl paralela — cablear en AMBOS): la regla se aplica ya (directiva
            # de sesión) y PERSISTE como user rule (state.rules). Gated a `ingest` (=turno real); con ingest=false
            # (tests de routing) NO se toca el estado. Sentido añadir/retirar por el guard determinista.
            if _router.looks_like_rule_removal(text):
                sess.directive = ""
                if ingest:
                    try:
                        from memory import api as _memapi
                        await asyncio.to_thread(_memapi.remove_user_rule, d)
                    except Exception:
                        pass
            else:
                sess.directive = d
                if ingest:
                    try:
                        from memory import api as _memapi
                        await asyncio.to_thread(_memapi.add_user_rule, d)
                    except Exception:
                        pass
    elif tags:
        show_ids = [str(t.get("extra", {}).get("id") or "") for t in tags if t["action"] == "show"]
        action = (f"canvas:show:{show_ids[-1]}" if show_ids and show_ids[-1]
                  else "canvas:" + ",".join(t["action"] for t in tags))
    else:
        action = "chat"

    # GUARD DETERMINISTA de SHOW-por-nombre (V2-038, espejo del provider `nucleo.py::_run` — impl PARALELA,
    # cablear en AMBOS): si el modelo ESCALÓ o buscó una petición que en realidad es MOSTRAR un widget que YA
    # existe (verbo de show + no-crear + `runtime.identify` resuelve), el turno real lo convierte en show. El
    # probe debe reportarlo igual, si no el test ve "escalate/search" donde la voz hace "show".
    # AMPLIADO 2026-07-19 (PROMESA SIN ACCIÓN, espejo del provider): también si el modelo solo CHARLÓ una promesa de
    # mostrar ("¿me enseñas la agenda?" → "aquí tienes la agenda" sin tool). No pisa música/vídeo/data (esos ya
    # resolvieron); _show_target exige verbo de show + identify real.
    if action in ("escalate", "search"):
        wid = _show_target(text, sess.window, sess.last_action)
        if wid:
            action = f"canvas:show:{wid}"
    # BACKSTOP PROMESA-SIN-ACCIÓN UNIFICADO (espejo del provider): el modelo charló una promesa sin tool → re-deriva
    # la intención. Gated por la promesa en la RESPUESTA. Generaliza sobre conjugaciones/cortesías.
    if action == "chat" and spoken:
        try:
            from . import router as _routerc
            if _routerc.promises_action(spoken):
                if (_routerc.looks_like_create_widget(text) or _routerc.looks_like_escalate_task(text)
                        or _routerc.looks_like_create_widget(spoken) or _routerc.looks_like_escalate_task(spoken)):
                    action = "escalate"
                elif _routerc.looks_like_show_strict(text):
                    from widgets import runtime as _rtp
                    _pw = (_rtp.identify(text) or {}).get("match")
                    if _pw:
                        action = f"canvas:show:{_pw}"
                elif _routerc.promises_music(spoken):
                    action = "music"
        except Exception:
            pass

    # GUARD MARKETPLACE → NAVEGAR (V2-057 2026-07-21, espejo del provider): un sitio de compraventa NOMBRADO
    # (Idealista/coches.net/Wallapop…) exige ENTRAR y navegar el catálogo, no un dato puntual de web_search ni un
    # "no puedo". Si el modelo eligió search/chat/show pero el texto nombra un marketplace → escala (navegador).
    # Alta precisión: el nombre del sitio + una intención de búsqueda/compra es señal fuerte de navegar.
    if action in ("search", "chat", "widget_data") or action.startswith("canvas:show") or action.startswith("canvas:unknown"):
        try:
            from . import router as _routerc2
            if _routerc2.looks_like_marketplace_nav(text) or _routerc2.looks_like_modify_widget(text):
                action = "escalate"
        except Exception:
            pass

    # BACKSTOP de CIERRE corto (sesión 22:40 2026-07-16, espejo del provider — cablear en AMBOS): «Vale,
    # ciérralo» → el modelo dice "cerrado" SIN emitir [[close]] (o cuela una data-op tipo mute). Orden corta de
    # cerrar (≤5 palabras, verbo de cerrar sin borrar) y ningún close en el turno → la voz cierra el widget
    # nombrado o el ÚNICO abierto; el probe lo reporta igual.
    # verbos AMPLIOS ('apaga/quita'): NO pises una acción ya tomada — si el turno resolvió MÚSICA ('apaga la música'
    # =stop audio), VÍDEO, búsqueda o data-op, el backstop de cierre NO cierra el widget además (espejo del guard
    # music_req/data_done del provider).
    # music/video/search/data ya resolvieron → no cerrar además. PERO un canvas:show ESPURIO en un turno de cerrar
    # SÍ debe corregirse a close (el modelo eligió show para 'podrías cerrar el reloj') → no lo metemos en _already.
    # BUG real 2026-07-23: "quita la pantalla completa" (verbo amplio 'quita' + turno corto + 1 widget abierto) NO
    # estaba en esta lista → el backstop de cierre de abajo CERRABA el widget entero en vez de solo salir de
    # fullscreen (fullscreen_widget YA resolvió la intención real este turno).
    _already = action.startswith(("music", "video", "search", "widget_data", "canvas:fullscreen"))
    if not _already and not any(t["action"] == "close" for t in tags):
        try:
            from . import router as _router0
            # AMPLIADO (sesión absurda 2026-07-19, espejo del provider): cerrar un widget NOMBRADO que está ABIERTO
            # cierra AQUÍ aunque el turno sea largo (una queja acompañaba «cierra el widget de música» → escaló a
            # modificar código y giró en bucle). Cerrar ≠ tarea de código.
            if _router0.looks_like_close(text) and not _router0.looks_like_create_widget(text):
                try:
                    from memory import api as _memapi
                    _ow = list((_memapi.state() or {}).get("open_widgets") or [])
                except Exception:
                    _ow = []
                _cw = None
                try:
                    from widgets import runtime as _rt
                    # los ABIERTOS desempatan ("cierra el vídeo": vídeo empata navegador↔youtube; gana el abierto)
                    _idc = _rt.identify(text, open_ids=_ow) or {}
                    if not _idc.get("ambiguous"):
                        _cw = _idc.get("match")
                except Exception:
                    _cw = None
                if not _cw and len(text.split()) <= 5 and len(_ow) == 1:
                    _cw = _ow[0]
                if _cw:
                    tags.append({"action": "close", "extra": {"id": _cw, "backstop": True}})
                    action = "canvas:close:" + _cw
        except Exception:
            pass

    # BACKSTOP de RESPUESTA A WORKER (espejo del provider — cablear en AMBOS): un worker ESPERA respuesta y el turno
    # corto ES esa respuesta, aunque el modelo mis-rutee a escalate/chat. Precede a la escalada espuria.
    if _akp and action in ("escalate", "chat") and "widget_data" not in names and len(text) <= 140:
        action = "answer_worker"

    # BACKSTOP de PARADA (espejo del provider L1182 — cablear en AMBOS): hay workers vivos, el operador ordena parar
    # trabajo y el modelo NO llamó stop_worker → se para de forma determinista (looks_like_stop_work). Cubre 'para
    # todas las tareas' cuando el no-razonador no emite la tool.
    if action == "chat" and "escalate_to_slowbrain" not in names:
        try:
            from nucleo import dispatch as _disp0
            from . import router as _router1
            if _disp0.has_active() and _router1.looks_like_stop_work(text):
                action = "stop_worker"
        except Exception:
            pass

    # BACKSTOP promesa-sin-acción → escalada de gestión WEB (V2-049, espejo del provider — cablear en AMBOS): el
    # modelo rápido a veces dice «me pongo con ello» sin llamar a escalate_to_slowbrain; si es una tarea web real,
    # la escalada la forzamos NOSOTROS (determinista). Arregla el «¿por qué te has parado?».
    if action == "chat" and spoken:
        import re as _re_prom
        _committed = bool(_re_prom.search(
            r"\b(me pongo con|me pongo a|ahora mismo|lo hago|lo hago ya|te lo (?:reservo|busco|miro|preparo|hago|"
            r"gestiono)|arranco|voy (?:con|a por|alla|alli|ya)|me meto en|enseguida|me encargo|lo pongo en marcha|"
            r"entro (?:en|a) la web)\b",
            "".join(c for c in __import__("unicodedata").normalize("NFKD", spoken) if not __import__("unicodedata").combining(c)).lower()))
        if _committed and _router.looks_like_web_task(text):
            action = "escalate"

    # PARIDAD con el canal vivo: recall y web_search are two-pass LIGHT routes. Historically the probe only
    # reported the tool and returned an empty reply, so a chronological headless conversation lost the assistant
    # turn and every following pronoun was tested against a state that can never occur in production.
    if "recall" in names and action == "chat":
        _rq = next((t["args"].get("query") for t in tool_calls if t["name"] == "recall"), "") or text
        try:
            from . import prompt as _prompt2
            _rblock, _ = await asyncio.to_thread(_prompt2.compose_recall, _rq)
            _sys2 = (_prompt2._lang_lock()
                     + "\nResponde en 1-3 frases habladas y naturales usando SOLO estos datos del operador. "
                       "No menciones capas ni memoria interna; si falta algo, dilo.\n\n"
                     + f"PETICIÓN: {text}\n\nDATOS:\n{_rblock or '(sin datos relevantes)'}")
            _parts = []
            async for _delta in FastClient().stream(
                    [{"role": "system", "content": _sys2}, {"role": "user", "content": text}],
                    spec=spec, max_tokens=260):
                _parts.append(_delta)
            spoken = dialog.sanitize_reply(speech.sanitize("".join(_parts), drop_metadata=False))
            action = "recall"
        except Exception:
            pass
    if action == "search":
        _sq = next((t["args"].get("query") for t in tool_calls if t["name"] == "web_search"), "") or text
        try:
            from nucleo import websearch as _ws
            from . import prompt as _prompt2
            _t_s = time.time()
            _res = await asyncio.to_thread(_ws.search, _sq)
            _ctx = _ws.format_results(_res)
            # PARIDAD DE OBSERVABILIDAD con el canal vivo (2026-08-10). El probe es una implementación PARALELA
            # del turno, y este camino no registraba nada: una búsqueda hecha por el canal de prueba no dejaba ni
            # la fila `search` ni su evidencia, así que auditar lo que hace el sistema dependía de por dónde
            # hubiera entrado la frase — justo el tipo de punto ciego que esta capa existe para no tener.
            try:
                from observability import evidence as _evd
                from voice.observer import emit as _emit_obs
                _x = {"source": _res.get("source"), "ai": bool(_res.get("ai")),
                      "n": len(_res.get("results", [])), "ms": round((time.time() - _t_s) * 1000),
                      "src": "probe", "evidence": _evd.web_results(_res.get("results"))}
                _a = _evd.body(_res.get("answer"))
                if _a:
                    _x["evidence"]["answer"] = _a
                _emit_obs("search", "🔎 resultados web", text=_sq, role="system", extra=_x)
            except Exception:
                pass
            _sys2 = (_prompt2._lang_lock()
                     + "\nResponde en 1-2 frases habladas, naturales, sin URLs, usando estos resultados web. "
                       "Si no contienen una respuesta clara, dilo; no inventes.\n\n"
                     + f"PREGUNTA: {_sq}\n\nRESULTADOS:\n{_ctx or '(sin resultados)'}")
            _parts = []
            async for _delta in FastClient().stream(
                    [{"role": "system", "content": _sys2}, {"role": "user", "content": _sq}],
                    spec=spec, max_tokens=240):
                _parts.append(_delta)
            spoken = dialog.sanitize_reply(speech.sanitize("".join(_parts), drop_metadata=False))
        except Exception:
            pass

    # (e-ter) EJECUCIÓN REAL de acciones de worker (V2-049, solo si execute=True) — para el test e2e de gestiones
    # web por TEXTO: la escalada arranca un Brain Worker REAL que conduce el navegador; inyección/respuesta/stop van
    # a un worker vivo. Marshalea al loop del server (mismo proceso). El resto de acciones (canvas/data/música) NO se
    # ejecutan aquí: este modo es para validar el ciclo de TAREAS, no el canvas.
    # BACKSTOP DE ORDEN IRREVERSIBLE (V2-128) — espejo del provider (impl PARALELA, cablear en AMBOS). Una orden
    # de pagar/comprar/cancelar que NO escaló está mis-ruteada: su sitio es una tarea, que además pasa por el
    # confirm-gate. Medido: «paga la factura de la luz antes del día 5» acabó creando un recordatorio.
    # Va fuera del `if execute` porque el probe REPORTA la decisión aunque no ejecute, y el test tiene que ver
    # `escalate` igual que lo vería la voz.
    if action in ("chat", "widget_data") or action.startswith("canvas:"):
        try:
            from nucleo import danger as _danger_bk
            if _danger_bk.is_dangerous(operator_text):
                action = "escalate"
        except Exception:
            pass

    if execute:
        # CONFIRMACIÓN de una TAREA irreversible parada por el confirm-gate (V2-126) — espejo del provider de
        # voz (impl PARALELA, cablear en AMBOS). Va ANTES que el resto: un «sí» reanuda la tarea PARADA, no abre
        # una nueva, así que tiene que poder anular la escalada de este turno.
        try:
            from nucleo import dispatch as _disp_cc
            if _disp_cc.pending_confirm():
                from widgets import confirm as _confirm_cc
                _v = _confirm_cc.classify_reply(text)
                if _v:
                    _r = _disp_cc.resolve_confirm(_v == "yes")
                    if _r:
                        action = "confirm_task"
                        return_extra_exec = {"executed": "confirm_task", "ok": bool(_r.get("ok"))}
        except Exception:
            pass
        # PROACTIVIDAD REAL (V2-121, 2026-08-18): las tags de cron se EJECUTAN, no solo se capturan. Va aparte del
        # `if action == …` de abajo a propósito — una tag de cron CONVIVE con una tool en el mismo turno, que es
        # justo el turno que este caso de uso pide («apúntame el jueves» → widget_data add_meeting, «y recuérdamelo
        # el miércoles» → [[cron.create]]); si compitiera por el mismo `action`, apuntar la cita mataría el aviso.
        #
        # Por qué existía el agujero: este módulo es la implementación PARALELA del provider de voz (el fichero lo
        # repite en cada backstop: «cablear en AMBOS»), y el bloque de ejecución solo cubría worker + data-op. El
        # canal `probe` es el que usan los casos de uso, así que el aviso NO PODÍA existir en una corrida por muy
        # bien que el modelo emitiera la tag: `remember-and-remind-deadline` medía un mecanismo inalcanzable.
        for _t in tags:
            if _t.get("action") not in ("cron.create", "cron.cancel"):
                continue
            try:
                from nucleo import scheduler as _sched
                _ex = _t.get("extra") or {}
                _d = _ex.get("data") or {}
                if _t["action"] == "cron.create":
                    _r = _sched.create((_d.get("prompt") or _d.get("task") or "").strip(),
                                       (_d.get("schedule") or _d.get("when") or "").strip(),
                                       name=(_d.get("name") or "").strip(), repeat=str(_d.get("repeat") or ""))
                    _t["executed"] = {"ok": bool(_r.get("ok")), "display": _r.get("display") or "",
                                      "error": _r.get("error") or ""}
                else:
                    _t["executed"] = {"ok": bool(_sched.cancel(_ex.get("name") or _d.get("name") or ""))}
            except Exception as _e:  # noqa: BLE001
                _t["executed"] = {"ok": False, "error": str(_e)[:200]}
            # Evento propio (kind `cron`) para que la programación DEJE RASTRO observable, igual que lo deja una
            # data-op o una escalada. Sin él, un aviso correctamente programado es indistinguible de uno que
            # nunca existió salvo consultando la BD — que es justo cómo se coló el fallo de V2-121.
            try:
                from voice.observer import emit as _emit_cron
                _ok = bool((_t.get("executed") or {}).get("ok"))
                _emit_cron("cron", "⏰ tarea programada" if _ok else "⚠️ schedule no reconocido",
                           text=str((_t.get("executed") or {}).get("display")
                                    or (_t.get("executed") or {}).get("error") or ""),
                           role="system", extra={"ok": _ok, "op": _t.get("action")})
            except Exception:
                pass
        try:
            if action == "escalate":
                # VARIAS tareas en un turno (V2-118, espejo del provider de voz — impl PARALELA, cablear en
                # AMBOS): el operador que encarga tres trabajos de una sentada emite tres llamadas, y antes solo
                # se ejecutaba la primera (`next(...)`). El tope de 3 es el mismo criterio que allí: el pool de
                # workers es real y limitado (`dispatch._max_parallel`).
                _reqs: list[str] = []
                for _tc in tool_calls:
                    if _tc["name"] != "escalate_to_slowbrain":
                        continue
                    _r = str(_tc["args"].get("request") or "").strip()
                    if _r and _r not in _reqs:
                        _reqs.append(_r)
                # Espejo del backstop del provider (impl PARALELA, cablear en AMBOS): si el turno pide CREAR
                # un widget y ninguna de las peticiones que van a salir lo es, se añade. Medido en V2-118: cero
                # tareas de kind `code` en 14 turnos pidiendo un juego.
                try:
                    from nucleo.flash import router_guards as _rg_cw
                    if (_rg_cw.looks_like_create_widget(operator_text)
                            and not any(_rg_cw.looks_like_create_widget(r) for r in _reqs)):
                        _reqs.append(operator_text)
                except Exception:
                    pass
                # `operator_text`, no `text`: el turno lleva las notas [SISTEMA] pegadas delante y una tarea
                # NUNCA debe tener por objetivo el mensaje de entrega del worker anterior.
                _reqs = _reqs[:3] or [operator_text]
                from nucleo.flash import escalate as _esc
                _tids = [_esc.escalate_to_slowbrain(str(_r), context={"src": "probe", "trace": _trace_id})
                         for _r in _reqs]
                return_extra_exec = {"executed": "escalate", "task_id": _tids[0], "task_ids": _tids}
            elif action == "send_to_worker":
                _msg = next((t["args"].get("message") for t in tool_calls
                             if t["name"] == "send_to_worker" and t["args"].get("message")), "") or text
                from nucleo import dispatch as _disp
                _disp.inject_soon("", str(_msg))
                return_extra_exec = {"executed": "inject"}
            elif action == "answer_worker":
                _ans = next((t["args"].get("answer") or t["args"].get("text") for t in tool_calls
                             if t["name"] == "answer_worker"), "") or text
                from nucleo import worker_api as _wapi
                _wapi.answer_active_soon(str(_ans))
                return_extra_exec = {"executed": "answer"}
            elif action == "stop_worker":
                from nucleo import dispatch as _disp
                _which = next((t["args"].get("which") for t in tool_calls if t["name"] == "stop_worker"), None)
                _disp.cancel_soon(str(_which) if _which else text)   # resuelve which del modelo, o del texto (bulk→todas)
                return_extra_exec = {"executed": "stop"}
            elif action == "widget_data":
                # EJECUCIÓN REAL de una data-op (2026-07-25): sin esto el probe validaba el ROUTING pero nunca
                # ENVIABA — imposible reproducir e2e "manda a zalo …". Ahora, si la acción es FAST, se despacha por
                # el MISMO camino que la voz (widgets.dispatch_tag → apply_action del widget). CONFIRM no se
                # auto-confirma (requiere el sí del operador); se reporta como pendiente. (V2-086: enviar al
                # cluster ya NO pasa por aquí — es la tool `cluster_send`, no una data-op de widget.)
                _wd = next((t["args"] for t in tool_calls if t["name"] == "widget_data"), {}) or {}
                _wid = (str(_wd.get("widget_id") or "")).strip().lower()
                _act = (str(_wd.get("action") or "")).strip()
                _pl = _wd.get("payload") if isinstance(_wd.get("payload"), dict) else {}
                from nucleo.flash import frontend as _fe
                from widgets import actions as _wa
                _mode = _fe.action_mode(_wid, _act)
                if _mode == _wa.FAST:
                    import widgets as _w
                    await _w.dispatch_tag("widget.data", {"id": _wid, "data": {"action": _act, "payload": _pl}})
                    return_extra_exec = {"executed": "widget_data", "widget": _wid, "act": _act}
                else:
                    return_extra_exec = {"executed": "widget_data_skipped", "mode": str(_mode), "widget": _wid, "act": _act}
            else:
                return_extra_exec = {}
        except Exception as e:  # noqa: BLE001
            return_extra_exec = {"execute_error": str(e)[:200]}
    else:
        return_extra_exec = {}

    # (e-bis) PARIDAD "nunca mudo" con la voz (round headless V2-038, hallazgos #1/#3): si el modelo fue directo
    # a la tool sin hablar, el provider emite un ack determinista (data_ack/show_ack/filler) — el probe debe
    # hacer LO MISMO, porque una data-op MUDA deja la ventana sin respuesta del asistente y el turno siguiente
    # ve la petición "sin atender" y la RE-DISPARA (context-bleed: la cita del dentista duplicada). Impl paralela:
    # cablear en ambos, siempre.
    if not spoken:
        try:
            from voice.engine.core import langs as _langs
            _lg = _langs.current_language()
            if action in ("widget_data", "confirm_task"):
                # `confirm_task` (V2-126) con el mismo ack corto que una data-op: el turno que resuelve un sí/no
                # no puede caer al backstop genérico y contestar «¿me lo repites?» a una confirmación.
                spoken = _lg.data_ack
            elif action.startswith("canvas:"):
                spoken = _lg.show_ack
            elif action in ("escalate", "send_to_worker", "stop_worker", "answer_worker", "authenticate_web",
                            "connect_cluster"):
                spoken = _lg.filler_holding
            elif action == "music":
                spoken = _lg.data_ack        # ack corto en el probe; el turno real dice lo que puso el conector
            elif action == "style":
                spoken = _lg.data_ack        # V2-046 A1: fijar/retirar una regla nunca deja el turno mudo
            else:
                # BACKSTOP GENÉRICO — turno de CHARLA pura (`action=="chat"` u otro no cubierto arriba) que
                # salió MUDO: el modelo no llamó a ninguna tool Y no dijo nada. Live bug (search-buy-used-car,
                # 2026-08-17): ninguno de los casos de arriba está gateado a `action=="chat"`, así que un turno
                # de check-in ("¿pudiste relanzarla?") con el modelo genuinamente sin respuesta se quedaba en
                # silencio total — y el turno SIGUIENTE, viendo ese hueco en la ventana, acabó ECOANDO la propia
                # pregunta del operador ("Dime algo, por favor. ¿Se relanzó la búsqueda...?", literalmente sus
                # palabras). Espejo del backstop genérico de `nucleo.py` (impl PARALELA, cablear en AMBOS).
                spoken = _lg.filler_still_working if _hw else "Perdona, ¿me lo repites?"
        except Exception:
            pass

    # CAPTURA FORENSE del turno (V2-040, espejo del provider de voz — cablear en AMBOS): prompt+ventana+tools+
    # decisión al fichero (categoría system). Así un test headless deja la misma traza diagnosticable.
    try:
        from voice import observer as _obs
        _obs.turn_detail(system=system, window=dialog.prune_window(sess.window)[-_WINDOW_MAX:], tools=_turn_tools,
                         user=text, decision={"action": action, "tool_calls": [t["name"] for t in tool_calls],
                                              "tags": [t["action"] for t in tags], "reply": spoken or ""})
    except Exception:
        pass

    # (f) actualiza la ventana con la respuesta SANEADA (corta el bucle de realimentación). El turno de usuario
    # entra por `dialog.push_user` para conservar la PARIDAD con la voz (que además lo usa para no perder la frase
    # de un turno pisado por solape del STT).
    dialog.push_user(sess.window, text)
    if spoken:
        sess.window.append({"role": "assistant", "content": spoken})
    del sess.window[:-_WINDOW_MAX]
    sess.last_action = action

    timings["total_ms"] = round((time.time() - t0) * 1000, 1)
    timings["ttft_ms"] = _ttft
    # totalizadores del modelo (tamaño + tokens + cold) fundidos en timings → visibles en `make flash`
    for _k in ("prompt_chars", "system_chars", "n_tools", "tools_chars", "n_msgs", "prompt_tokens",
               "prompt_tokens_est", "completion_tokens", "completion_tokens_est", "completion_chars",
               "total_ms", "cold_estimate", "gap_since_last_s", "usage_source"):
        if _k in llm_metrics:
            timings.setdefault(f"llm_{_k}" if _k in ("total_ms",) else _k, llm_metrics[_k])
    # VEREDICTO de latencia, igual que en la voz (paridad probe↔voz): prompt grande vs proveedor vs frío.
    try:
        from . import turn_perf as _perf
        timings["verdict"] = _perf.emit_verdict({
            **timings, "escalated": action == "escalate", "searched": action == "search",
            "engine": spec.provider, "model": spec.model,
            "tok_per_s": (round((llm_metrics.get("completion_tokens") or llm_metrics.get("completion_tokens_est") or 0)
                                / max(0.001, (llm_metrics.get("total_ms") or 0) / 1000.0), 1)
                          if llm_metrics.get("total_ms") else None)})
    except Exception:
        pass
    return {
        "ok": True,
        "reply": spoken,
        "action": action,
        "tool_calls": tool_calls,
        "tags": tags,
        "degenerate": degenerate,          # el output venía empalmado/repetido (se saneó)
        "loop_run": dialog.repeated_replies(sess.window),
        "turns": len([m for m in sess.window if m.get("role") == "user"]),
        "prompt_chars": len(system),
        "spec": f"{spec.provider}/{spec.model}",
        "metrics": llm_metrics,
        "timings": timings,
        "trace": _trace_id,                # V2-044: id de la cadena texto→acción→eventos en el timeline
        **return_extra_exec,               # V2-049: {executed, task_id} si execute=True disparó una acción de worker
        **({"reveal": reveal_out} if reveal_out else {}),   # V2-060: desenlace de reveal_secret (sin el valor)
    }


# ── HTTP + CLI (V2-098 split) ────────────────────────────────────────────────────────────────────────────
# The FastAPI router (say/reset) is a thin wrapper around run_turn()/_session()/_SESSIONS above; it lives in
# probe_api.py, which imports THIS module for those — the mount point (server/__init__.py) now imports `router`
# from probe_api directly, so this module does NOT import probe_api back (that would circular-import the moment
# this runs as `__main__`: runpy loads it as `__main__` AND, transitively, as `nucleo.flash.probe`). The CLI
# (_post/_fmt/main) needs none of this module's state — it only talks to the running server over HTTP — and
# lives in probe_cli.py; `python -m nucleo.flash.probe` still works via the __main__ block below.
if __name__ == "__main__":
    from nucleo.flash.probe_cli import main as _main
    _main()
