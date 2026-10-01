"""nucleo/flash/probe.py — FlashBrain HEADLESS TEST CHANNEL (V2-032, the third testing approach).

The PROBLEM it solves: fixing the FlashBrain conversation required a SUPER-FAST way to inject text and read its
response WITHOUT voice, the interface, or a LiveKit room — so real examples could be iterated from Claude Code
and evaluated immediately. The other two channels (memory tests; the INI-013 end-to-end voice tester) are slower
and include STT noise.

This channel runs INSIDE the server's live process (which already has memory/bus/state/widgets initialized by the
lifespan), so fidelity is maximal: it reproduces the CORE of the FlashBrain turn — the SAME prompt
(`build_flash_system` with state+memory+recall), the SAME model (`FastClient`), the SAME tools (`router.TOOLS`)
and the SAME dialogue safeguards (`dialog.py`) as the voice turn (`nucleo.py::_run`) — but without audio transport
or real widget execution: instead of ACTING, it REPORTS what it would do (selected tool/tag), the text, and
latencies. This makes it possible to evaluate the failures from the report (loops, degeneration, loss of thread,
and which state/memory the model saw).

Usage (with the server running and memory reset with `make reset`):
    curl -s localhost:43917/api/flash/say -H 'content-type: application/json' -d '{"text":"hola, ¿cómo te llamas?"}'
    python -m nucleo.flash.probe "hola"          # one-shot
    python -m nucleo.flash.probe                 # interactive REPL
    python -m nucleo.flash.probe --reset          # clears the probe conversation window
    make flash T="me llamo Alex"                  # one-shot shortcut
    make flash-repl                               # REPL shortcut

It does NOT touch the voice session (it uses its own `_SESSIONS` window). By default it INGESTS into memory like
the real turn (`ingest=true`) so state/memory tests are faithful; pass false for isolated conversation.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from nucleo.errors import brief as _brief
from nucleo.flash.panel_canon import wall_tab_for as _wall_tab_for
from nucleo.flash import music_turn as _music_turn, reminder_guards as _rg_mute
from nucleo.flash import image_turn as _image_turn, listing_turn as _lt
from nucleo.flash import video_turn as _video_turn
from nucleo.flash import widget_data_turn as _widget_data_turn
from nucleo.flash import probe_scheduling as _probe_scheduling
from .probe_actionmap import try_fast_lanes as _fast_lanes
from nucleo.flash import second_pass as _second
from nucleo.flash import harness_turn as _ht_p

_WINDOW_MAX = 10


@dataclass
class ProbeSession:
    """Conversation state for ONE test session (isolated from voice)."""
    window: list[dict] = field(default_factory=list)
    directive: str = ""
    seeded: bool = False   # window seeded from memory? (short-term circuit, mirror of nucleo.py::_run)
    smalltalk_bounce: bool = False   # V2-674: did OUR last phrasebook reply hand the question back?
    last_action: str = ""  # surface/action produced by the preceding turn (for deictic continuity)


_SESSIONS: dict[str, ProbeSession] = {}


def _session(sid: str) -> ProbeSession:
    return _SESSIONS.setdefault(sid or "default", ProbeSession())


# The show-target resolver (mirror of providers/nucleo.py) lives in show_target.py — extracted
# 2026-08-29 (architecture ratchet).
from .show_target import (  # noqa: F401
    _ctx_ids, _identify_ctx, _running_goals, _show_target, classify_alias_call,
    close_target as _close_target,   # demo pass 2026-09-28: close is a tool too
    fullscreen_target as _fullscreen_target,
    fullscreen_exit_due as _fullscreen_exit_due,   # V2-759
    last_assistant_line as _last_assistant_line, show_card as _show_card,
    show_instance as _show_instance,
)






async def _task_list(text: str, sess) -> dict | None:
    """The text channel's side of `fast_lane.task_list` (V2-771): the receipt line, or None → normal turn."""
    from nucleo import batch
    got = await batch.intake(text, origin="chat")
    if not got:
        return None
    from . import dialog
    dialog.remember_what_was_said(sess, text, _WINDOW_MAX)
    sess.window.append({"role": "assistant", "content": got["ack"]})
    return {"ok": True, "reply": got["ack"], "action": "task_list", "tool_calls": [], "tags": []}


async def run_turn(text: str, *, sid: str = "default", ingest: bool = True, model: str = "",
                   execute: bool = False, lists: bool = True) -> dict:
    """Run ONE headless FlashBrain turn and return an evaluable dict. Reproduces the core of
    `nucleo.py::_run` (real prompt + real model + real tools + dialogue safeguards) without voice or execution.
    `model` (optional) forces another fast model for the turn (A/B model testing, same provider/base/key).
    `execute` (V2-049, end-to-end TEST channel for web tasks): IN ADDITION to reporting, actually EXECUTES worker
    actions (escalation→real Brain Worker that drives the browser; injection/response/stop to a live worker) — this
    makes it possible to drive the entire lifecycle of a task (booking an appointment) by TEXT, without voice or STT noise."""
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
    # V2-605 — TURN-SCOPED, declared here and not inside the `show_widget` branch that sets it: the ack site far
    # below runs for EVERY `canvas:show:`, and several other paths reach it, so a branch-local name would raise
    # `UnboundLocalError` on exactly the routes that never disambiguate anything. Named the card we had to CHOOSE
    # when the operator had already been asked once and still did not pick; empty is the normal case.
    _show_chose = ""

    # VAULT: security config + spoken secret, decided by the SHARED gate (F1, 2026-08-23).
    # There were three mirror implementations and they had already drifted: this copy returned the note
    # “(encrypted secret)” where voice spoke a localized sentence, and V2-141 had to fix it twice. The
    # DECISION now lives in `nucleo/turn/vault_gate.py`; what remains specific to this channel is the DELIVERY (a
    # dict, not a voice) and `ingest`, which is why this path does not always encrypt: a dry run cannot write the
    # operator’s real secrets to the real vault.
    from nucleo.turn import vault_gate as _vault_gate
    _vg = await _vault_gate.inspect(text, store=bool(ingest))
    if _vg.kind == "config":
        return {"ok": True, "reply": [_vg.line], "action": "vault_config", "tool_calls": [], "tags": [],
                "security": {_vg.config[0]: _vg.config[1]}}
    if _vg.consumed:
        # REDACTED, never the raw line: this output exists precisely because the ENTIRE turn was a secret. What
        # the window preserves is the SHAPE of what happened, so the next turn knows that the operator spoke and
        # what it concerned.
        dialog.remember_what_was_said(sess, _vg.text, _WINDOW_MAX)
        return {"ok": True, "reply": [_vg.line],
                "action": "vault_save" if _vg.has_vault else "vault_need_create", "tool_calls": [], "tags": [],
                "secret": {"n": len(_vg.labels), "labels": _vg.labels, "vault": _vg.has_vault}}
    text = _vg.text          # el valor NO sobrevive; la petición que lo acompañaba sí se atiende

    # TRACEABILITY (V2-044, mirror of nucleo.py::_run): the probe turn also starts with a trace ID — the TEST
    # channel validates the text→action→events chain just like voice. The ID returns in the response (evaluable).
    _trace_id = ""
    try:
        from voice import trace as _trace
        _trace_id = _trace.begin(text, origin="probe")
    except Exception:
        pass

    # SHORT-TERM CIRCUIT (B, mirror of nucleo.py::_run): seed the window from the persistent conversation buffer
    # the first time — this lets the probe faithfully reproduce startup after reconnecting (seeded window), not
    # an artificially empty session. Best-effort.
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

    # Lanes that skip the model, MIRRORING the provider (map V2-539 · knock V2-640 · phrasebook V2-674).
    from voice.engine.core import langs as _lg_am
    # V2-771 — a list goes before every lane (see `fast_lane.task_list`); `lists=False` is a step of one.
    if lists and execute and (_tl := await _task_list(text, sess)):
        return _tl
    _lane = _fast_lanes(text, sess, execute=execute, trace_id=_trace_id, spec=_lg_am.spec,
                        pick_ack=_lg_am.pick_ack, smalltalk_book=_lg_am.smalltalk_book())
    if _lane is not None:
        return _lane

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
    try:
        from nucleo import request_row as _rq
        _rq.begin(operator_text, parent=_rq.step_parent(sid), origin="chat")     # V2-776 M1
    except Exception:  # noqa: BLE001
        pass

    # JEV CANVAS VERDICT (T-jev-show-close, ESPEJO del provider): una pregunta Choice barata
    # (show/close/neither) en su propio hilo mientras se monta el prompt y corre el modelo, lista en los
    # guardas de canvas. Consultiva: un "close" seguro licencia un [[close]] que la gramática no ve;
    # lo demás mantiene el camino de hoy. Nunca rompe el turno (None = solo gramática).
    # V2-770 — the WHOLE turn brief, as the voice provider fires it (`_brief = canvas_h = ask_for_turn`): it
    # carries the canvas verb too, and without it this channel had no verdict about WHICH action of an open
    # card was meant, so what it measured was a product voice does not run.
    canvas_h = _tbrief = None
    try:
        from nucleo.flash import turn_brief as _tb_probe
        canvas_h = _tbrief = _tb_probe.ask_for_turn(operator_text)
    except Exception:
        canvas_h = _tbrief = None
    if canvas_h is None:
        try:
            from nucleo.flash import show_target as _st_cnv
            canvas_h = _st_cnv.ask_canvas_async(operator_text)
        except Exception:
            canvas_h = None

    # (a2) DRENA brain_notes como el provider (paridad voz/probe, V2-053): las notas [SISTEMA] pendientes
    # (SlowBrain, proactive, Susurro repair_say) se anteponen al turno — sin esto el canal de prueba no podía
    # verificar el circuito nota→respuesta y las notas se quedaban esperando a un turno de VOZ.
    try:
        from voice import brain_notes as _bn
        from voice.observer import emit as _emit_note
        _notes = _bn.drain() if lists else []    # V2-771: a list step never eats HIS notes (see runner)
        if _notes:
            for _n in _notes:
                _emit_note("brain", "📩 system note → FlashBrain (probe)", text=_n, role="system")
            text = "\n".join(_notes) + "\n\n" + text
    except Exception:
        pass

    # (b) PROMPT real: estado+memoria+recall (bajo demanda) + 2º pase de CORTO (contexto reciente ampliado si el
    #     turno lo referencia) + BREAK-LOOP si el asistente se estaba repitiendo.
    # El recall DURABLE se compone FUERA del event loop y con presupuesto (`nucleo/turn/recall_budget`), igual
    # que en la voz. Antes se pasaba `recall_query=`, que es la ruta de COMPATIBILIDAD PARA TESTS —lo dice el
    # docstring de `build_flash_system`— y compone en línea: con la memoria lenta (medido el 2026-08-23 durante
    # una descarga de 1,1 GB) bloqueaba el proceso ENTERO y la tanda moría como «INFRA: timed out», sin nombrar
    # a la memoria por ningún sitio. Pasado el presupuesto el turno sigue SIN recall durable, que es peor
    # respuesta y no un agente muerto.
    from nucleo.turn import recall_budget as _recall
    recall_block, _rc_ids = await _recall.compose(operator_text if needs_recall(operator_text) else "", timings)
    recent_block = compose_recent_block() if needs_recent(text) else ""
    timings["recent_fired"] = bool(recent_block)
    system, _used = build_flash_system(directive=sess.directive, recall_block=recall_block,
                                       recent_block=recent_block, timings=timings, turn_text=text)
    nudge = dialog.loop_nudge(sess.window)
    if nudge:
        system += nudge

    messages = [{"role": "system", "content": system}]
    messages += dialog.prune_window(sess.window)[-_WINDOW_MAX:]
    messages.append({"role": "user", "content": text})
    # The prompt for THIS turn is now assembled from the window as it was, so the line can go in without
    # appearing twice — and from here on every exit path, including the ones added later, keeps it.
    dialog.remember_what_was_said(sess, text, _WINDOW_MAX)

    # (c) captura de tool calls y tags (en vez de ejecutarlos)
    tool_calls: list[dict] = []
    tags: list[dict] = []

    def _on_tool_call(name: str, args: dict) -> None:
        tool_calls.append({"name": name, "args": args})

    def _tag_emit(action: str, extra: dict) -> None:
        if action == "close":
            # V2-635 (espejo del guarda del provider) + licencia Jev (T-jev-show-close, lector COMPARTIDO
            # `show_target.close_has_order`, nunca una segunda implementación): un [[close]] sin orden se
            # descarta; un "close" seguro de Jev lo licencia (dos lectores de acuerdo).
            from nucleo.flash import direct_action as _da_close, show_target as _st_close
            if _da_close.order_is_inside(_tbrief, str((extra or {}).get("id") or "")):
                return                           # V2-770 — the order is an action inside the card, not this tag
            _has_order, _order_src = _st_close.close_has_order(text, canvas_h)
            if not _has_order:
                return
            if _order_src == "jev":
                try:
                    from voice.observer import emit as _emit_lic
                    _emit_lic("brain", "🔓 close licenciado por Jev (espejo del provider)",
                              text=(text or "")[:120], role="system",
                              extra={"cat": "flash", "kind_diag": "close_jev_licensed"})
                except Exception:
                    pass
        if action == "show":
            contextual = _show_target(text, sess.window, sess.last_action)
            if contextual:
                extra = {**(extra or {}), "id": contextual}
        tags.append({"action": action, "extra": {k: v for k, v in (extra or {}).items() if k != "data"}
                     or (extra or {})})

    # (d) stream from the real model
    buf = ""
    raw = ""
    spec = spec_from_config()
    # V2-307 — si el titular fijado por config está en COOLDOWN (acaba de fallar de verdad: un cooldown solo
    # existe porque `note_failure`/`note_stall` anotaron un fallo real), el turno ARRANCA ya en el escalón sano
    # que elegiría la cadena. Sin esto, cada turno quemaba un 402 en el titular seco antes de poder relevar —
    # medido a las 03:13-03:15 (2026-08-25): cuatro turnos mudos con el broker con fondos esperando al lado.
    # Con el titular sano (lo normal), esto no toca nada: el pin de config sigue mandando.
    try:
        from nucleo.flash import provider_chain as _pc0
        from nucleo.flash import provider_failure as _pf0
        _t0 = _pf0.tier_for(spec, _pc0.ROLE_VOICE)
        if _t0 is not None and not _pc0.tier_available(_t0):
            _n0 = _pc0.pick(_pc0.ROLE_VOICE)
            if _n0 and _n0.get("name") != _t0.get("name"):
                spec = _pc0.spec_for(_n0)
    except Exception:
        pass
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
    # UN FALLO DE PROVEEDOR SE DICE, Y ADEMÁS SE RELEVA — ESTE MISMO TURNO (V2-252). Reportarlo ya se hacía
    # (2026-08-15); relevar, no: el turno moría con un escalón sano esperando al lado. Medido por el arnés el
    # 2026-08-21 y es lo que le tuvo OCHO HORAS sin poder medir — con la cadena real sembrada, un turno devolvía
    # `{"ok":false,"error":"modelo: 402 Insufficient Balance"}` en el MISMO SEGUNDO en que el log decía
    # «`deepseek-directo` SIN SALDO → relevo a `aimlapi-failover`». La voz relevaba, i18n relevaba, el texto no.
    #
    # Mismo patrón que el canal de CLUSTER, que lleva haciéndolo desde 2026-08-03 (`connectors/meshkore/brain.py`):
    # un intento, un relevo, un reintento — y no más, para que un proveedor roto no se convierta en un bucle.
    #
    # SOLO se reintenta si el turno no había dicho NADA todavía. Con un 402 el stream muere antes del primer
    # delta, que es el caso real; pero si ya había salido texto o una tool, repetir el turno lo diría dos veces.
    _relay_done = False
    while True:
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
            break
        except Exception as e:  # noqa: BLE001
            _err = _brief(e, 200)
            from loguru import logger as _log

            from nucleo.flash import provider_chain as _pchain_err
            from nucleo.flash import provider_failure as _pfail
            _v = _pfail.handle(str(e), role=_pchain_err.ROLE_VOICE, spec=spec)
            _nxt = _v.get("relay")
            _virgen = not raw and not buf and not tool_calls
            if _nxt and not _relay_done and _virgen:
                _relay_done = True
                _log.warning(f"probe: relevo a «{_nxt['name']}» a mitad de turno tras «{_err}» — reintento")
                spec = _pchain_err.spec_for(_nxt)
                _ttft = None
                continue
            return {"ok": False, "error": f"modelo: {_err}", "spec": f"{spec.provider}/{spec.model}",
                    "sin_relevo": bool(_v.get("dry"))}

    spoken = speech.sanitize(strip_tags(raw, lambda *a: None, True)[0], drop_metadata=False)
    degenerate = dialog.looks_degenerate(spoken)
    spoken = dialog.sanitize_reply(spoken)

    # (e) acción derivada. V2-658/V2-660: lo que el turno DEBE lo decide la costura compartida y se sintetiza
    await _ht_p.mirror_probe(tool_calls, tags, spoken, text, llm_metrics)
    names = [t["name"] for t in tool_calls]
    reveal_out = None                       # V2-060: desenlace de reveal_secret (sin el valor — lo sirve la API)
    music_req = None                        # V2-380: lo que pidió `play_music`, para EJECUTARLO abajo
    video_req = None                        # V2-383: lo que pidió `play_video`, para EJECUTARLO abajo
    images_req = None                       # V2-457: lo que pidió `show_images`, igual
    # hard-interrupt DETERMINISTA (V2-015) — ESPEJO del provider (nucleo.py:122): 'cierra todo'/'quita todo' →
    # [[close]] TODO; 'para'/'silencio'/'basta' → corta sin acción. En voz/chat se resuelve ANTES que el LLM; sin
    # este espejo el probe daba veredictos FALSOS ('cierra todo' caía en widget_data ~60% de las veces, 2026-07-21).
    try:
        from voice import attention as _att_p
        _hard = _att_p.hard_interrupt(text)
    except Exception:
        _hard = None
    # V2-778 F1 — naming the turn's action from what the model called lives in `nucleo/flash/probe_decide.py`.
    _blk = await _probe_decide.name_the_action(
        _hard=_hard,
        _router=_router,
        _tbrief=_tbrief,
        _vault_gate=_vault_gate,
        ingest=ingest,
        names=names,
        sess=sess,
        tags=tags,
        text=text,
        tool_calls=tool_calls,
    )
    if '_cw' in _blk:
        _cw = _blk['_cw']
    if '_rt' in _blk:
        _rt = _blk['_rt']
    if '_show_chose' in _blk:
        _show_chose = _blk['_show_chose']
    if '_sp' in _blk:
        _sp = _blk['_sp']
    if 'action' in _blk:
        action = _blk['action']
    if 'images_req' in _blk:
        images_req = _blk['images_req']
    if 'music_req' in _blk:
        music_req = _blk['music_req']
    if 'reveal_out' in _blk:
        reveal_out = _blk['reveal_out']
    if 'video_req' in _blk:
        video_req = _blk['video_req']

    # GUARD DETERMINISTA de SHOW-por-nombre (V2-038, espejo del provider `nucleo.py::_run` — impl PARALELA,
    # cablear en AMBOS): si el modelo ESCALÓ o buscó una petición que en realidad es MOSTRAR un widget que YA
    # existe (verbo de show + no-crear + `runtime.identify` resuelve), el turno real lo convierte en show. El
    # probe debe reportarlo igual, si no el test ve "escalate/search" donde la voz hace "show".
    # AMPLIADO 2026-07-19 (PROMESA SIN ACCIÓN, espejo del provider): también si el modelo solo CHARLÓ una promesa de
    # mostrar ("¿me enseñas la agenda?" → "aquí tienes la agenda" sin tool). No pisa música/vídeo/data (esos ya
    # resolvieron); _show_target exige verbo de show + identify real.
    # V2-778 F1 — the mirrors of the voice backstops live in `nucleo/flash/probe_mirrors.py`.
    _blk = await _probe_mirrors.mirror_the_voice_backstops(
        _akp=_akp,
        _cw=locals().get('_cw'),
        _hw=_hw,
        _router=_router,
        _rt=locals().get('_rt'),
        _sp=locals().get('_sp'),
        _tbrief=_tbrief,
        action=locals().get('action'),
        canvas_h=canvas_h,
        dialog=dialog,
        names=names,
        operator_text=operator_text,
        sess=sess,
        spec=spec,
        speech=speech,
        spoken=spoken,
        tags=tags,
        text=text,
        tool_calls=tool_calls,
    )
    if '_ar' in _blk:
        _ar = _blk['_ar']
    if '_forced_search' in _blk:
        _forced_search = _blk['_forced_search']
    if '_window_goal' in _blk:
        _window_goal = _blk['_window_goal']
    if 'action' in _blk:
        action = _blk['action']
    if 'music_req' in _blk:
        music_req = _blk['music_req']
    if 'spoken' in _blk:
        spoken = _blk['spoken']
    # V2-778 F1 — answering a web search lives in `nucleo/flash/probe_after.py`.
    _blk = await _probe_after.answer_a_search(
        FastClient=FastClient,
        _forced_search=_forced_search,
        _res=locals().get('_res'),
        action=action,
        dialog=dialog,
        operator_text=operator_text,
        spec=spec,
        speech=speech,
        text=text,
        tool_calls=tool_calls,
    )
    if 'spoken' in _blk:
        spoken = _blk['spoken']

    # BÚSQUEDA DE ANUNCIOS (V2-556) — espejo del provider (impl PARALELA, cablear en AMBOS). El cuerpo es
    # COMPARTIDO (`listing_turn.run`: pasada rápida → hoja → auto-escalación con la hoja heredada, y él mismo
    # emite la fila de observabilidad), así que este canal solo añade la composición hablada. Bajo `execute`
    # porque la pasada busca de verdad y puede lanzar un worker real: el banco de ruteo (2.13) tiene que poder
    # VER la decisión `listings` sin pagar ninguna de las dos cosas — igual que `escalate` se reporta aquí y
    # solo se ejecuta más abajo.
    if action == "listings" and execute:
        _lc = next((t["args"] for t in tool_calls if t["name"] == "search_listings"), {}) or {}
        _, _said = await _lt.voice_turn(_lt.request_from(_lc, text), operator_text or text, spec=spec)
        if _said:
            spoken = dialog.sanitize_reply(speech.sanitize(_said, drop_metadata=False))

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

    # V2-770 — a commission about to cost minutes whose verdict names an action of an OPEN card gets one pass
    # with that card's fields first (`act_repair`). Measured: «a partir de noviembre ya no hay piano» →
    # `agenda:cancel_meeting` at 0.96, and a worker was spawned for a two-field data-op the rung below cannot
    # fill by itself. Mirror of the voice provider; a dangerous sentence never takes this path.
    if action == "escalate" and "widget_data" not in names:
        try:
            from nucleo import danger as _danger_ar
            from . import act_repair as _ar_esc, direct_action as _da_esc
            _owner, _owner_act = _da_esc.from_brief(_tbrief)
            if _owner and not _danger_ar.is_dangerous(operator_text):
                _ar = await _ar_esc.call_for_promise_or_order(operator_text, spoken or text, _owner, _owner_act,
                                                              spec=spec)
                if _ar:
                    tool_calls.append({"name": "widget_data", "args": {"widget_id": _ar["widget_id"],
                                       "action": _ar["action"], "payload": _ar["payload"], "_repair": True}})
                    action, spoken = "widget_data", ""
        except Exception:
            pass

    # V2-778 F1 — executing the decision lives in `nucleo/flash/probe_after.py`.
    _blk = await _probe_after.execute_what_was_decided(
        _kind=locals().get('_kind'),
        _r=locals().get('_r'),
        _res=locals().get('_res'),
        _tbrief=_tbrief,
        _trace_id=_trace_id,
        _window_goal=_window_goal,
        action=action,
        execute=execute,
        images_req=images_req,
        music_req=music_req,
        operator_text=operator_text,
        sess=sess,
        spoken=spoken,
        tags=tags,
        text=text,
        tool_calls=tool_calls,
        video_req=video_req,
    )
    if 'action' in _blk:
        action = _blk['action']
    if 'return_extra_exec' in _blk:
        return_extra_exec = _blk['return_extra_exec']

    # (e-bis) PARIDAD "nunca mudo" con la voz (round headless V2-038, hallazgos #1/#3): si el modelo fue directo
    # a la tool sin hablar, el provider emite un ack determinista (data_ack/show_ack/filler) — el probe debe
    # hacer LO MISMO, porque una data-op MUDA deja la ventana sin respuesta del asistente y el turno siguiente
    # ve la petición "sin atender" y la RE-DISPARA (context-bleed: la cita del dentista duplicada). Impl paralela:
    # cablear en ambos, siempre.
    # V2-778 F1 — the words the turn owes live in `nucleo/flash/probe_after.py`.
    _blk = await _probe_after.the_words_it_owes(
        _hw=_hw,
        _parts=locals().get('_parts'),
        _show_chose=_show_chose,
        action=action,
        images_req=images_req,
        return_extra_exec=locals().get('return_extra_exec'),
        sess=sess,
        spoken=spoken,
        tags=tags,
        text=text,
        video_req=video_req,
    )
    if '_lg' in _blk:
        _lg = _blk['_lg']
    if 'spoken' in _blk:
        spoken = _blk['spoken']

    # V2-469 — a promise must not outlive its own delivery: when the model DID speak («voy a buscar…»)
    # while its list-search already filled the player, the canned naming above never fired (it is gated
    # on the mute turn) — the user had to ask for the titles and the next turn the model DENIED having
    # searched. The decision lives once in `video_turn.ensure_delivery_named`; a non-list turn is a no-op.
    if action == "canvas:show:youtube" and video_req and isinstance(return_extra_exec, dict):
        try:
            spoken = _video_turn.ensure_delivery_named(spoken, return_extra_exec)
        except Exception:
            pass
    # V2-469 — and the FAILURE rides along too: a spoken narration over a failed data-op («te muestro el
    # siguiente» over «No hay más vídeos en la lista») lied because the honest canned line only replaced
    # a mute turn. Sibling augmentation, failure direction.
    if action == "widget_data" and isinstance(return_extra_exec, dict):
        try:
            spoken = _widget_data_turn.ensure_failure_named(spoken, return_extra_exec)
        except Exception:
            pass

    # EL BACKSTOP DE ENTREGA (V2-305/336/339, extraído a `delivery` en V2-340): una respuesta de pura espera
    # con la hoja ya llena de filas frescas sale CON ellas, y su silencio queda registrado con las entradas de
    # la decisión. Aquí solo se le pasa la respuesta del turno; el porqué de cada regla vive en su módulo.
    from . import delivery as _delivery
    spoken = _delivery.apply_to_reply(spoken, sess.window)

    # CAPTURA FORENSE del turno (V2-040, espejo del provider de voz — cablear en AMBOS): prompt+ventana+tools+
    # decisión al fichero (categoría system). Así un test headless deja la misma traza diagnosticable.
    try:
        from voice import observer as _obs
        _obs.turn_detail(system=system, window=dialog.prune_window(sess.window)[-_WINDOW_MAX:], tools=_turn_tools,
                         user=text, decision={"action": action, "tool_calls": [t["name"] for t in tool_calls],
                                              "model_calls": [{"name": t.get("name"), "args": t.get("args")} for t in tool_calls][:12],
                                              "tags": [t["action"] for t in tags], "reply": spoken or ""})
    except Exception:
        pass

    # (f) actualiza la ventana con la respuesta SANEADA (corta el bucle de realimentación). El turno de usuario
    # entra por `dialog.push_user` para conservar la PARIDAD con la voz (que además lo usa para no perder la frase
    # de un turno pisado por solape del STT).
    dialog.push_user(sess.window, text)
    if spoken:
        sess.window.append({"role": "assistant", "content": spoken})
    elif tags or tool_calls:
        from i18n import langs as _lg
        dialog.record_silent_action(sess.window, _lg.current_language().data_ack)
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


# V2-778 F1 — what runs after the model answered lives in `nucleo/flash/probe_after.py`. A module import at the
# end (that module reads this one's names) keeps the two-way reference safe whichever is imported first.
from nucleo.flash import probe_after as _probe_after  # noqa: E402
from nucleo.flash import probe_decide as _probe_decide  # noqa: E402 — V2-778 F1, reads this module back
from nucleo.flash import probe_mirrors as _probe_mirrors  # noqa: E402 — V2-778 F1, reads this module back
