#
# NUCLEO brain (zaelar v2 «Colmena») as a LiveKit LLM provider (EPIC-v2-colmena, V2-004).
#
# El FlashBrain (código PROPIO, `nucleo/flash/`) enchufado al motor de voz por la MISMA costura que `duo`: el
# LLMStream lee el último turno del ChatContext, corre el FlashBrain y emite ChatChunk YA LIMPIADOS (pasan por
# strip_tags→side-effects→speech). El contrato agnóstico del motor se conserva.
#
# Diferencia con `duo`: NO hay Hermes. La memoria de arranque y el contexto salen de la memoria central propia
# (`memory/`, inyectada en el prompt por `nucleo/flash/prompt.py`). El escalado va a `nucleo/flash/escalate.py`
# (STUB en V2-004: registra + publica en el bus; el SlowBrain real llega en V2-006/V2-007). La degradación NO
# cae a Hermes — habla una frase de reserva.
#
# Se activa con BRAIN=nucleo (opt-in, en paralelo a duo/hermes; cero regresión hasta el cutover de V2-009).
#
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, llm, utils
from livekit.agents.llm import ChatChunk, ChoiceDelta

from .. import registry

_WINDOW_MAX = 10
_TAG_TASKS: set = set()


def _last_user_text(chat_ctx) -> str:
    """Último turno de usuario del ChatContext (el FlashBrain compone su propia ventana + memoria)."""
    try:
        items = list(chat_ctx.items)
    except Exception:
        items = []
    for it in reversed(items):
        if getattr(it, "role", None) != "user":
            continue
        txt = getattr(it, "text_content", None)
        if txt:
            return str(txt).strip()
        content = getattr(it, "content", None)
        if isinstance(content, list):
            return " ".join(c for c in content if isinstance(c, str)).strip()
        return str(content or "").strip()
    return ""


def _turn_budget_ms() -> int:
    """Cuánto SILENCIO se le tolera al modelo dentro de un turno de voz antes de darlo por atascado.

    No es la duración máxima del turno: se renueva con cada trozo hablable (ver el bucle de streaming), así que una
    respuesta larga sale entera. Es el plazo para que ALGO empiece a salir. 9 s ya es mucho hablando en voz alta;
    el único límite que había antes era el timeout de red de httpx, 60 s. Ajustable en caliente; 0 lo desactiva.
    """
    try:
        v = int(os.getenv("ZAELAR_TURN_QUIET_MS", "9000"))
    except ValueError:
        return 9000
    return v if v > 0 else 10 ** 9


def stream_advancing(metrics: dict, quiet_ms: int, now: float | None = None) -> bool:
    """¿El stream del modelo AVANZA aunque no salga nada hablable?

    Es la corrección de 2026-08-12, y viene de matar tres turnos SANOS en dos minutos. `fast_client.stream()` solo
    yieldea chunks CON TEXTO: los de una tool-call (argumentos goteando, `content` vacío) se consumen dentro y no
    salen. O sea que un turno cuya respuesta es una ACCIÓN —«muéstrame los resultados», «cierra eso»— se ve, desde
    el bucle del turno, exactamente igual que un modelo colgado. Medido en el corte de las 13:49: `ttft=1.50s` (el
    modelo había contestado en segundo y medio) con cero caracteres hablables; el plazo lo guillotinaba a los 9 s y
    el operador oía «se me ha ido un momento» sin llegar a ver sus resultados.

    Así que el plazo pregunta por el LATIDO del stream (`last_chunk_ts`, que sella quien sí ve cada chunk) y no por
    la voz. Sin sello todavía → False: nada ha llegado, es un atasco de verdad. Pura y sin IO a propósito."""
    last = float((metrics or {}).get("last_chunk_ts") or 0)
    if not last:
        return False
    return ((now if now is not None else time.time()) - last) * 1000.0 < quiet_ms


def _norm_utt(s: str) -> str:
    return " ".join((s or "").lower().split())


def _extends(prev: str, cur: str) -> bool:
    """¿`cur` es LA MISMA frase que `prev`, solo más larga?

    Señal puramente ESTRUCTURAL, no semántica: el STT entrega la transcripción ACUMULADA de la frase en curso, así
    que un fragmento de algo que el operador sigue diciendo es un PREFIJO del turno siguiente. Detectarlo así no
    necesita tablas de verbos ni heurísticas de idioma — vale igual en castellano, en japonés o dictando código.
    """
    p, c = _norm_utt(prev), _norm_utt(cur)
    return bool(p) and len(c) > len(p) and c.startswith(p)


# Cuánto tiempo sigue "en gracia" el trace de una cadena ya resuelta, para que el trozo siguiente de la MISMA
# frase lo adopte en vez de abrir un flujo nuevo (V2-116). 3 s cubre con holgura las pausas reales medidas dentro
# de una frase (V2-096: p50 2,3 s) sin llegar a pegar dos peticiones distintas: pasada la ventana, tema nuevo =
# flujo nuevo, como siempre.
_CHAIN_GRACE_S = float(os.getenv("ZAELAR_CHAIN_GRACE_S", "3.0"))


def _begin_or_adopt_trace(brain: "NucleoLLM", text: str, first_turn: bool) -> None:
    """Decide si este turno abre un trace NUEVO o ADOPTA el de una cadena de fragmentos ya a medias (V2-096
    addenda, 2026-08-15). LiveKit cierra un turno por CADA segmento final del STT, así que una frase larga dicha
    sin pausas abría un flujo nuevo por trozo — cada uno cancelado por el siguiente (barge-in) hasta que el
    último se completaba. El ACUMULADOR (`nucleo/flash/accumulator.py`) ya sabe si hay una cadena en curso
    (`.pending()`): mientras la tenga, este turno es esa misma frase creciendo → adopta su trace en vez de abrir
    uno nuevo, sin repetir aquí el juicio de completitud (ya es su trabajo). Un turno que empieza cadena nueva
    (buffer vacío) abre trace con `begin()` como siempre, y ese id pasa a ser el de la cadena hasta que se
    resuelva (`brain._acc_trace_id`, limpiado por el llamador cuando `offer()` devuelve "act").

    ⚠️ ESO SOLO NO BASTA, y volvió a romperse el 2026-08-18 (sesión b403c979, V2-116). La adopción se apoyaba
    ENTERAMENTE en que el acumulador tuviera la cadena abierta (`.pending()`), o sea en que la capa LÉXICA
    (`segmenter.looks_incomplete`) acertara al decir «esto está a medias». Un solo falso «completo» rompe la
    cadena y con ella el flujo: medido con los cinco finales de STT reales de esa sesión,
    `looks_incomplete("Mira, lo que quiero es")` devuelve **False** —una cláusula colgada de la cópula «es», que
    exige un complemento que aún no se ha dicho— así que el acumulador la SUELTA, `_acc_trace_id` se limpia
    (rama "act") y el trozo siguiente abre un flujo nuevo. En producción salieron CUATRO corr_ids de una sola
    frase, cada uno cancelando al anterior por barge-in.

    La continuidad del FLUJO no puede depender de acertar la completitud de la frase: son dos preguntas
    distintas, y el flujo es el esqueleto («cualquier acción continua que pueda durar minutos se asocia a un
    flujo», norma del operador). Por eso, al resolverse una cadena, su trace no se tira: queda en GRACIA unos
    segundos (`_CHAIN_GRACE_S`) y un turno que llegue dentro de esa ventana lo ADOPTA. Es estructural y
    barato — sin listas de palabras, sin LLM, sin latencia — y falla del lado seguro: como mucho une dos frases
    dichas casi seguidas en un flujo, que es MUCHO menos dañino que partir una frase titubeante en cuatro.
    La causa de raíz (el falso «completo» de la capa léxica, que además quema un prompt entero y deja un turno
    cancelado) queda documentada y reproducida en V2-116; tocar esas listas exige la medición contra el corpus
    que V2-095 dejó montada, no un parche a ojo.

    Función aparte (no inline en `_run_inner`) para que sea comprobable SIN un stream de LiveKit real — ver
    `tests/voice/unit/providers/test_nucleo_trace_merge.py`."""
    from voice import trace as _trace
    if first_turn:
        _trace.begin(text, origin="kickoff")
        return
    if getattr(brain, "_acc", None) is not None and brain._acc.pending() and brain._acc_trace_id:
        _trace.adopt(brain._acc_trace_id)
        return
    grace_tid, grace_ts = getattr(brain, "_chain_grace", ("", 0.0))
    if grace_tid and (time.time() - grace_ts) <= _CHAIN_GRACE_S:
        brain._acc_trace_id = grace_tid
        _trace.adopt(grace_tid)
        return
    brain._acc_trace_id = _trace.begin(text, origin="turno")


def _resolve_acc_chain(brain: "NucleoLLM") -> None:
    """Una cadena de fragmentos acaba de RESOLVERSE (`offer()` devolvió "act"): su trace deja de estar activo pero
    pasa a GRACIA en vez de tirarse, para que el trozo siguiente de la misma frase lo adopte
    (`_begin_or_adopt_trace`) en vez de abrir un flujo nuevo.

    Existe como función —y no como dos líneas dentro de `_run_inner`— para que el test pueda ejercitar EL MISMO
    código que corre en producción. Un test que se re-implemente la contabilidad del llamante puede pasar
    mientras producción hace otra cosa, que es exactamente el modo de fallo que V2-116 viene a cerrar."""
    if getattr(brain, "_acc_trace_id", ""):
        brain._chain_grace = (brain._acc_trace_id, time.time())
    brain._acc_trace_id = ""


_ACC_NUDGE_S = float(os.getenv("ZAELAR_ACC_NUDGE_S", "8.0"))


def _acc_notice_plan(action: str, dropped: str, n_before: int) -> tuple[bool, bool]:
    """Pure decision extracted from one `Accumulator.offer()` outcome (2026-08-15 fix): (speak_drop_notice,
    start_fresh_chain). Kept separate from the async plumbing (`_speak_acc_drop`/`_schedule_acc_nudge`) so it is
    testable without an event loop or a live voice session.

    `speak_drop_notice` fires whenever this call's `dropped` is non-empty, in EITHER branch — the bug this fixes
    is exactly that it used to only ever surface on "act" (see `Accumulator.offer` docstring). `start_fresh_chain`
    is true when this "hold" begins a chain with no prior context to lean on: either nothing was buffered before
    (`n_before == 0`) or what WAS buffered just got wiped by the drop — in both cases the operator is now waiting
    on a reply to a fragment the system has never seen the rest of, which is the case that needs a nudge if it
    drags on. `action != "hold"` never starts a chain (it just resolved one)."""
    fresh_chain = action == "hold" and (bool(dropped) or n_before == 0)
    return bool(dropped), fresh_chain


async def _speak_acc_drop(dropped: str) -> None:
    """A stale fragment chain just got discarded (`Accumulator`'s gap valve, > MAX_GAP_S). Silence here IS the
    bug: acknowledge it out of band (`voice.proactive.speaker()`, the same lead-in channel V2-093 uses for
    fillers) so the operator learns their earlier words weren't just ignored. Best-effort: no live speaker
    (probe/text channel, no session) → no-op; never talks over the operator mid-sentence
    (`proactive.user_speaking()`).

    V2-102: before settling for the generic "I missed that", give the JUDGE one more look at what got dropped —
    a genuinely complete or clarification-worthy request shouldn't get the same shrug as real gibberish just
    because the operator paused too long. `ASK` speaks the clarifying question right here, same as the live
    path. `COMPLETE` still speaks the generic notice (the operator needs SOME immediate signal) but ALSO pushes
    a `[SISTEMA]` note (`voice/brain_notes.py`) so the content itself surfaces on the NEXT turn instead of
    vanishing — never spoken unprompted, since nothing was just asked. Only a genuine `INCOMPLETE` verdict (the
    judge agrees there's nothing worth resurrecting) keeps today's plain behavior."""
    try:
        from voice import proactive
        speak = proactive.speaker()
        if speak is None or proactive.user_speaking():
            return
        from voice.engine.core import langs
        text = langs.current_language().acc_fragment_dropped
        try:
            from nucleo.flash import segmenter
            verdict, extra = await segmenter.judge(dropped)
            if verdict == "ask" and extra:
                text = extra
            elif verdict == "complete":
                try:
                    from voice import brain_notes
                    brain_notes.push(
                        f'[SISTEMA] El operador dijo esto antes de una pausa larga y no llegó a procesarse: '
                        f'"{dropped}". Si sigue vigente, atiéndelo en tu próxima respuesta.')
                except Exception:
                    pass
        except Exception:
            pass          # judge unavailable → fall back to the plain generic notice, same as before V2-102
        r = speak(text)
        if asyncio.iscoroutine(r):
            await r
    except Exception:
        pass


def _schedule_acc_nudge(brain: "NucleoLLM", gen: int) -> None:
    """Give the operator ONE gentle audible sign that a long HOLD is still "listening", not hung (the silence
    reported live: a 64s gap with zero signal either way). A pure reassurance ping, never an action: it never
    touches the accumulator's buffer, so it can't violate V2-096's no-timed-flush invariant — a fragment that
    never continues still gets no reply, only an acknowledgement that the system is waiting on it.

    `gen` pins the nudge to THIS chain (`brain._acc_gen`, bumped by the caller every time a chain resolves or gets
    dropped): if the chain already moved on by the time the delay elapses, the nudge checks the counter and
    no-ops instead of firing after the fact for a conversation that has already continued elsewhere."""
    async def _run() -> None:
        await asyncio.sleep(_ACC_NUDGE_S)
        if getattr(brain, "_acc_gen", None) != gen or not brain._acc.pending():
            return
        try:
            from voice import proactive
            speak = proactive.speaker()
            if speak is None or proactive.user_speaking():
                return
            from voice.engine.core import langs
            r = speak(langs.current_language().acc_still_listening)
            if asyncio.iscoroutine(r):
                await r
            from voice.observer import emit
            emit("brain", "🕒 sigo esperando el resto de la frase", role="system", extra={"cat": "flash"})
        except Exception:
            pass
    _spawn(_run(), "acc_nudge")


# Tools that CONTROL a running task rather than start something else. A turn that only used these (or none at
# all) is a turn about the task already in flight — see `_merge_target`.
_WORKER_CONTROL_TOOLS = frozenset({"send_to_worker", "stop_worker", "answer_worker", "recall", "need_capability"})


def _merge_target(tid: str, live_traces, turn_tools, just_escalated: bool = False) -> str:
    """Pure decision (V2-123): which LIVE task's flow should absorb this finished turn, or '' for none.

    The gap this closes was reported with a screenshot: while a worker searched for a guitar, "sí, muéstramelo todo
    en tiempo real" and the agent's reply to it opened a SEPARATE flow, because V2-090's merge only fires when the
    model happens to call `send_to_worker` (its handler is where `resolve_sessions` gets consulted). A follow-up
    the model answers conversationally — the most natural thing an operator says while waiting — matched nothing
    and split the thread. The operator's rule is the opposite: "siempre que nos estemos refiriendo a la misma
    tarea… todo tiene que ir en un mismo hilo cronológico".

    Deliberately NOT text matching. Both resolvers this module could have reused are wrong for attribution, and
    that mattered more than it looks: `dispatch.resolve_sessions` is loose ON PURPOSE ("mejor parar de más que
    dejar zombies") so with one live task it returns it for ANY wording — precision it does not actually have;
    `find_duplicate` is strict (60% content-word overlap) and "muéstramelo en tiempo real" shares zero words with
    "busca una guitarra zurda", so it would reject the very case this exists for. What IS solid evidence is state
    we already hold: exactly one task is running, and this turn started nothing else.

    Guards, each closing a way this could attribute wrongly:
      · `just_escalated` — this turn launched a NEW task; by definition its own thread (V2-113's signal, reused).
      · `tid` itself live — this trace already IS a task; it is not a loose turn looking for a home.
      · exactly ONE candidate — with several tasks running, which one a bare "¿cómo va?" refers to is a guess, and
        the standing rule since V2-090 is that a stray extra flow beats guessing.
      · tools outside `_WORKER_CONTROL_TOOLS` — putting on music or opening an unrelated widget is a turn about
        something else, whatever else is running.

    KNOWN false merge, accepted with eyes open: a purely conversational request that uses no tool ("cuéntame un
    chiste") while one task runs lands in that task's thread. The trade is deliberate — the operator asked for a
    COMPLETE thread, the split is the reported bug, and the mis-attribution is bounded to one live task's lifetime
    and stays visible (the board paints the `+N` chip). The upgrade that removes the guesswork is the model
    DECLARING continuation (V2-105's recommended design); that needs a tool-schema change and its own measurement,
    and it is not a reason to keep splitting threads meanwhile."""
    if not tid or just_escalated:
        return ""
    live = [t for t in (live_traces or []) if t]
    if tid in live:
        return ""
    candidates = [t for t in live if t != tid]
    if len(candidates) != 1:
        return ""
    if any(t not in _WORKER_CONTROL_TOOLS for t in (turn_tools or ())):
        return ""
    return candidates[0]


def _flow_should_close(tid: str, acc_trace_id: str, confirm_trace_ids, has_live_worker: bool,
                        just_escalated: bool = False) -> bool:
    """Pure decision: should THIS trace's flow close now? Factored out so it is comprobable without the observer/
    dispatch/confirm modules (see `tests/voice/unit/providers/test_nucleo_trace_merge.py`).

    A plain conversational turn never gets its own explicit close from anywhere else — only a worker-spawned flow
    does (`dispatch.py`'s `_run_session` finally block). Without this, the master can only guess "is this flow
    still active?" from RECENCY (`last_ms` within a window), which is wrong the instant a turn finishes: a
    completed kickoff/reply looks identical to a genuinely stuck one until the window expires minutes later —
    reported live by the operator ("he reiniciado el sistema... pero hay siete procesos activos").

    `just_escalated` (V2-113) closes a STRUCTURAL race, not an occasional one: `escalate_to_slowbrain()` publishes
    `escalate.requested` synchronously and returns, but `dispatch.run_listener` registers the SessionRecord that
    `has_live_worker` checks for ASYNCHRONOUSLY, on its own task — this function runs moments later, in the SAME
    synchronous turn that just published, before the event loop has given the listener a scheduler turn to react
    at all. Without this guard `has_live_worker` is reliably still False and the flow closes seconds before the
    worker it just spawned even starts (confirmed sub-ms apart on a real trace). Bounded, not indefinite: whatever
    `run_listener` decides — spawn (its own `_run_session` finally block closes it for real), reject-while-halted,
    or dedup-inject into a live session — always emits its own explicit close (`dispatch._close_escalated_flow`
    for the latter two), so this never leaves a flow stuck open."""
    if not tid:
        return False
    if acc_trace_id == tid:
        return False           # the V2-096 accumulator still expects a continuation on THIS trace
    if tid in confirm_trace_ids:
        return False           # a question asked on this trace is still waiting for the operator's answer
    if has_live_worker:
        return False           # a worker spawned on this trace is still running — IT owns the close
    if just_escalated:
        return False           # escalate.requested just published on THIS trace — see docstring above
    return True


# Turn TEXT can finish generating well before its own TTS finishes narrating it — closing the flow right then
# made the master board's column vanish while the agent was still audibly speaking (operator report, 2026-08-16:
# "le he hecho una pregunta... el turno ha desaparecido... la gente todavía me está contestando"). `_run()`'s
# success branch used to close immediately; now, if the bot is still speaking, it only QUEUES the close here and
# `agent.py`'s `on_state_change` drains the queue on the next speaking→idle transition (real audio playout done,
# see `agent_activity.py`'s post-playout state update — not the LLM stream returning, which fires from a sibling
# task and can't see it). Trace ids are captured HERE, inside this stream's OWN task, the only place
# `voice.trace.current()` is guaranteed to be THIS turn's — a later cross-task read could already see a newer
# turn's trace (LiveKit's `preemptive_generation`). The close itself uses `trace.scope(tid)` to stamp the event
# explicitly rather than relying on whatever trace happens to be ambient when the queue drains.
_PENDING_FLOW_CLOSES: dict[str, "NucleoLLM"] = {}


def drain_pending_flow_closes() -> None:
    """Nothing is speaking right now — safe to resolve every flow queued by `_maybe_close_flow` while its own
    TTS was still in flight. Re-checks each one's close conditions fresh (a confirm/worker could have started
    since it was queued), it doesn't just trust the snapshot taken at queue time."""
    if not _PENDING_FLOW_CLOSES:
        return
    pending = list(_PENDING_FLOW_CLOSES.items())
    _PENDING_FLOW_CLOSES.clear()
    for tid, brain in pending:
        _close_flow_now(tid, brain)


def _close_flow_now(tid: str, brain: "NucleoLLM") -> None:
    try:
        from widgets import confirm as _confirm_close
        from nucleo import dispatch as _disp_close
        confirm_trace_ids = {v.get("trace_id") for v in _confirm_close.pending().values()}
        _just_esc = (getattr(brain, "_escalated_trace_id", "") == tid)
        if not _flow_should_close(tid, getattr(brain, "_acc_trace_id", ""), confirm_trace_ids,
                                   _disp_close.has_live_trace(tid),
                                   just_escalated=_just_esc):
            return
        from voice import trace as _trace
        from voice.observer import emit as _emit_close
        # This turn was ABOUT a task already running → fuse the two flows instead of closing a second column
        # (V2-123). The absorbed trace does NOT emit its own end: a close counts for the folded row, so closing
        # here would mark the still-working titular as finished and drop it off the board. The worker owns it.
        _target = _merge_target(tid, _disp_close.live_traces(),
                                getattr(brain, "_turn_tools", ()), just_escalated=_just_esc)
        if _target:
            _trace.merge(_target, tid)
            return
        with _trace.scope(tid):
            _emit_close("flow", "end", role="system", extra={"ok": True, "reason": "turn_complete"})
    except Exception:
        pass


def _maybe_close_flow(brain: "NucleoLLM") -> None:
    """Called once a turn finishes CLEANLY (V2-090 addenda, 2026-08-15) — never on a barge-in cancellation
    (`_run`'s `except asyncio.CancelledError` branch skips this on purpose: whether a cancelled turn's trace gets
    continued by the next fragment or abandoned isn't knowable yet at cancellation time). Queues instead of
    closing outright when the bot is still speaking (see module comment above `_PENDING_FLOW_CLOSES`)."""
    try:
        from voice import trace as _trace
        tid = _trace.current()
        if not tid:
            return
        from voice import proactive as _proactive
        if _proactive.bot_speaking():
            _PENDING_FLOW_CLOSES[tid] = brain
            return
        _close_flow_now(tid, brain)
    except Exception:
        pass


def _release_acc_trace_if_fresh(brain: "NucleoLLM") -> None:
    """Real bug diagnosed live (2026-08-16): "cierra todos los widgets" turns sat "EN CURSO" in the master
    forever despite doing their job — closing the widgets — correctly. `_begin_or_adopt_trace()` sets
    `brain._acc_trace_id` for EVERY fresh (non-continuation) turn, on the assumption that the accumulator's
    `offer()` call further down `_run_inner` will clear it once the utterance resolves as complete. Three
    early-exit branches (hard interrupt, echo suppression, the not-directed/ambient gate) `return` BEFORE ever
    reaching `offer()` — their trace never gets released, and `_flow_should_close()`'s "a chain still expects a
    continuation on THIS trace" guard (there to protect a REAL pending fragment chain) ends up blocking that
    exact flow from EVER closing, since nothing later ever revisits the decision.

    Only safe to clear when the accumulator has nothing buffered: if it does, `_acc_trace_id` may belong to a
    genuine unresolved chain this turn merely ADOPTED (`_begin_or_adopt_trace`'s other branch, e.g. a "para"
    said mid-fragment) — clearing it there would end that unrelated chain's protection early, not just this
    turn's own bookkeeping."""
    if not getattr(brain, "_acc", None) or not brain._acc.pending():
        brain._acc_trace_id = ""


def _confirm_ui_paints(widget_id: str) -> bool:
    """Whether an irreversible-action confirmation on this widget should paint the card's visual Sí/No overlay.

    Default True (unchanged behavior everywhere). A widget can opt out via `"confirm_ui": false` in its
    `manifest.json` (2026-08-15, operator request: "el widget de agenda se maneja solo con la voz" — no
    button/overlay for it). Voice resolution (`classify_reply`) never depended on the overlay existing, so
    turning it off changes NOTHING about how "sí"/"no" gets resolved — only whether a card gets a button."""
    try:
        from widgets import runtime as _wruntime
        man = _wruntime.get((widget_id or "").strip().lower())
        if man is not None:
            return bool(man.get("confirm_ui", True))
    except Exception:
        pass
    return True


def _resolve_pending_confirm(ok: bool) -> bool:
    """Resuelve la confirmación pendiente (cualquier widget). Si `ok`, EJECUTA lo confirmado: un BORRADO de widget
    (determinista, memoria incluida) o una DATA-OP irreversible (despacho por `apply_action`, NUNCA código).
    Devuelve True si había algo que resolver.

    Función de MÓDULO (no closure de `_run_inner`, V2-090 addenda 2026-08-15) precisamente para poder llamarla
    ANTES de que el turno haga ningún trabajo lento — ver el hueco real que arregla en el sitio donde se llama
    pronto, dentro de `_run_inner`: el backstop determinista viejo solo corría TRAS el streaming COMPLETO del
    modelo, y un turno cancelado por barge-in antes de llegar allí perdía el "sí" EN SILENCIO — la confirmación se
    quedaba pendiente para siempre y el widget nunca se tocaba (sesión real: «Sí, vacía la entera.» canceló por
    seguir hablando, el operador vio "confirmar" y la agenda no cambió)."""
    try:
        from voice.observer import emit
        from widgets import confirm as _confirm, lifecycle as _lifecycle
        p = _confirm.resolve("", ok)
        if p is None:
            return False
        # Observability (V2-090 addenda): esta respuesta nació en SU PROPIO turno (trace fresco) — antes de
        # ejecutar/cancelar, adopta el trace de la pregunta para que ask→respuesta→acción sean UN flujo, no dos.
        try:
            _ptid = str(p.get("trace_id") or "")
            if _ptid:
                from voice import trace as _trace4
                _trace4.adopt(_ptid)
        except Exception:
            pass
        if not ok:
            emit("brain", "↩️ acción cancelada", text=p.get("widget_id", ""), role="system")
        elif p.get("action") == "data" and isinstance(p.get("op"), dict) \
                and p["op"].get("action") == "connect_cluster":
            try:
                from connectors import meshkore as _mk
                _pl = p["op"].get("payload") or {}
                _spawn(_mk.dispatch_tag("cluster.connect", {"data": _pl}), "cluster")
                emit("brain", "🛰 conectando cluster MeshKore (confirmado)", text=_pl.get("name", ""),
                     role="system")
            except Exception:
                pass
        elif p.get("action") == "data" and isinstance(p.get("op"), dict):
            try:
                import widgets
                _spawn(widgets.dispatch_tag("widget.data", {"id": p["widget_id"], "data": p["op"]}),
                       "widget-data-confirmed")
                emit("brain", "✅ acción irreversible confirmada", role="system",
                     text=f"{p['widget_id']}:{p['op'].get('action')}")
            except Exception:
                pass
        elif p.get("action") == "delete":
            _spawn(_lifecycle.delete_widget(p["widget_id"], "flash"), "widget-delete")
            emit("brain", "🗑️ widget borrado (confirmado)", text=p["widget_id"], role="system")
        return True
    except Exception:
        return False


def _surface_is_empty(widget_id: str) -> bool:
    """¿La tarjeta que acabamos de abrir no tiene NADA que enseñar?

    Nace del incidente de la sesión 13:20:50: el operador pidió resultados de una búsqueda que nunca se hizo, el
    cerebro abrió una hoja en blanco y dijo «Aquí lo tienes». En el log no quedaba ni una pista de que la pantalla
    estaba vacía — había que estar mirando. Marcarlo en el evento `show_widget` convierte ese acuse falso en un dato
    consultable (y en algo que un test puede exigir). Genérico y sin catálogo de widgets: mira el estado GUARDADO,
    así que vale igual para resultados, mensajes o cualquier superficie futura. Fail-open a `False` (no afirmamos
    que esté vacía si no lo podemos saber).
    """
    try:
        from widgets import store
        data = store.load(widget_id) or {}
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    for v in data.values():
        if isinstance(v, (list, tuple, dict)) and len(v) > 0:
            return False
    return True


def _spawn(coro, label: str) -> None:
    task = asyncio.create_task(coro)
    _TAG_TASKS.add(task)
    task.add_done_callback(lambda t: _TAG_TASKS.discard(t))


@registry.register("nucleo")
def build(model: str = "") -> llm.LLM:
    return NucleoLLM()


class NucleoLLM(llm.LLM):
    def __init__(self) -> None:
        super().__init__()
        self._window: list[dict] = []      # ventana de diálogo corta del FlashBrain
        self._seeded = False               # ¿ya sembrada la ventana desde memoria? (circuito de corto plazo)
        self._directive = ""               # preferencia de estilo fijada esta sesión (set_style_directive)
        self._last_spoken = ""             # última frase que DIJO zaelar (anti-eco, FASE 2) — INCLUYE fillers
        self._last_spoke_at = 0.0          # cuándo la dijo (epoch s) → ventana de eco
        self._last_reply = ""              # última respuesta con CONTENIDO real (nunca un filler) — contexto
        #                                    de `attention.evaluate_content()` (ver el `send()` de más abajo)
        self._last_dataop = None           # (wid, action, payload, ts) última data-op EJECUTADA — guard anti
        #                                    context-bleed (round headless V2-038 #1: re-emisión cross-turno)
        self._utterance: dict = {"text": "", "at": 0.0}   # frase EN CURSO del operador (guarda de fragmentos, _extends)
        self._acc_trace_id: str = ""       # trace del flujo mientras el acumulador (V2-096) tiene trozos a medias
        self._chain_grace: tuple[str, float] = ("", 0.0)   # (trace, ts) de la última cadena RESUELTA (V2-116):
        #                                    sigue adoptable unos segundos para que el trozo siguiente de la
        #                                    misma frase no abra un flujo nuevo — ver `_begin_or_adopt_trace`
        self._escalated_trace_id: str = "" # trace que ACABA de publicar escalate.requested este turno (V2-113):
        #                                    bridges the sync race before dispatch.run_listener gets a scheduler
        #                                    turn to register/reject/dedup it — see `_flow_should_close`
        self._turn_tools: set = set()      # tools this turn actually RAN (V2-123): tells a turn that merely talked
        #                                    about the running task apart from one that started something else —
        #                                    see `_merge_target`. Reset per turn in `_run_inner`.
        self._acc_gen: int = 0             # accumulator chain generation (2026-08-15, see `_schedule_acc_nudge`):
        #                                    bumped every time a chain resolves or gets dropped, so a nudge
        #                                    scheduled for it and now stale doesn't fire late
        self._turn_count = 0                # turnos conversacionales completados esta sesión (INI-018 T6, demo cap)
        self._last_action = ""              # route/surface del turno anterior para referencias deícticas
        self._session_started_at = time.time()  # arranque de la sesión (INI-018 T6, demo TTL)

    @property
    def label(self) -> str:
        return "zaelar.nucleo"

    @property
    def model(self) -> str:
        return "nucleo-flash"

    def set_briefing(self, text: str) -> None:
        """Compat con el entrypoint (duo lo usa). En nucleo la memoria de arranque sale de `memory.state()` en el
        prompt cada turno, así que aquí no hace falta — se acepta y se ignora para no romper una llamada genérica."""
        return None

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS,
             parallel_tool_calls=None, tool_choice=None, extra_kwargs=None) -> llm.LLMStream:
        return NucleoLLMStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class NucleoLLMStream(llm.LLMStream):
    # ── UN TURNO QUE MUERE DEJA RASTRO (2026-08-10) ───────────────────────────────────────────────────────────────
    # Incidente real (sesión 13:20:50): el operador dictó una petición larga —ferry Dénia→Ibiza, fechas, medidas del
    # coche, 4 pasajeros— y su turno (T6) se quedó SIN RESPUESTA. 13 ms después entró el turno siguiente
    # («muéstrame los resultados») y LiveKit canceló T6 en pleno montaje del prompt. Dos daños, los dos invisibles:
    #   (a) el TEXTO se perdió — el `push_user` que conserva la frase del operador vivía SOLO en el `except` del
    #       stream, así que una cancelación ANTES de llegar al stream se llevaba los criterios por delante y el
    #       turno siguiente hablaba de «los resultados» sin saber de qué; y
    #   (b) no quedaba ni una línea en la observabilidad: el evento `prompt` salía y luego NADA. Mirando el log se
    #       veía la petición entrar y no salir, sin motivo — el mismo pecado que un micrófono encendido con el
    #       agente muerto (ver la regla «estado visible, no silencioso»).
    # Por eso el cuerpo del turno pasa a `_run_inner` y `_run` queda como ENVOLTURA: cualquier cancelación, en
    # cualquier fase, conserva la frase y deja su rastro con la FASE en la que murió. No cambia el camino feliz.
    async def _run(self) -> None:
        self._phase = "arranque"
        self._death_logged = False
        try:
            await self._run_inner()
        except asyncio.CancelledError:
            self._note_death("superado por otro turno")
            raise
        else:
            _maybe_close_flow(self._llm)

    def _superseded(self) -> bool:
        """True si ya llegó una versión MÁS LARGA de la misma frase que este turno está atendiendo — o sea, el
        operador seguía hablando y esto es un fragmento viejo. Ver `_extends` para el porqué de la señal."""
        mine = getattr(self, "_turn_text", "")
        if not mine:
            return False
        return _extends(mine, (getattr(self._llm, "_utterance", None) or {}).get("text", ""))

    def _note_death(self, reason: str) -> None:
        """Conserva la frase del operador y registra DÓNDE murió el turno. Idempotente: el `except` del stream ya
        emite su propia línea (con métricas de barge-in), así que marca la bandera y esta no duplica."""
        if getattr(self, "_death_logged", False):
            return
        self._death_logged = True
        try:
            from voice.observer import emit
        except Exception:
            return
        text = _last_user_text(self._chat_ctx)
        kept = False
        if text:
            # Cancelar la RESPUESTA no borra la FRASE (misma regla que el barge-in del stream, ahora en TODAS las
            # fases): sin esto, el turno siguiente llega al modelo sin el contexto que el operador acababa de dar.
            try:
                from nucleo.flash import dialog as _dialog
                _dialog.push_user(self._llm._window, text)
                del self._llm._window[:-_WINDOW_MAX]
                kept = True
            except Exception:
                pass
        emit("brain", "✂️ turno descartado — sin respuesta", text=text[:200], role="system",
             extra={"cat": "flash", "reason": reason, "phase": getattr(self, "_phase", "?"),
                    "text_kept": kept})

    async def _run_inner(self) -> None:
        brain: NucleoLLM = self._llm  # type: ignore[assignment]
        try:
            from voice.observer import emit
        except Exception:
            emit = lambda *a, **k: None

        text = _last_user_text(self._chat_ctx)
        if not text:
            emit("brain", "⚠️ Nucleo triggered but no user text in context")
            return

        # GATE DE ATENCIÓN (V2-015): el micro está SIEMPRE abierto — un turno que no va DIRIGIDO a zaelar no
        # produce acción ni respuesta (solo se registra como `ambient`, visible en /debug). El kickoff
        # ("I just connected") y el chat/paste (marcados `note_directed()` en agent.py) sí van dirigidos.
        from voice import attention
        first_turn = "I just connected" in text

        # TRAZABILIDAD (V2-044): cada frase del operador nace con un trace id — ANTES del gate, así los descartes
        # (ambient/eco/interrupción dura) también quedan encadenados a su frase y son evaluables. Todo lo que este
        # turno derive (tools, tags, rails, escaladas, memoria) hereda el id por ContextVar (create_task/to_thread).
        # Una continuación de la MISMA frase (V2-096 addenda, ver `_begin_or_adopt_trace`) ADOPTA el trace de la
        # cadena en vez de abrir uno nuevo por trozo.
        try:
            _begin_or_adopt_trace(brain, text, first_turn)
        except Exception:
            pass
        # What this turn ACTUALLY did, for the flow-merge decision at the end (V2-123, `_merge_target`). Lives on
        # `brain` because `_close_flow_now` only receives that object — same ownership (and same overlapping-turn
        # caveat under preemptive generation) as `_acc_trace_id`/`_escalated_trace_id` right next to it.
        brain._turn_tools = set()

        # T136 — interrupción DURA: "cierra los widgets / para / silencio" se atiende SIEMPRE (salta el gate)
        # y se ejecuta de forma DETERMINISTA, nunca enterrada en un turno gigante. Fue el bug real (el `close`
        # quedó fuera del recorte de un turno de 14k chars).
        if not first_turn:
            hard = attention.hard_interrupt(text)
            if hard:
                # V2-038 precedencia (§v3·M): un STOP corto ("para eso", "para el widget") con Brain Workers VIVOS y
                # referencia a TRABAJO NO es callar el TTS — es PARAR UN WORKER. No retornamos aquí: el turno sigue y
                # el modelo llama stop_worker (con backstop determinista post-stream). Sin workers, es stop de TTS.
                _worker_stop = False
                if hard == "stop":
                    try:
                        from nucleo import dispatch as _d0
                        from nucleo.flash import router as _router0
                        _worker_stop = _d0.has_active() and _router0.looks_like_stop_work(text)
                    except Exception:
                        _worker_stop = False
                    # MÚSICA (bug 2026-07-16): con música SONANDO, "para / para la música" PARA la música — no solo
                    # calla el TTS. El barge-in de LiveKit corta la VOZ de zaelar, NO el stream de música (widget/
                    # Spotify) → sin esto había que decirlo dos veces. Determinista, off-loop; el run vivo del rail
                    # `music.playing`/`music.search` indica que suena/se busca (µs, en RAM). Precedencia: parar un
                    # WORKER manda (si aplica); si no, parar la música.
                    if not _worker_stop:
                        try:
                            from nucleo import rails as _rails0
                            if _rails0.get("music.playing") or _rails0.get("music.search"):
                                from connectors import music as _music0
                                await asyncio.to_thread(_music0.control, "stop")
                                _rails0.resolve("music.playing")
                                _rails0.resolve("music.search")
                                emit("music", "🎵 stop (interrupción dura · música viva)", text=text[:80],
                                     role="system", extra={"reason": "hard_interrupt"})
                        except Exception:
                            pass
                if not _worker_stop:
                    emit("ambient", "✋ interrupción dura atendida", text=text[:160], role="user",
                         extra={"cmd": hard, "reason": "hard_interrupt"})
                    if hard == "close":
                        emit("widget", "close", extra={"src": "flash"})   # cerrar TODOS los widgets, ya
                    _release_acc_trace_if_fresh(brain)          # ver docstring — este turno no llega a offer()
                    return                                   # 'stop' → el barge-in ya cortó el TTS; no respondemos

        # SUPRESIÓN DE ECO (FASE 2, 2026-07-14): con el micro SIEMPRE abierto y sin AEC perfecto, el mic capta el
        # TTS de zaelar y el STT lo transcribe como si fuera el operador → zaelar "se responde a sí mismo" (las
        # respuestas ZOMBIE / la frase del tiempo re-emitida del test). Si el turno se PARECE MUCHO a lo que zaelar
        # ACABA de decir y cae dentro de la ventana de eco, lo descartamos (determinista, no depende del LLM).
        # Observabilidad: evento `ambient` con reason=echo → visible en /debug para medir cuánto eco hay.
        # V2-038 §v3·N: si un Brain Worker ESPERA respuesta, el turno inmediato (a menudo monosilábico: "enduro")
        # queda EXENTO de la supresión de eco — si no, "sí"/una palabra contenida en lo último dicho se descartaría
        # y la respuesta al worker moriría.
        _ask_waiting = False
        if not first_turn:
            try:
                from nucleo import worker_api as _wapi0
                _ask_waiting = _wapi0.has_pending_ask()
            except Exception:
                _ask_waiting = False
        if not first_turn and brain._last_spoken and not _ask_waiting:
            _echo_win = float(os.getenv("ZAELAR_ECHO_WINDOW_S", "12"))
            _gap = time.time() - brain._last_spoke_at
            if _gap < _echo_win:
                try:
                    from nucleo.flash import dialog as _dlg
                    _is_echo = _dlg.similar(text, brain._last_spoken, thr=0.82)
                except Exception:
                    _is_echo = False
                if _is_echo:
                    emit("ambient", "🔇 eco descartado (zaelar se oyó a sí mismo)", text=text[:160], role="user",
                         extra={"reason": "echo", "gap_s": round(_gap, 1), "cat": "flash"})
                    _release_acc_trace_if_fresh(brain)          # ver docstring — este turno no llega a offer()
                    return

        # T134 — un turno no dirigido no se atiende (ni siquiera drena notas: se preservan para el próximo).
        # El kickoff (saludo de zaelar) NO abre la ventana a propósito: es zaelar quien habla, no el operador
        # dirigiéndose a él — así, si la sesión arranca en mitad de una reunión, no hay un hueco inicial en el
        # que la voz ambiente se cuele como dirigida y auto-extienda la ventana. El operador abre la conversación
        # con la wake-word ("zaelar") y a partir de ahí la ventana la mantiene viva (o chat/paste, ya marcados).
        if not first_turn:
            # `evaluate_content()` (2026-08-16), no la `evaluate()` heurística pura: en modo `always` (el
            # default, micro siempre abierto) lo único que distingue "me hablas a mí" de "ruido de fondo" es la
            # NATURALEZA de la frase, así que le pregunta al modelo rápido — ver voice/attention.py. `context`
            # es deliberadamente barato (una frase, no la ventana entera): solo hace falta saber "qué estábamos
            # haciendo", no reconstruir el diálogo completo para esto. `_last_reply`, NUNCA `_last_spoken`: este
            # último incluye fillers ("Pues…", "Mmm…") que no llevan tema — pasarlo aquí dejaba al juez sin
            # contexto justo tras cada relleno, y una pregunta de seguimiento real se leía como ruido ambiente.
            verdict = await attention.evaluate_content(text, context=brain._last_reply)
            if not verdict.directed:
                emit("ambient", "🙉 ambiente — no dirigido a zaelar", text=text[:200], role="user",
                     extra={"mode": attention.mode(), "reason": verdict.reason})
                _release_acc_trace_if_fresh(brain)              # ver docstring — este turno no llega a offer()
                return
            attention.note_directed()   # refresca la ventana de conversación activa

        # GUARDA DE FRAGMENTOS (2026-08-10). La frase de este turno queda registrada como la utterance EN CURSO. Si
        # mientras trabajamos llega una versión MÁS LARGA de la misma frase (el operador seguía hablando), este turno
        # es un fragmento viejo y hay que abandonarlo ANTES de gastar modelo o —sobre todo— de disparar una tool.
        # Incidente de la sesión 13:20:50: una sola petición de ferry se partió en 8 transcripciones finales y cada
        # trozo abrió su propio turno; uno de ellos («…de Denia a») llegó a HABLAR, preguntando por el destino que el
        # operador estaba diciendo en ese momento. Un fragmento no debe poder abrir widgets ni lanzar un worker.
        if not first_turn:
            brain._utterance = {"text": text, "at": time.time()}
            self._turn_text = text

        # ACUMULADOR DE FRASE PARTIDA (V2-096). Hermano de la guarda de arriba, para el caso que ella NO cubre: la
        # guarda mata un fragmento cuando ya llegó su continuación; esto decide qué hacer cuando la continuación
        # AÚN NO ha llegado. Antes se actuaba sobre el trozo.
        #
        # V2-095 lo intentaba RETRASANDO el turno, y eso es un tiempo fijo: medido sobre 372 pausas reales, el
        # `max_delay` de 2,2 s solo cubría el 48,7% (p50 2,3 s · p90 4,9 s · max 19,5 s). Acumular saca el reloj de
        # la ecuación — la pausa puede durar lo que quiera, porque lo que se juzga son los trozos JUNTOS.
        #
        # Va AQUÍ, y el sitio es la mitad del arreglo: por delante ya pasaron la interrupción DURA (una orden de
        # parar nunca se retiene) y el gate de atención; por detrás viene `ingest_utterance`, así que un trozo a
        # medias tampoco entra en la MEMORIA. Un fragmento no habla, no actúa y no se recuerda.
        if not first_turn:
            from nucleo.flash import accumulator as _acc
            if getattr(brain, "_acc", None) is None:
                brain._acc = _acc.Accumulator()
            _n_before = len(brain._acc.fragments)
            _action, _merged, _why, _dropped = await brain._acc.offer(text)

            # BUG FIX (2026-08-15, session d4b2bc35): a stale chain that got silently discarded (gap > MAX_GAP_S)
            # used to only ever surface — muted, in `extra`, never spoken — when the CALL AFTER the drop happened
            # to land on "act". The far more common case is that the fragment causing the drop is itself
            # incomplete and falls to "hold" a few lines below, which carried no drop info at all: the operator's
            # words vanished with zero trace anywhere, timeline included. `Accumulator.offer()` now reports
            # `_dropped` on EITHER branch, so this fires every time regardless of what this call goes on to do.
            _speak_drop, _fresh_chain = _acc_notice_plan(_action, _dropped, _n_before)
            if _dropped:
                emit("brain", "🕳️ frase anterior descartada por el hueco", text=_dropped[:200], role="system",
                     extra={"cat": "flash", "gap_s": _acc.MAX_GAP_S})
            if _speak_drop:
                _spawn(_speak_acc_drop(_dropped), "acc_drop_notice")

            if _action == "hold":
                # Callar es la conducta CORRECTA aquí, no un efecto colateral que haya que compensar con un
                # temporizador. Norma del operador, con su propio ejemplo: «si digo "oye, ¿qué tal? ahora vamos
                # a…" y me paro ahí, obviamente esa frase no genera absolutamente nada NI DEBE GENERARLO».
                # Por eso no hay flush por tiempo: un fragmento abandonado se queda sin respuesta a propósito, y
                # las válvulas del acumulador (hueco máximo, nº de trozos, tamaño) son solo para que el buffer no
                # crezca ni contamine una petición posterior que no tiene nada que ver.
                # Y se VE: el trozo retenido y el motivo salen al timeline (⏸), que es la diferencia entre «está
                # esperando a que acabes» y «se ha quedado colgado».
                # 2026-08-15: and if the wait drags on, it's now also HEARD (`_schedule_acc_nudge` below) — the
                # real session's 64s gap had neither signal.
                if _fresh_chain:
                    brain._acc_gen += 1
                    _schedule_acc_nudge(brain, brain._acc_gen)
                emit("brain", "⏸ frase a medias — espero a que termines", text=text[:200], role="system",
                     extra={"cat": "flash", "why": _why, "trozos": len(brain._acc.fragments),
                            "acumulado": brain._acc.text()[:300]})
                return

            if _action == "ask":
                # V2-102: layer 2 (the LLM judge) says this looks actionable but is missing something concrete
                # enough that a real assistant would ASK rather than guess or wait in silence. `_why` carries the
                # question text here (repurposed — see `Accumulator.offer`'s docstring). Speaks it exactly like
                # the drop-notice/nudge do (`voice.proactive.speaker()`, never over the operator mid-sentence)
                # and RETURNS — the question IS this turn's response, no FlashBrain dispatch, no memory ingest.
                brain._acc_gen += 1
                brain._acc_trace_id = ""
                emit("brain", "❓ pidiendo aclaración", text=_why[:200], role="system",
                     extra={"cat": "flash", "acumulado": _merged[:300]})
                try:
                    from voice import proactive
                    speak = proactive.speaker()
                    if speak is not None and not proactive.user_speaking():
                        r = speak(_why)
                        if asyncio.iscoroutine(r):
                            await r
                except Exception:
                    pass
                return

            if _n_before and not _dropped:
                emit("brain", "🧩 frase completada en varios tiempos", text=_merged[:300], role="user",
                     extra={"cat": "flash", "trozos": _n_before + 1, "motivo": _why})
            brain._acc_gen += 1          # cadena resuelta — un aviso pendiente para ella queda obsoleto
            _resolve_acc_chain(brain)    # el trace pasa a GRACIA, no se tira (V2-116)
            text = _merged

        # V2-013: el "corazón" (agente de memoria) clasifica en background lo que dijo el operador y, si es
        # perfil (nombre/ubicación/trato/hardware/coche) o deseo durable, lo lleva a `state`/`long` sin
        # bloquear el turno. Fire-and-forget: regex µs + escritura por la cola async → cero coste en TTFB.
        try:
            from nucleo import memory_agent as _mem_agent
            asyncio.create_task(_mem_agent.ingest_utterance(text, role="operator"))
        except Exception:
            pass

        # CIRCUITO DE CORTO PLAZO (B, 2026-07-14): la ventana de diálogo vive en RAM y arranca VACÍA en cada
        # instancia del brain (reinicio/reconexión) → el FlashBrain perdía "de qué hablábamos". La SEMBRAMOS una
        # sola vez desde el buffer conversacional persistente (`memory.recent_window`, lectura directa µs, sin LLM
        # ni retriever) → el PRIMER turno tras reconectar ya está situado. Cero coste de tokens en régimen normal
        # (la ventana ya está capada a _WINDOW_MAX). Best-effort.
        if not brain._seeded:
            brain._seeded = True
            if not brain._window:
                try:
                    from memory import api as _memory
                    _seed = _memory.recent_window(limit=int(os.getenv("ZAELAR_WINDOW_SEED", "6")))
                    if _seed:
                        brain._window[:0] = _seed
                        emit("brain", "🌱 ventana sembrada desde memoria", role="system",
                             extra={"turns": len(_seed)})
                except Exception:
                    pass

        # LATENCY GUARD + T135: acota lo que ve la capa rápida (turnos-parrafada) PRESERVANDO un comando
        # explícito — nunca truncar a ciegas los últimos N chars (así se perdía el "cierra los widgets").
        _max_in = int(os.getenv("ZAELAR_FAST_MAX_INPUT", "1600"))
        text, _clipped = attention.clamp_input(text, _max_in)
        if _clipped:
            emit("brain", "✂️ input recortado (comando preservado)", text=f"→{_max_in} chars")
        if first_turn:
            text = ("Es el primer turno. Salúdame en 1-2 frases, cálido y breve; si por tu MEMORIA ya sabes mi "
                    "nombre, úsalo y NO preguntes quién soy; si no, preséntate en una línea y pregúntame el nombre. "
                    "Luego para.")

        # V2-1xx: la petición REAL del operador, capturada ANTES de que se le antepongan notas del sistema —
        # el recall semántico (más abajo) tiene que buscar por ESTO, nunca por el turno completo. Confirmado en
        # vivo (auditoría 2026-08-17): una nota de Telegram pegada delante ("...Near our tp1 we take out
        # 20-30%...") dominaba el vector de la query y enterraba los hechos de familia/coche que SÍ existían en
        # el largo plazo — el modelo respondió sin ningún dato delante y rellenó el hueco inventando uno.
        operator_text = text

        # Notas del sistema (resultados async, subidas de fichero…) — se anteponen al turno para que el
        # FlashBrain las vea como CONTEXTO de esta respuesta; NUNCA como parte de lo que el operador pidió.
        try:
            from voice import brain_notes
            notes = brain_notes.drain()
        except Exception:
            notes = []
        if notes:
            for n in notes:
                emit("brain", "📩 system note → FlashBrain", text=n, role="system")
            text = "\n".join(notes) + "\n\n" + text

        from nucleo.flash import dialog as _dialog
        from nucleo.flash import escalate as _escalate_mod
        from nucleo.flash import frontend as _frontend
        from nucleo.flash.fast_client import FastClient, spec_from_config
        from nucleo.flash.prompt import build_flash_system
        from nucleo.flash import router as _router

        # EL SPEC SE RESUELVE POR TURNO, contra la cadena de relevo (V2-094). Antes se cogía el titular fijo de la
        # config, así que un proveedor lento o sin cuota se repetía igual turno tras turno: no había a dónde ir.
        # `pick()` es O(1) contra un dict de cooldowns en memoria — no reprueba la cadena en cada turno — y devuelve
        # el titular mientras esté sano, que es el 99% del tiempo. En self-host la cadena es solo el titular (sin
        # relevo por defecto), así que esto es idéntico al comportamiento anterior. Fail-open duro: cualquier
        # problema resolviendo la cadena y se usa la config, como siempre.
        spec = spec_from_config()
        try:
            from nucleo.flash import provider_chain as _pchain0
            _tier = _pchain0.pick(_pchain0.ROLE_VOICE)
            if _tier and _tier.get("name") not in ("", "titular"):
                spec = _pchain0.spec_for(_tier)
        except Exception as _e_pc:  # noqa: BLE001
            logger.warning(f"provider_chain(voice) no resolvió; sigo con la config: {_e_pc!r}")
        emit("brain", "⚡ Nucleo(flash): prompt", text=text, role="user",
             extra={"engine": spec.provider, "model": spec.model})

        self._phase = "montando el prompt"
        timings: dict = {}
        _t_prompt = time.time()
        # RECALL semántico BAJO DEMANDA y FUERA del event loop (T115+T116): `compose_recall` hace embeddings HTTP
        # a Ollama — meterlo en el loop, cada turno, era la regresión de V2-004. Ahora (a) solo se dispara cuando
        # el turno PIDE recordar algo (`needs_recall`, heurística ligera) — la charla normal ni toca el retriever,
        # así que cierra en ~1s; y (b) cuando se dispara, corre en un hilo (`to_thread`) → el event loop nunca se
        # para. El bloque de estado (nombre/trato/…) sale SIEMPRE del caché (T114); el resto del prompt es de ms.
        from nucleo.flash import prompt as _prompt_mod
        recall_block = ""
        recall_ids: list = []
        timings["recall_fired"] = _prompt_mod.needs_recall(operator_text)
        if timings["recall_fired"]:
            # TIME-BOX del recall (regla dura "nunca lento"): el retriever suele cerrar en ~0.4-1.5s, pero en el
            # turno vivo puede dispararse a 4s+ (recarga del modelo de embedding tras un desalojo por el CORAZÓN
            # qwen2.5:14b, o contención de Metal con STT/TTS). El recall está en el CAMINO CRÍTICO del turno (su
            # bloque alimenta el prompt), así que un pico lo paga el usuario en tiempo real. Lo acotamos: si no
            # cierra dentro del presupuesto, el turno SIGUE SIN el bloque durable — el ESTADO (nombre/misión/
            # conversación reciente) YA va en el prompt desde el caché (µs), así que la degradación es suave, no
            # amnesia total. Presupuesto configurable (ZAELAR_RECALL_BUDGET_MS, def 800). 2026-07-13: bajado de
            # 2000→800 tras medir en la sesión manual que el embedding en frío (desalojo por el CORAZÓN) hacía
            # timeout SIEMPRE a 2000ms → +2s tirados por turno. Con 800ms, caliente entra (round-trip ~50-150ms) y
            # en frío corta rápido (pierde 0.8s, no 2s). El fix DE RAÍZ (residencia de embeddinggemma) va por el
            # workflow de memoria.
            _budget = float(os.getenv("ZAELAR_RECALL_BUDGET_MS", "800")) / 1000.0
            try:
                recall_block, recall_ids = await asyncio.wait_for(
                    asyncio.to_thread(_prompt_mod.compose_recall, operator_text, timings), timeout=_budget)
            except asyncio.TimeoutError:
                timings["recall_timeout"] = True
                logger.info(f"nucleo recall over budget ({_budget:.1f}s) — turno sigue sin recall durable")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"nucleo recall skipped (voice continues): {e}")
        # 2º PASE DE CORTO PLAZO (C, 2026-07-14): si el turno referencia la interacción RECIENTE ("de qué
        # hablábamos", "lo que te dije antes", "repite eso"), inyectamos el buffer conversacional AMPLIADO
        # (verbatim, más turnos que la ventana normal). Lectura DIRECTA µs, pero la corremos igualmente en un
        # hilo por consistencia con V2-011 (nunca I/O de memoria en el event loop). El prompt por defecto NO lo
        # lleva → cero tokens extra en charla normal; solo se carga bajo demanda.
        recent_block = ""
        timings["recent_fired"] = _prompt_mod.needs_recent(text)
        if timings["recent_fired"]:
            try:
                recent_block = await asyncio.wait_for(
                    asyncio.to_thread(_prompt_mod.compose_recent_block), timeout=0.5)
            except Exception:
                recent_block = ""
        # `turn_text` (V2-085): la frase del operador entra en el build para que la SELECCIÓN PROGRESIVA de widgets
        # promocione al top-K el que él nombra. NO clasifica la intención (invariante: sin tablas de verbos), solo
        # recupera candidatos — así el bloque de widgets es O(K) aunque el catálogo tenga miles.
        system, _used_ids = build_flash_system(
            directive=brain._directive, recall_block=recall_block, recent_block=recent_block, timings=timings,
            turn_text=text)
        # BREAK-LOOP (V2-032): si el cerebro llevaba ≥2 respuestas casi idénticas, añade una instrucción que le
        # OBLIGA a cambiar de estrategia — corta el bucle de repetición/negación (bloqueante #1 del informe).
        _nudge = _dialog.loop_nudge(brain._window)
        if _nudge:
            system += _nudge
            emit("brain", "🔁 break-loop: nudge anti-repetición inyectado", role="system")
        timings["prompt_ms"] = round((time.time() - _t_prompt) * 1000, 1)
        emit("timing", "⏱ turn breakdown (prompt build)", extra=timings)
        self._phase = "eligiendo qué hacer"

        # OBSERVABILIDAD DE MEMORIA (V2-014 Task 2): una fila por CAPA leída este turno, con módulo=memory,
        # capa (state/short/slow), la petición y el resultado (nº de tarjetas/chars) + su tiempo. Alimenta la
        # columna ◷ de logs; las tarjetas del mapa las sigue iluminando el pulso `memory.query`/`memory.updated`.
        try:
            from nucleo.flash import memory_cache as _mc
            ms = _mc.stats()
            emit("memory", "estado", role="system",
                 text=(f"perfil del operador → {ms.get('state_fields', 0)} campos" if ms.get("has_state")
                       else "perfil del operador → vacío (sin poblar)"),
                 extra={"layer": "state", "mem_ms": timings.get("mem_state_ms")})
            emit("memory", "corto", role="system",
                 text=f"working set entero → {ms.get('short_count', 0)} tarjetas · {ms.get('short_chars', 0)} chars",
                 extra={"layer": "short", "mem_ms": timings.get("mem_state_ms")})
            if timings.get("recall_fired"):
                emit("memory", "recall", role="system",
                     text=f"«{text[:60]}» → {len(recall_ids)} tarjetas del largo plazo",
                     extra={"layer": "slow", "mem_ms": timings.get("mem_query_ms")})
        except Exception:
            pass
        messages = [{"role": "system", "content": system}]
        messages += _dialog.prune_window(brain._window)[-_WINDOW_MAX:]   # colapsa turnos gemelos (anti-degeneración)
        messages.append({"role": "user", "content": text})

        from voice import speech
        from voice.tag_protocol import strip_tags

        t0 = time.time()
        # FASE 3: foto de CONTENCIÓN al arrancar el LLM del turno (¿estaba el CORAZÓN/embed/rerank ocupando la
        # máquina?). Se adjunta al `reply` → correlacionamos si el TTFT sube bajo carga local. TTFT es CLOUD, así
        # que si sube con carga LOCAL activa, es contención de CPU/event-loop, no de GPU.
        try:
            from voice import observer as _obs
            _busy_at_start = _obs.busy_snapshot()
        except Exception:
            _busy_at_start = {}
        buf, spoken, first_ms = "", [], None
        # `v` = la escalada PRINCIPAL del turno (la primera); `more` = las ADICIONALES cuando el operador encarga
        # varias tareas DISTINTAS de una sentada (V2-118, medido 2026-08-18). Antes solo existía `v` con un
        # `if is None`, así que de «hazme un informe, búscame un monitor y móntame un widget» arrancaba UNA tarea
        # y las otras dos se descartaban en silencio — mientras el turno DECÍA que las tres iban en marcha. El
        # arnés lo midió por el registro real (`/api/tasks`), no por el transcript: máximo simultáneo 1.
        # Sigue habiendo una principal a propósito: todo el resto del turno (guards de show, backstops, dedup,
        # ack «nunca mudo») razona sobre UNA decisión, y esos caminos no cambian. Las adicionales solo se suman
        # al final, cuando ya se sabe que el turno escaló de verdad.
        escalate_req: dict = {"v": None, "more": [], "surface": {}}   # V2-227: superficie declarada POR petición
        search_req = {"v": None}
        recall_req = {"v": None}         # V2-056: el modelo pidió RECORDAR (tool recall) — se resuelve tras el stream
        reveal_req = {"v": None}         # V2-060: el operador pidió un SECRETO (reveal_secret) — valor OUT-OF-BAND
        music_req = {"v": None, "followup": None}  # V2-041: {'query','action'}; 'followup' = 2ª acción de CONTROL
                                          # (volumen/pausa) pedida EN EL MISMO turno que un play/queue (bug real
                                          # 2026-07-23: "pon música de Queen y súbele el volumen" decía las DOS
                                          # cosas pero solo ejecutaba la 1ª — la 2ª se tiraba en silencio)
        style_fired = {"v": False}       # V2-046 A1: se fijó/retiró una user rule → ack si el modelo no habló
        acted = {"widget": False}
        confirm_state = {"handled": False}
        clarify = {"msg": None}          # V2-026: pregunta a decir si una referencia a un item no se resolvió
        data_done = {"v": False}         # V2-026: se despachó una data-op FAST → ack hablado si el modelo no habló
        worker_acted = {"v": None}       # V2-038: 'inject'|'stop'|'answer' si se dirigió a un Brain Worker vivo
        cron_seen = {"v": False}         # V2-146: el turno YA pidió un cron → el backstop de aviso no duplica
        _shown_ids: set = set()          # ids ya mostrados ESTE turno → dedup de [[show]] duplicado
        # ¿había una confirmación de borrado en el aire al empezar el turno? Solo entonces interpretamos un
        # "sí/no" suelto como respuesta a ELLA (red determinista, por si el modelo no llama a la tool).
        try:
            from widgets import confirm as _confirm_mod
            had_pending_confirm = bool(_confirm_mod.pending())
        except Exception:
            had_pending_confirm = False

        def send(txt: str):
            nonlocal first_ms
            if not txt:
                return
            if first_ms is None:
                first_ms = round((time.time() - t0) * 1000)
            spoken.append(txt)
            # ANTI-ECO (FASE 2): recuerda lo ÚLTIMO que zaelar dice + cuándo, para descartar el eco que el mic
            # recaptura como turno del operador. Se actualiza en CADA salida de voz (respuesta, filler, degradado).
            brain._last_spoken = "".join(spoken)
            brain._last_spoke_at = time.time()
            # `_last_reply` es el mismo texto pero SOLO pasa por aquí (nunca por el camino del filler, ver
            # `_lead_in_filler` más abajo) — es el contexto que `evaluate_content()` necesita para juzgar si el
            # siguiente turno va dirigido. Un filler ("Pues…", "Mmm…") no lleva ningún tema: si se dejaba pisar
            # `_last_spoken` con él, el juez recibía "Se estaba haciendo: Pues…" justo tras una pregunta real y
            # clasificaba el siguiente turno del operador como ambiente (bug real, sesión 2026-08-17: 4 preguntas
            # de seguimiento — incluida la queja «te acabo de hacer preguntas ahora» — descartadas de seguido,
            # cada una justo tras un filler).
            brain._last_reply = "".join(spoken)
            self._event_ch.send_nowait(
                ChatChunk(id=utils.shortuuid(), delta=ChoiceDelta(role="assistant", content=txt))
            )

        # CONFIRMACIÓN PENDIENTE — resuelta YA, antes de CUALQUIER trabajo lento (V2-090 addenda, 2026-08-15).
        # El backstop determinista de más abajo (RED DETERMINISTA V2-017, `classify_reply` + `_resolve_confirm`)
        # solo corre TRAS el streaming COMPLETO del modelo — cientos de líneas y varios segundos de por medio. Si
        # el operador sigue hablando, este turno se cancela por barge-in (como CUALQUIER turno) antes de llegar
        # allí, y el "sí" se pierde EN SILENCIO: la confirmación se queda pendiente para siempre y el widget nunca
        # se toca. Sesión real que lo demuestra: «Sí, vacía la entera.» se canceló por barge-in antes de resolver
        # nada; el operador vio "confirmar" y la agenda no cambió — no era un fallo de `apply_action` (que SÍ
        # marca los datos), era que la confirmación jamás llegó a ejecutarse. Un sí/no CLARO se resuelve AQUÍ,
        # determinista y ANTES de llamar al modelo — mismo principio que `attention.hard_interrupt`: lo
        # irreversible no puede depender de que el turno sobreviva entero. Ambiguo (`classify_reply` → None) cae
        # al backstop de siempre, que sigue con el modelo por si aporta más contexto.
        if not first_turn and had_pending_confirm:
            try:
                _verdict_early = _confirm_mod.classify_reply(text)
            except Exception:
                _verdict_early = None
            if _verdict_early:
                if _resolve_pending_confirm(_verdict_early == "yes"):
                    _ack_early = "Hecho." if _verdict_early == "yes" else "Vale, no toco nada."
                    send(speech.sanitize(_ack_early, drop_metadata=False))
                    return

        # V2-029: escaladas YA en vuelo al EMPEZAR el turno — para (a) deduplicar si el operador insiste con la
        # MISMA petición mientras el SlowBrain trabaja (no abrir tareas ni entregas duplicadas) y (b) variar el
        # filler ("sigo con ello" en vez de repetir el mismo "dame un momento" turno a turno).
        # V2-038 §v3·G: la FUENTE DE VERDAD de "qué hay en marcha" es el registro RAM de dispatch (no escalate._tasks).
        try:
            from nucleo import dispatch as _disp0
            _prev_pending = _disp0.pending_summaries()
        except Exception:
            try:
                _prev_pending = _escalate_mod.pending()
            except Exception:
                _prev_pending = []

        def _tag_emit(action: str, extra: dict) -> None:
            if action in ("deep",):
                # legacy Hermes escalation tag — el cerebro v2 no lo enseña; si aparece, se trata como escalada.
                if escalate_req["v"] is None:
                    escalate_req["v"] = (extra.get("request") or "").strip() or text
                return
            if action in ("json_leak_dropped",):
                from voice.tag_protocol import parse_json
                leaked = parse_json(extra.get("text") or "")
                if isinstance(leaked, dict) and isinstance(leaked.get("name"), str):
                    a = leaked.get("arguments")
                    if isinstance(a, str):
                        a = parse_json(a) or {}
                    _on_tool_call(leaked["name"], a if isinstance(a, dict) else {})
                elif isinstance(leaked, dict) and leaked.get("request"):
                    _on_tool_call("escalate_to_slowbrain", leaked)
                elif isinstance(leaked, dict) and leaked.get("directive"):
                    _on_tool_call("set_style_directive", leaked)
                else:
                    if escalate_req["v"] is None:
                        escalate_req["v"] = text
                return
            if action in ("unknown_tag_dropped",):
                logger.warning(f"unknown_tag_dropped: {(extra.get('text') or '')[:120]!r}")
                return
            if action == "widget.data":
                # Camino de RESERVA (V2-026): el tag inline sigue soportado, pero el camino PRINCIPAL de las
                # data-ops es la tool `widget_data` (function-calling, fiable). Ambos convergen en _apply_widget_data.
                data = extra.get("data") or {}
                _apply_widget_data(str(extra.get("id") or ""), str(data.get("action") or ""),
                                   data.get("payload") or {})
                return
            if action == "delete":
                # BORRAR es cosa del FlashBrain (rápido, determinista) PERO con confirmación (V2-017). Si el
                # modelo emitió el tag en vez de la tool, lo tratamos igual: abre la confirmación (overlay Sí/No
                # en la tarjeta), nunca borra directo.
                _request_delete_confirm(extra.get("id") or "", text)
                acted["widget"] = True
                return
            if action in ("create", "modify", "push"):
                # Boundary duro: crear/modificar/entregar datos a un widget → SlowBrain (escribe código), nunca el
                # Flash. Borrar NO entra aquí (es determinista y lo hace el Flash tras confirmar, arriba).
                logger.warning(f"nucleo(flash) intentó [[{action}]] — bloqueado, escalando")
                if escalate_req["v"] is None:
                    escalate_req["v"] = text
                return
            if action.startswith("cluster."):
                try:
                    from connectors import meshkore
                    _spawn(meshkore.dispatch_tag(action, extra), "cluster")
                except Exception:
                    pass
                return
            if action.startswith("architect."):
                try:
                    from connectors import architect
                    _spawn(architect.dispatch_tag(action, extra), "architect")
                except Exception:
                    pass
                return
            if action.startswith("msg."):
                try:
                    from connectors import messaging
                    _spawn(messaging.dispatch_tag(action, extra), "messaging")
                except Exception:
                    pass
                return
            if action in ("cron.create", "cron.cancel"):
                # Proactividad PROPIA (V2-005): re-cableado al scheduler del loop orquestador (NO al cron de
                # Hermes, que muere en V2-009). Persistido en memory.journal; lo dispara nucleo/loop.py.
                if action == "cron.create":
                    cron_seen["v"] = True          # V2-146: el backstop de abajo no duplica lo que ya se pidió
                try:
                    from nucleo import scheduler as _sched
                    d = extra.get("data") or {}
                    if action == "cron.create":
                        # V2-214 (impl PARALELA — cablear en AMBOS): las palabras del OPERADOR sobre su propia
                        # obligación se envuelven en un «AVÍSALE»; una orden ya dirigida al agente se deja igual.
                        from nucleo.flash import router_guards as _rg_cron
                        r = _sched.create(
                            _rg_cron.safe_reminder_prompt((d.get("prompt") or d.get("task") or "").strip()),
                            (d.get("schedule") or d.get("when") or "").strip(),
                            name=(d.get("name") or "").strip(), repeat=str(d.get("repeat") or ""))
                        emit("cron", "⏰ tarea programada" if r.get("ok") else "⚠️ schedule no reconocido",
                             text=r.get("display") or r.get("error") or "", role="system",
                             extra={"ok": bool(r.get("ok")), "op": action})
                    else:
                        _sched.cancel(extra.get("name") or d.get("name") or "")
                        emit("cron", "🗑️ tarea cancelada", role="system", extra={"ok": True, "op": action})
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"nucleo cron {action} failed: {e}")
                return
            # show / close / move → acción de canvas.
            if action == "show":
                contextual = _show_guard_target(text, brain._window, brain._last_action)
                if contextual:
                    extra = {**(extra or {}), "id": contextual}
            # GUARD anti-clutter (2026-07-12): el modelo tiende a emitir [[show:navegador]] al pedir una búsqueda,
            # abriendo el navegador VACÍO ("Nuevo navegador") ADEMÁS de la tarjeta de la tarea → dos/tres cajas de
            # navegador en pantalla. La búsqueda se ve en SU tarjeta (navegador::tN, la abre la tarea sola); el
            # navegador "a pelo" no es una superficie que el operador pida. Lo ignoramos (no rompe: la tarjeta manda).
            if action == "show" and str(extra.get("id") or "").strip().lower() == "navegador":
                emit("brain", "🚫 [[show:navegador]] ignorado (la tarjeta de la tarea es la superficie)", role="system")
                return
            # El modelo a veces emite [[show:X]] cuando el operador solo PREGUNTA por un widget ("¿por qué abriste
            # proyectos?") → abría un widget espurio en mitad de otra conversación (bug 2026-07-12). Una pregunta
            # META sobre una acción pasada NO es una orden de mostrar → ignora el show del modelo.
            if action == "show" and _is_meta_widget_question(_norm_nfkd(text)):
                emit("brain", "🚫 show ignorado (pregunta META sobre un widget, no una orden)",
                     text=str(extra.get("id") or ""), role="system")
                return
            # DEDUP de show por id en el MISMO turno (test post-P1/P2: el modelo emitía [[show:X]] dos veces →
            # doble evento). desktop.show ya es idempotente (reusa la tarjeta), pero no floodeamos el bus/SSE.
            if action == "show":
                _sid = str(extra.get("id") or "").strip().lower()
                if _sid and _sid in _shown_ids:
                    return
                _shown_ids.add(_sid)
            acted["widget"] = True
            if action == "close":
                acted["closed"] = True                   # el backstop de cierre corto no re-cierra (ver post-stream)
            extra["src"] = "flash"                       # V2-039: procedencia — esta orden viene del FlashBrain
            # REGISTRO DE ÓRDENES DE CANVAS (2026-08-09, petición del operador): el evento se lleva la FRASE que
            # lo provocó. Cuando se abre el widget EQUIVOCADO, la pregunta siempre es «¿de qué texto salió esto?»
            # — y hasta ahora había que reconstruirla saltando al evento `transcript` anterior o abriendo la vista
            # de trazas. Con el texto pegado al propio evento, la fila ya dice orden + objetivo + origen.
            emit("widget", action, text=(text or "").strip()[:160], extra=extra)

        def _request_delete_confirm(widget_id: str, turn_text: str) -> None:
            """FlashBrain pide BORRAR un widget → abre la CONFIRMACIÓN (overlay Sí/No en la tarjeta); el borrado
            real solo ocurre al confirmar. Resuelve el id flojito contra el catálogo (el modelo/STT no siempre
            dan el id exacto)."""
            try:
                from widgets import confirm as _confirm
                wid = (widget_id or "").strip().lower()
                if not wid or not _identify_is_widget(wid):
                    wid = _identify(widget_id or turn_text) or wid
                if not wid:
                    emit("brain", "⚠️ borrar: no identifiqué el widget", text=widget_id or turn_text[:80])
                    return
                # GUARD cerrar≠borrar (V2-045, invariante V2-017): el modelo a veces llama a delete_widget para
                # 'CIERRA el widget de X' (cerrar es reversible, borrar es PARA SIEMPRE). Si el turno dice cerrar y
                # NO dice borrar, es un CLOSE → no abrir confirmación de borrado. Determinista (no depende del LLM).
                from nucleo.flash import router as _router
                if _router.looks_like_close(turn_text):
                    _t = _close_target(wid)
                    if _t["ask"]:                       # V2-259 F3: varias tarjetas de esa pieza → se PREGUNTA
                        clarify["msg"] = _t["ask"]
                        emit("brain", "❓ cerrar: varias tarjetas abiertas", text=wid, role="system",
                             extra={"options": _t["options"]})
                        return
                    emit("widget", "close", extra={"id": _t["id"] or wid, "src": "flash"})
                    emit("brain", "🙈 cerrar (no borrar) — guard cerrar≠borrar", text=wid, role="system")
                    acted["widget"] = True
                    acted["closed"] = True
                    return
                _confirm.request("delete", wid, "¿Seguro que quieres que borre este widget?",
                                  notify_ui=_confirm_ui_paints(wid))
                confirm_state["opened"] = f"¿Seguro que quieres que borre el widget «{wid}»?"
                emit("brain", "🗑️ confirmación de borrado pedida", text=wid, role="system")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"delete confirm request falló: {e}")

        def _request_data_confirm(widget_id: str, action_name: str, payload: dict) -> None:
            """El FlashBrain quiere ejecutar una data-op IRREVERSIBLE (`confirm:true` en el manifest, V2-025) →
            abre la CONFIRMACIÓN (overlay Sí/No en la tarjeta) guardando la MUTACIÓN; solo al decir "sí" se
            despacha por `apply_action` — jamás se escala a código. Espejo de `_request_delete_confirm`."""
            try:
                from widgets import confirm as _confirm
                wid = (widget_id or "").strip().lower()
                if not wid:
                    return
                # COPY HUMANO (2026-07-15): antes el overlay decía «¿Confirmas «drop_project»?» — jerga interna que
                # el operador leyó como "borra el widget entero". La confirmación debe exponer el ALCANCE REAL en
                # lenguaje natural (qué HACE la acción + sobre QUÉ item), leído del manifest, para que el operador
                # vea si es más de lo que pidió (aquí: un PROYECTO entero, no la tarea que nombró). Genérico.
                q = _human_confirm_question(wid, (action_name or "").strip(), payload or {})
                _confirm.request("data", wid, q,
                                 op={"action": (action_name or "").strip(), "payload": payload or {}},
                                 notify_ui=_confirm_ui_paints(wid))
                confirm_state["opened"] = q
                emit("brain", "⚠️ confirmación de acción irreversible pedida", text=f"{wid}:{action_name}",
                     role="system")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"data confirm request falló: {e}")

        def _request_cluster_confirm(name: str, cluster_id: str, token: str, handle: str | None,
                                     perms: dict | None = None, vis: str = "") -> None:
            """V2-064, bug 2026-07-23: la sola DESCRIPCIÓN de la tool ('solo si el operador te lo pide') NO bastó —
            un bloque de texto pegado que se limitaba a MENCIONAR un cluster_id/token (sin que el operador pidiera
            nada aparte) hizo que el modelo llamara a `connect_cluster` igual, y encima confabuló "ya estoy
            conectado". Abrir un socket real a un cluster desconocido no puede depender de que el modelo pequeño
            distinga una orden de un texto que solo la menciona — así que, como con borrar un widget o una data-op
            irreversible, se pide confirmación DETERMINISTA antes de tocar la red. Sin un «sí» explícito del
            operador, nada se conecta.

            V2-086: el Sí/No ya NO vive en una tarjeta del canvas (el widget `cluster-registro` se retiró: la red
            es infraestructura del sistema, no un widget de usuario). Ahora se pinta en la pestaña NATIVA
            «Clusters» del ChatWall, que además es donde el operador ve el resultado. Esto arregla de paso un
            agujero real: la confirmación por BOTÓN nunca funcionó para conectar — `/widgets/{id}/confirm` solo
            sabía resolver borrados, así que el único camino que cerraba el círculo era decir «sí» por voz."""
            try:
                from widgets import confirm as _confirm
                q = (f"¿Conectar al cluster MeshKore «{name}» (cluster_id {cluster_id[:10]}…)? Solo si tú me lo "
                     f"acabas de pedir — no por algo que hayas pegado o reenviado.")
                _payload = {"name": name, "cluster_id": cluster_id, "token": token, "handle": handle}
                if vis:
                    _payload["vis"] = vis              # V2-086: cluster PÚBLICO (sin token) → viaja al connect
                if perms:
                    _payload["perms"] = perms          # V2-076: la concesión viaja con la conexión → store.set_perms
                _confirm.request("data", _confirm.NATIVE_CLUSTERS, q,
                                 op={"action": "connect_cluster", "payload": _payload})
                confirm_state["opened"] = q
                emit("brain", "🛰 confirmación de conexión a cluster pedida", text=name, role="system")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"cluster confirm request falló: {e}")

        def _resolve_confirm(ok: bool) -> bool:
            """Wrapper de turno sobre `_resolve_pending_confirm` (función de módulo, V2-090 addenda): añade el
            bookkeeping de ESTE turno (`acted["widget"]`) que la versión de módulo no puede conocer. La lógica de
            ejecución vive una sola vez, en `_resolve_pending_confirm` — este turno y el chequeo TEMPRANO de más
            arriba (antes del streaming) llaman a la MISMA función, nunca a una copia."""
            resolved = _resolve_pending_confirm(ok)
            if resolved:
                acted["widget"] = True
            return resolved

        def _apply_widget_data(wid: str, action_name: str, payload: dict) -> None:
            """Ejecuta una data-op según su modo (V2-025): FAST → despacha ya (apply_action / mailbox del owner);
            CONFIRM → abre confirmación con la mutación guardada (se ejecuta al decir "sí"); ESCALATE/None (acción
            no declarada o vía de escape) → escala al SlowBrain. Punto de convergencia de la tool y el tag."""
            from widgets import actions as _wactions
            wid = (wid or "").strip().lower()
            action_name = (action_name or "").strip()
            mode = _frontend.action_mode(wid, action_name)

            def _log_dataop(m: str) -> None:
                """REGISTRO DE ACCIONES DE WIDGET (2026-08-09, petición del operador). Hasta ahora una data-op
                («sube el volumen», «maximiza», «marca hecha la tarea») solo dejaba rastro cuando el widget
                GUARDABA (`widget/data` desde `widgets/store.py`), una fila genérica con el id y nada más — sin
                el nombre de la acción, sin quién la pidió y sin la frase. Y encima está clasificada como ruido,
                así que por defecto ni se ve. Aquí se registra la ORDEN en sí: qué acción, sobre qué widget, en
                qué modo (fast/confirm/escalate) y con la FRASE que la originó, para poder atar una acción
                equivocada con el texto exacto que la produjo. La fila del store se queda como está (es el efecto,
                no la orden)."""
                emit("widget", f"data:{action_name}", text=(text or "").strip()[:160],
                     extra={"id": wid, "action": action_name, "mode": m, "src": "flash"})

            if mode == _wactions.FAST:
                # GUARD anti context-bleed (round headless V2-038 #1): el modelo a veces RE-emite la data-op del
                # turno ANTERIOR junto a la acción de ESTE ("borra el reloj" arrastró el add_meeting del dentista
                # → cita DUPLICADA). Una mutación IDÉNTICA a la recién ejecutada (<120s), cuyo contenido el turno
                # actual NI MENCIONA, es arrastre → se ignora. Determinista: "apunta otra vez lo del dentista" SÍ
                # menciona el contenido → pasa.
                _last = brain._last_dataop
                if _last and _last[0] == wid and _last[1] == action_name and _last[2] == (payload or {}) \
                        and (time.time() - _last[3]) < 120 \
                        and _word_overlap(" ".join(str(v) for v in (payload or {}).values()), text) == 0:
                    emit("brain", "🛡️ data-op del turno anterior re-emitida — ignorada (context-bleed)",
                         text=f"{wid}:{action_name}", role="system")
                    return
                acted["widget"] = True
                data_done["v"] = True
                _log_dataop("fast")
                brain._last_dataop = (wid, action_name, dict(payload or {}), time.time())
                try:
                    from widgets import provenance as _prov
                    _prov.note(wid, "flash")             # V2-039: el cambio de datos que viene = ordenado por FlashBrain
                except Exception:
                    pass
                try:
                    import widgets
                    _spawn(widgets.dispatch_tag("widget.data",
                                                {"id": wid, "data": {"action": action_name, "payload": payload or {}}}),
                           "widget-data")
                except Exception:
                    pass
            elif mode == _wactions.CONFIRM:
                acted["widget"] = True
                _log_dataop("confirm")
                _request_data_confirm(wid, action_name, payload or {})
            else:
                logger.warning(f"nucleo(flash) widget.data {mode or 'no-declarada'} ({wid}:{action_name}) — escalando")
                _log_dataop("escalate")
                if escalate_req["v"] is None:
                    escalate_req["v"] = text

        def _handle_widget_data_tool(args: dict) -> None:
            """Tool `widget_data` (V2-026, camino PRINCIPAL de las data-ops): resuelve el widget y la REFERENCIA a
            item en lenguaje natural a un id REAL (nunca inventado), y despacha por `_apply_widget_data`. Si la
            referencia es ambigua o no existe, PREGUNTA en vez de actuar sobre el item equivocado."""
            from widgets import refs, runtime
            wid = (args.get("widget_id") or "").strip().lower()
            action_name = (args.get("action") or "").strip()
            ref = (args.get("item") or "").strip()
            payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
            if wid and runtime.get(wid) is None:            # id flojito del modelo → resuélvelo contra el catálogo
                wid = _identify(wid) or _identify(ref) or _identify(text) or wid
            if not wid or not action_name:
                return
            # GUARD (2026-07-16): un "abre/muéstrame el widget X" PURO (sin verbo de cambio) NUNCA debe ejecutar un
            # data-op — el modelo cuela una acción inventada ('unhide') o incluso ALUCINA un add_meeting ("abre la
            # agenda" → añadía "Reunión con Axa Seguros"). Se redirige a MOSTRAR la tarjeta (misma ruta que [[show]]).
            from nucleo.flash import router as _router
            if _router.is_pure_show_request(text) and runtime.get(wid) is not None:
                emit("brain", "🪟 'abrir/mostrar' puro → show (no data-op inventada)", text=wid, role="system")
                _tag_emit("show", {"id": wid})
                return
            # GUARD cerrar≠data-op (sesión 22:40 2026-07-16, espejo del guard cerrar≠borrar): «Vale, ciérralo» →
            # el modelo ejecutó `widget_data(youtube, mute)` (una data-op DECLARADA) en vez de emitir [[close]] →
            # el vídeo quedó MUTEADO, no cerrado, y el operador tuvo que corregir. Una orden CORTA que es
            # claramente CERRAR (verbo de cerrar, sin verbo de borrar, ≤5 palabras — sin más sustancia que el
            # pronombre/el widget) se redirige DETERMINISTA a la tag de canvas. Una frase larga con "cierra"
            # dentro ("cierra la sesión de spotify del widget") NO entra aquí (pasa a su data-op normal).
            if (_router.looks_like_close(text) and len(text.split()) <= 5
                    and runtime.get(wid) is not None):
                emit("brain", "🙈 orden corta de CERRAR → close (no data-op)", text=f"{wid} (era {action_name})",
                     role="system")
                _tag_emit("close", {"id": wid})
                return
            if _frontend.action_mode(wid, action_name) is None:   # acción no declarada → ¿verbo de canvas o escala?
                # GUARD frontera CANVAS vs DATOS (diag sesiones-largas 2026-07-15): a profundidad, el modelo a
                # veces cuela el SHOW/CLOSE como pseudo data-op (`widget_data(clock, action="show")` ante
                # "muéstrame un reloj"). Antes se curaba por el DESVÍO no-declarada→escalate→show-guard (frágil y
                # caro); ahora se mapea DIRECTO a la tag de canvas — misma ruta que [[show]]/[[close]] (dedup,
                # guards anti-clutter/meta, ack "nunca mudo"). Solo si el widget existe de verdad.
                _cv = _frontend.canvas_verb(action_name)
                if _cv and runtime.get(wid) is not None:
                    emit("brain", "🪟 widget_data con verbo de CANVAS → tag determinista",
                         text=f"{wid}:{action_name}→{_cv}", role="system")
                    _tag_emit(_cv, {"id": wid})
                    return
                if escalate_req["v"] is None:
                    escalate_req["v"] = text
                return
            res = refs.resolve(wid, action_name, ref, payload)
            # GUARD mis-ruteo por VERBO (2026-07-21, caso «hay que cancelarlo» tras «¿qué día tengo la ITV?»): el modelo
            # enganchó el verbo ("cancelar") con una data-op (agenda.drop) de un widget que NO está ABIERTO NI el
            # operador NOMBRÓ; el objeto era un PRONOMBRE SUELTO ("lo") cuyo antecedente vive en la CONVERSACIÓN, no en
            # ese widget. Cuando el item no ancla (pronombre suelto o no resuelve) Y el widget no está en pantalla NI se
            # nombra en el turno → el destino es erróneo: escalamos el turno CRUDO → el worker recibe la ventana
            # reciente verbatim (la ITV) y lo resuelve con contexto, en vez de operar/clarificar items de un widget
            # cerrado. NOTA: NO cubre el caso EXPLÍCITO con item que sí casa ("cancela la cita de la ITV" cuando la
            # agenda tiene ese appointment) — eso exige entender que es una acción del mundo real (capa de inteligencia,
            # ver V2-061); aquí solo se ataja el mis-ruteo por pronombre/ítem-ausente.
            # BUG real (maratón de testing 2026-07-22): `looks_like_bare_ref("")` es True por diseño (ref vacía =
            # "bare"), así que esta guarda disparaba en TODA acción de CREAR (add_meeting…) que nunca lleva `ref` —
            # escalaba "añade una cita con el dentista mañana" cada vez que la agenda no estaba ya abierta en
            # pantalla, aunque `res.ok` fuera True (refs.resolve ya distingue "nada que resolver" para estas
            # acciones). Solo tiene sentido mirar `ref` cuando la acción REALMENTE apunta a un item existente.
            _needs_item = bool(refs.id_field_for_action(wid, action_name))
            if (not res.ok or (_needs_item and _router.looks_like_bare_ref(ref))):
                try:
                    from memory import api as _memapi
                    _openw = set((_memapi.state() or {}).get("open_widgets") or [])
                except Exception:
                    _openw = set()
                if wid not in _openw and _identify(text) != wid:
                    emit("brain", "🧭 data-op en widget ausente/no-nombrado (pronombre/ítem sin anclar) → escala con contexto",
                         role="system", text=f"{wid}:{action_name}:{ref or '∅'}",
                         extra={"needs": res.needs, "bare": _router.looks_like_bare_ref(ref), "open": sorted(_openw)})
                    acted["widget"] = True
                    if escalate_req["v"] is None:
                        escalate_req["v"] = text
                    return
            if not res.ok:
                acted["widget"] = True                      # lo ATENDIMOS (preguntando) — no caer a escalate/fallback
                cands = ", ".join(res.candidates[:3])
                clarify["msg"] = (f"¿Cuál exactamente? Tengo {cands}." if cands
                                  else "No tengo claro a cuál te refieres, ¿me lo concretas?")
                emit("brain", "❓ referencia de item sin resolver", role="system",
                     text=f"{wid}:{action_name}:{ref or '∅'}", extra={"needs": res.needs, "cands": res.candidates[:4]})
                return
            _apply_widget_data(wid, action_name, res.payload)

        _tool_fired: set = set()

        def _word_overlap(a: str, b: str) -> int:
            wa = {w for w in (a or "").lower().split() if len(w) > 3}
            wb = {w for w in (b or "").lower().split() if len(w) > 3}
            return len(wa & wb)

        def _says_stop(t: str) -> bool:
            """¿Ha pedido el operador PARAR un proceso, en ESTE turno? Determinista, para gatear lo irreversible.

            Cuidado con «para»: en castellano es preposición mucho más veces que verbo («para nada», «para ti»,
            «no era para ti»), así que NO entra suelta — y de hecho «para» a secas solo calla la voz, nunca detiene
            tareas de fondo (regla del operador). Se piden formas inequívocas: el infinitivo/imperativo de parar con
            o sin pronombre, detener, cancelar, anular, abortar, «deja de», y los equivalentes en inglés."""
            n = _norm_nfkd(t or "")
            import re as _re_ss
            return bool(_re_ss.search(
                r"\b(par[ae]r(?:me|te|lo|la|los|las)?|par[ae]l[oa]s?|paralo|parala|"
                r"det[ei]n(?:er|lo|la|los|las|ga|gan)?|cancel(?:a|ar|alo|ala|o|en)|"
                r"anul(?:a|ar|alo|ala)|abort(?:a|ar|)|deja de|dejalo|"
                r"stop|cancel|abort|kill|halt|call it off)\b", n))

        def _on_tool_call(name: str, args: dict) -> None:
            # NINGUNA tool se ejecuta desde un fragmento superado: mientras el modelo generaba, el operador siguió
            # hablando, así que esta decisión se tomó sobre media frase. Abrir un widget o lanzar un worker con
            # criterios a medias es peor que no hacer nada — el turno completo llega enseguida.
            if self._superseded():
                emit("brain", "🧩 tool ignorada — la frase seguía", text=name, role="system",
                     extra={"cat": "flash", "fragment": (getattr(self, "_turn_text", "") or "")[:120]})
                return

            # Recorded AFTER the superseded gate on purpose: a tool that never ran is not something this turn did,
            # so it must not weigh on the end-of-turn flow-merge decision (V2-123, `_merge_target`).
            try:
                brain._turn_tools.add(name)
            except Exception:
                pass

            # ESCOTILLA de la selección progresiva (V2-096 F2): el modelo dice que le falta una familia. Se apunta
            # para que el turno la RECOMPONGA con esa familia cargada — un viaje extra MEDIBLE en vez de una
            # capacidad negada en silencio, que es el fallo que de verdad rompe una conversación. No es una tool
            # real: no hace nada, solo marca.
            if name == "need_capability":
                _fam = str((args or {}).get("family") or "").strip()
                if _fam:
                    self._need_family = _fam
                emit("brain", "🔓 el modelo pide una familia que se había recortado", text=_fam, role="system",
                     extra={"cat": "flash", "family": _fam, "retry": True})
                return

            # Alimenta la capa `recent` del turno siguiente: una conversación que ya iba de widgets no debería
            # perderlos porque el turno siguiente no los nombre.
            try:
                from nucleo.flash import tool_selection as _tsel2
                _fams = _tsel2.families_used([name])
                if _fams:
                    prev = list(getattr(brain, "_recent_tool_families", None) or ())
                    brain._recent_tool_families = list(dict.fromkeys(list(_fams) + prev))[:3]
            except Exception:
                pass
            if name == "widget_data":
                # UNA data-op por turno: el modelo pequeño a veces emite VARIAS widget_data en un mismo turno
                # (enumera acciones ante "muéstrame la agenda" → done/drop/snooze…, o DUPLICA un add_meeting → cita
                # doble). Solo la PRIMERA se ejecuta (mismo criterio "1 acción/turno" que escalate/search).
                if "widget_data" in _tool_fired:
                    return
                _tool_fired.add("widget_data")
                _handle_widget_data_tool(args)
            elif name == "escalate_to_slowbrain":
                req = (args.get("request") or "").strip() or text
                # V2-227: la superficie declarada se guarda POR petición. Solo se puebla desde la llamada real
                # del modelo; los caminos de respaldo de este fichero (el tag filtrado, los backstops) no la
                # conocen y dejan que `surfaces.resolve()` la derive del kind — que es para lo que existe.
                _sf = str(args.get("surface") or "").strip()
                if _sf:
                    escalate_req["surface"][req] = _sf
                if escalate_req["v"] is None:
                    escalate_req["v"] = req
                elif (args.get("request") or "").strip():
                    # Una 2ª (3ª…) llamada del MODELO en el mismo turno = otra tarea. Se exige `request` propio:
                    # sin él la llamada cae a `text`, que es la MISMA frase, y duplicaríamos la tarea principal.
                    # El tope existe porque el destinatario es un pool de workers reales (`dispatch._max_parallel`,
                    # 3 por defecto): un modelo que se atasque enumerando no debe poder abrir una tarea por ítem.
                    if len(escalate_req["more"]) < 2 and req not in escalate_req["more"] and req != escalate_req["v"]:
                        escalate_req["more"].append(req)
            elif name == "web_search":
                q = (args.get("query") or "").strip() or text
                # TURN-BLEED: el modelo a veces re-emite la búsqueda del turno ANTERIOR junto a la de este (visto:
                # "precio bitcoin" colado en el turno "¿cuándo es el eclipse?"). Nos quedamos con la query que MÁS
                # se parece al turno ACTUAL, no con la primera (que puede ser la vieja) → no buscamos lo que no es.
                if search_req["v"] is None or _word_overlap(q, text) > _word_overlap(search_req["v"], text):
                    search_req["v"] = q
            elif name == "recall":
                # V2-056: el MODELO decide recordar (V2-022 aplicado a la memoria). Se resuelve tras el stream,
                # fuera del event loop; la heurística needs_recall queda como prefetch.
                if recall_req["v"] is None:
                    recall_req["v"] = (args.get("query") or "").strip() or text
            elif name == "reveal_secret":
                # V2-060: el operador pide un SECRETO guardado. Se resuelve tras el stream; el valor NUNCA entra en
                # un prompt del modelo → el provider lo entrega OUT-OF-BAND (voz/pantalla). Aquí solo se captura QUÉ.
                if reveal_req["v"] is None:
                    reveal_req["v"] = (args.get("label") or "").strip() or text
            elif name == "play_music":
                # V2-041: una acción de música por turno. Ruta LIGERA como web_search: se resuelve tras el stream,
                # FUERA del event loop.
                _mq = {"query": (args.get("query") or "").strip(),
                       "action": (args.get("action") or "play").strip().lower()}
                if music_req["v"] is None:
                    music_req["v"] = _mq
                else:
                    # COLAPSO determinista de VARIAS play_music en un turno (V2-047 F4, sesión 23:15: el modelo
                    # no-razonador emite play Y queue a la vez para «luego pon X» → si gana el 'play' reproduce en
                    # vez de encolar). Con música YA sonando, un `queue` MANDA sobre un `play` (añades, no
                    # reemplazas); sin nada sonando, se queda la primera. Sobre el ESTADO del rail + la acción que
                    # el propio modelo eligió — no una tabla de palabras.
                    try:
                        from nucleo import rails as _rails_m
                        _playing = _rails_m.get("music.playing") is not None
                    except Exception:
                        _playing = False
                    if _playing and _mq["action"] == "queue" and music_req["v"].get("action") != "queue":
                        music_req["v"] = _mq
                    # BUG real 2026-07-23: "pon música de Queen y súbele el volumen al máximo" — el modelo emite
                    # play(Queen) + volume_up en el MISMO turno; antes la 2ª se tiraba en silencio mientras el
                    # modelo SÍ decía "subo el volumen" (confabulación: la voz prometía algo que el código no
                    # hacía). Una 2ª llamada de CONTROL puro (sin query, verbo de ajuste) tras un play/queue NO se
                    # descarta: se guarda como `followup` y se ejecuta EN SECUENCIA tras el play (abajo).
                    elif (not _mq["query"] and _mq["action"] in
                          ("volume_up", "volume_down", "pause", "resume", "stop", "next", "previous")):
                        music_req["followup"] = _mq
            elif name == "play_video":
                # V2-045: VÍDEO = widget youtube (VER), hermano de play_music (OÍR). Tool de 1ª clase para que el
                # modelo discrimine tool-vs-tool (la prosa no bastaba con el titular anterior: el vídeo caía en play_music). La
                # EJECUTA el provider: muestra el widget youtube + data-op `load` con la query (el widget busca y
                # reproduce el vídeo real). Una por turno. El ack "nunca mudo" lo cubre data_done/acted (abajo).
                if "play_video" not in _tool_fired:
                    _tool_fired.add("play_video")
                    _vq = (args.get("query") or "").strip()
                    emit("widget", "show", extra={"id": "youtube", "src": "flash"})
                    _apply_widget_data("youtube", "load", {"query": _vq} if _vq else {})
                    emit("brain", "▶️ vídeo → widget youtube", text=_vq[:80], role="system")
            elif name == "show_widget":
                # MOSTRAR un widget (incl. JUEGOS) como TOOL de 1ª clase — más fiable que el tag [[show]] cuando la
                # palabra colisiona con play_music/play_video ('juega al snake'). Converge en la MISMA ruta de canvas
                # ([[show:id]], dedup/idempotente). Resuelve el id: exacto del catálogo o fuzzy con runtime.identify.
                if "show_widget" not in _tool_fired:
                    _tool_fired.add("show_widget")
                    _wid = (args.get("widget_id") or "").strip()
                    # GUARD: CREAR un widget nuevo NO es show → escala al generador (el modelo elige show_widget para
                    # 'créame un widget de X' e `identify` devuelve un widget EXISTENTE equivocado). Backstop determinista.
                    if _router.looks_like_create_widget(text):
                        if escalate_req["v"] is None:
                            escalate_req["v"] = text
                        emit("brain", "🏗️ show_widget→CREATE: se escala al generador (no es un show)", role="system")
                    else:
                        from widgets import runtime
                        # Resolver CON CERTEZA (V2-082): solo nombre/alias abren; contexto (abiertos>recientes) para
                        # desempatar. Devuelve match (widget), system (superficie de sistema nombrada) o nada.
                        try:
                            from memory import api as _memapi
                            _st = _memapi.state() or {}
                            _open, _recent = _st.get("open_widgets") or [], _st.get("recent_widgets") or []
                        except Exception:
                            _open, _recent = [], []
                        _res = {}
                        try:
                            _contextual = _show_guard_target(text, brain._window, brain._last_action)
                            if _contextual:
                                _res = {"match": _contextual, "system": None}
                            elif _wid and runtime.get(_wid) is not None:       # id exacto del catálogo
                                _res = {"match": _wid, "system": None}
                            else:                                            # nombre/alias → id REAL o superficie
                                _res = runtime.identify(_wid or text, open_ids=_open, recent_ids=_recent) or {}
                        except Exception:
                            _res = {"match": _wid if runtime.get(_wid) is not None else None, "system": None}
                        _rid = _res.get("match") or ""
                        _rid = _rid if (_rid and runtime.get(_rid) is not None) else ""
                        _sys = _res.get("system")
                        if _rid:
                            _tag_emit("show", {"id": _rid})
                            # V2-209: QUÉ se abrió, no solo QUE se abrió. Sin el id, el ack de más abajo no puede
                            # distinguir «aquí lo tienes» de «te lo abro y sigo con ello», que es la diferencia
                            # entre informar y afirmar una entrega que no ha ocurrido.
                            acted["widget_id"] = _rid
                            emit("brain", "🪟 show_widget → canvas", text=_rid, role="system",
                                 extra={"empty": _surface_is_empty(_rid)})
                        elif _sys == "chat":
                            # nombró el CHAT (superficie de sistema, no un widget) → abre el panel nativo.
                            emit("panel", "open", extra={"tab": "chat", "src": "flash"})
                            emit("brain", "🗂️ show_widget→chat (superficie de sistema)", role="system")
                            acted["widget"] = True
                        else:
                            # V2-082: NO se fabrica un widget cuando no hay match. Si nombró una pieza de sistema o
                            # nada reconocible → se PREGUNTA con naturalidad, jamás se escala al generador ni se abre
                            # el "más parecido". (Crear solo con crea/genera/hazme/modifica, ya filtrado arriba.)
                            clarify["msg"] = ("No tengo ninguna pieza con ese nombre; ¿cuál quieres que te abra?"
                                              if _sys is None else
                                              "Eso es una pieza del sistema; ábrela desde su botón o dime su nombre.")
                            emit("brain", "🤔 show_widget sin match → pregunto (no fabrico widget)",
                                 text=str(_sys or "—"), role="system")
            elif name == "show_panel":
                # V2-079: abre el PANEL nativo lateral (ChatWall) en una pestaña por voz — 'enséñame los procesos',
                # 'los crons', 'ábreme el chat'. NO es un widget del canvas: se emite un evento `panel` que el
                # frontend (sse.js) traduce a store.setChatTab + setChatOpen. UI nativa e intocable.
                if "show_panel" not in _tool_fired:
                    _tool_fired.add("show_panel")
                    _tab = _router._canon_panel(args.get("panel"))
                    # 2026-08-10: también CIERRA. Antes solo abría, así que «cierra el chat» no tenía a dónde ir y
                    # el turno acababa en un «vale, cerrado» que era falso.
                    _act = _router._canon_panel_action(args.get("action"))
                    emit("panel", _act, extra={"tab": _tab, "src": "flash"})
                    emit("brain", f"🗂️ show_panel → panel nativo ({_act})", text=_tab, role="system")
                    acted["widget"] = True     # cuenta como acción de UI (ack "nunca mudo" + no escala espurio)
            elif name == "manage_widget_alias":
                # V2-082: añade/quita un NOMBRE/ALIAS de un widget por voz ("añade el alias WhatsApp a mensajería").
                # Escritura QUIRÚRGICA del manifest (no regenera código), con guard de colisión. Resuelve el widget
                # por id exacto o por nombre/alias (mismo resolver de certeza). Este bucle de tool-calls es SÍNCRONO
                # (como _apply_widget_data) → la escritura va inline (I/O de fichero de ms, no un await).
                if "manage_widget_alias" not in _tool_fired:
                    _tool_fired.add("manage_widget_alias")
                    from widgets import aliases as _al, runtime as _rt_al
                    _awid = (args.get("widget_id") or "").strip()
                    _alias = (args.get("alias") or "").strip()
                    _op = "remove" if str(args.get("op") or "add").lower().startswith(("rem", "quit", "borr")) else "add"
                    _rid = _awid if (_awid and _rt_al.get(_awid) is not None) else \
                        ((_rt_al.identify(_awid or text) or {}).get("match") or "")
                    if not _rid:
                        clarify["msg"] = "¿A qué widget le cambio el nombre? No lo localizo."
                    elif not _alias:
                        clarify["msg"] = "¿Qué alias quieres que le ponga?"
                    else:
                        _res = (_al.remove if _op == "remove" else _al.add)(_rid, _alias)
                        acted["widget"] = True
                        if _res.get("ok") and not _res.get("unchanged"):
                            clarify["msg"] = (f"Hecho, le quité el alias «{_alias}»." if _op == "remove"
                                              else f"Hecho, «{_rid}» también responde ahora a «{_alias}».")
                        elif _res.get("unchanged"):
                            clarify["msg"] = (f"«{_rid}» ya {'no tenía' if _op == 'remove' else 'tenía'} ese alias.")
                        else:
                            clarify["msg"] = _res.get("error") or "No pude cambiar el alias."
                        emit("brain", f"🏷️ manage_widget_alias {_op} → {_rid}", text=_alias, role="system")
            elif name == "fullscreen_widget":
                # BUG real 2026-07-23: "ponme el vídeo a pantalla completa" no tenía tool → el modelo confabulaba
                # éxito o inventaba una data-op falsa. Espejo de show_widget: resuelve el id (exacto o fuzzy) y
                # emite la tag de CANVAS `fullscreen` (nunca una data-op — esto es tamaño en pantalla, no datos).
                if "fullscreen_widget" not in _tool_fired:
                    _tool_fired.add("fullscreen_widget")
                    from widgets import runtime as _rt_fs
                    _wid = (args.get("widget_id") or "").strip()
                    _rid = ""
                    try:
                        if _wid and _rt_fs.get(_wid) is not None:
                            _rid = _wid
                        else:
                            _m = (_rt_fs.identify(_wid or text) or {}).get("match") or ""
                            _rid = _m if (_m and _rt_fs.get(_m) is not None) else ""
                    except Exception:
                        _rid = _wid if _rt_fs.get(_wid) is not None else ""
                    if _rid:
                        _tag_emit("show", {"id": _rid})     # por si no estaba abierto todavía
                        _tag_emit("fullscreen", {"id": _rid})
                        emit("brain", "⛶ fullscreen_widget → canvas", text=_rid, role="system")
            elif name == "reply_message":
                # V2-051: responder un mensaje del buzón. Converge en la data-op `reply` de `mensajeria`
                # (confirm:true) → el gate CONFIRM lee el borrador y pide OK antes de ENVIAR. Una por turno.
                if "reply_message" not in _tool_fired:
                    _tool_fired.add("reply_message")
                    try:
                        _n = int(args.get("n"))
                    except (TypeError, ValueError):
                        _n = None
                    _rtext = (args.get("text") or "").strip()
                    if _n is not None and _rtext:
                        _apply_widget_data("mensajeria", "reply", {"n": _n, "text": _rtext})
                    else:
                        clarify["msg"] = "¿A qué mensaje respondo y qué le digo?"
            elif name == "delete_widget":
                _request_delete_confirm((args.get("widget_id") or "").strip(), text)
            elif name == "confirm_widget_delete":
                confirm_state["handled"] = _resolve_confirm(bool(args.get("confirmed")))
            elif name == "set_style_directive":
                # V2-046 A1: la regla se aplica YA (directiva de sesión, capa inmediata — intacto) y PERSISTE como
                # USER RULE en el ESTADO (state.rules, off-loop → viaja en compose_state §B en cada prompt, µs).
                # El sentido añadir/retirar lo decide un guard determinista sobre el turno, no el LLM. Fuera el
                # anti-patrón viejo de "lanza un worker para guardarla".
                directive = (args.get("directive") or "").strip()
                if directive:
                    style_fired["v"] = True

                    async def _persist_rule(d: str, removal: bool) -> None:
                        try:
                            from memory import api as _mem
                            if removal:
                                _, gone = await asyncio.to_thread(_mem.remove_user_rule, d)
                                emit("brain", "🧬 user rule retirada" if gone else "🧬 user rule: sin match para retirar",
                                     text=(gone or d)[:100], role="system")
                            else:
                                await asyncio.to_thread(_mem.add_user_rule, d)
                                emit("brain", "🧬 user rule guardada (persiste)", text=d[:100], role="system")
                        except Exception as e:  # noqa: BLE001
                            logger.warning(f"user rule no persistida (voz sigue): {e}")

                    if _router.looks_like_rule_removal(text):
                        brain._directive = ""            # la capa inmediata también suelta la regla retirada
                        _spawn(_persist_rule(directive, True), "user-rule")
                    else:
                        brain._directive = directive
                        emit("brain", "🎯 directiva de estilo fijada", text=directive, role="system")
                        _spawn(_persist_rule(directive, False), "user-rule")
            elif name == "authenticate_web":
                # Guard DETERMINISTA (V2-022): si además de entrar hay una TAREA ("entra en mi Gmail y BÓRRAME…"),
                # no es un login → es una tarea con sesión → escala al navegador (que resuelve el login como parte
                # de la tarea). authenticate_web es SOLO para login puro ("conéctame a Wallapop").
                # V2-176: la DECISIÓN (cuál de los cuatro caminos es) vive en `nucleo/flash/web_auth.decide`,
                # compartida con el canal de texto — la cadena estaba solo aquí, así que el otro canal no tenía
                # ninguna. Los EFECTOS se quedan donde estaban: cada canal emite lo suyo y este además es el que
                # tiene `escalate_req`.
                from nucleo.flash import web_auth as _wa_v
                _site = (args.get("site") or "").strip()
                _kind_v, _site_resolved = _wa_v.decide(_site, text)
                if _kind_v == _wa_v.KIND_MUSIC:
                    # INVARIANTE (2026-07-16): un servicio de MÚSICA (Spotify) se conecta en el widget `musica`
                    # (su tarjeta OAuth), NUNCA por el navegador. El routing del titular anterior insistía en authenticate_web
                    # para "conéctame a mi cuenta de Spotify" pese a la descripción → el guard lo redirige aquí.
                    emit("widget", "show", extra={"id": "musica", "src": "flash"})
                    emit("brain", "🎵 conectar música → tarjeta del widget musica (no navegador)", text=_site or text[:60], role="system")
                elif _kind_v == _wa_v.KIND_MESSAGING:
                    # INVARIANTE (V2-045, espejo del guard de música): WhatsApp/Telegram se VINCULAN por QR DENTRO
                    # del widget `mensajeria`, NUNCA por login de navegador. 'conéctame/abre WhatsApp' → mostrar el
                    # widget (ahí está el QR), no abrir un Chromium en whatsapp.com.
                    emit("widget", "show", extra={"id": "mensajeria", "src": "flash"})
                    emit("brain", "💬 conectar mensajería → QR del widget mensajeria (no navegador)", text=_site or text[:60], role="system")
                elif _kind_v == _wa_v.KIND_TASK:
                    if escalate_req["v"] is None:
                        escalate_req["v"] = text
                    emit("brain", "🔐→🧭 login+tarea → escalado (no solo auth)", role="system")
                else:
                    _start_web_auth(_site_resolved)
            elif name == "login_done":
                _finish_web_auth()
            elif name == "connect_cluster":
                # V2-064: la tubería real (bridge.dispatch/dispatch_tag) ya existía — lo que faltaba era esta tool
                # PARA que el FlashBrain pudiera invocarla. No conecta directo: pide confirmación determinista
                # primero (ver _request_cluster_confirm) — la descripción de la tool sola no bastó para que el
                # modelo distinguiera una orden real de un texto pegado que solo mencionaba un cluster_id/token.
                _ccid = (args.get("cluster_id") or "").strip()
                _ctok = (args.get("token") or "").strip()
                # V2-086 — DOS clases de cluster. Antes la condición era `_ccid and _ctok`, así que un cluster
                # PÚBLICO (MeshKore Commons: tokenless por diseño) se descartaba en silencio: la tool se llamaba,
                # no pasaba nada y el operador no recibía ni un "no puedo". Ahora basta el cluster_id cuando el
                # cluster es público; el token solo es obligatorio en los privados.
                _cvis = (args.get("vis") or "").strip().lower()
                if _cvis not in ("public", "private", ""):
                    _cvis = ""
                if _ccid and not _ctok and not _cvis:
                    _cvis = "public"          # id sin token = solo puede ser un cluster abierto
                if _ccid and (_ctok or _cvis == "public"):
                    _cname = (args.get("name") or "meshcore").strip() or "meshcore"
                    _chandle = (args.get("handle") or "").strip() or None
                    # PERMISOS al conectar (V2-076): si el operador concede código, se persiste con la conexión.
                    _cperms = None
                    if bool(args.get("code")):
                        _cperms = {"workers": True, "code": True, "repo": (args.get("repo") or "").strip() or None}
                    _request_cluster_confirm(_cname, _ccid, _ctok, _chandle, perms=_cperms,
                                             vis=("public" if _cvis == "public" else ""))
            elif name == "cluster_send":
                # V2-086: enviar al cluster, ahora como tool de 1ª clase (antes iba por widget_data sobre el
                # widget `cluster-registro`, que ya no existe). Sale por el MISMO camino que el tag
                # [[cluster.send]] → `bridge.dispatch_tag`, así que hereda el guard de salida (un secreto duro
                # bloquea el envío) y el journal. No pide confirmación: es una comunicación normal que el
                # operador acaba de pedir, como escribir en un chat.
                _stext = (args.get("text") or "").strip()
                if _stext:
                    _sto = (args.get("to") or "").strip()
                    _scl = (args.get("cluster") or "").strip()
                    if not _scl:
                        try:
                            from connectors import meshkore as _mk2
                            _live = [c for c in _mk2.get_manager().clusters() if c.get("connected")]
                            _scl = _live[0]["name"] if len(_live) == 1 else ""
                        except Exception:
                            _scl = ""
                    if _scl:
                        _data = {"text": _stext}
                        if _sto:
                            _data["to"] = _sto
                        try:
                            from connectors import meshkore as _mk3
                            _spawn(_mk3.dispatch_tag(f"cluster.send:{_scl}", {"data": _data}), "cluster-send")
                            emit("brain", "🛰 mensaje enviado al cluster", role="system",
                                 text=f"{_scl}{('→' + _sto) if _sto else ''}")
                        except Exception as _e:  # noqa: BLE001
                            logger.warning(f"cluster_send falló: {_e}")
                    else:
                        emit("brain", "🛰 cluster_send sin cluster resuelto (¿varios o ninguno?)", role="system")
            elif name == "set_cluster_objective":
                # T-02 (auditoría 2026-07-26): antes NADA escribía nunca capsule.objective — el guard
                # `perms.gate_dev_by_objective` (V2-076) dejaba el dev-worker de CUALQUIER cluster con permiso
                # 'code' permanentemente inerte por falta de una vía para fijarlo. Sin confirm-gate (a diferencia
                # de connect_cluster): esto es solo bookkeeping declarativo del operador, no toca la red ni
                # ejecuta nada — reversible llamando de nuevo con objective vacío.
                _ocluster = (args.get("cluster") or "").strip()
                _opeer = (args.get("peer") or "").strip()
                _oobjective = (args.get("objective") or "").strip()
                if _ocluster and _opeer:
                    async def _persist_objective(cluster: str, peer: str, objective: str) -> None:
                        try:
                            from connectors.meshkore import capsule as _capsule
                            await asyncio.to_thread(_capsule.patch, cluster, peer, objective=objective)
                            emit("brain", ("🎯 objetivo de cluster fijado" if objective else
                                          "🎯 objetivo de cluster borrado"),
                                 text=f"{cluster}·{peer}: {objective}"[:160], role="system")
                        except Exception as e:  # noqa: BLE001
                            logger.warning(f"set_cluster_objective no persistido (voz sigue): {e}")
                    _spawn(_persist_objective(_ocluster, _opeer, _oobjective), "cluster-objective")
                else:
                    clarify["msg"] = "¿Con qué agente y de qué cluster es ese objetivo?"
            elif name == "send_to_worker":
                # V2-038 (↓): refina/amplía un worker vivo → INYECTA (no relanza). Fire-and-forget marshalado al
                # loop del server (§v3·O: nunca await de una op de worker en el turno).
                which = (args.get("which") or "").strip()
                msg = (args.get("message") or "").strip()
                if msg:
                    try:
                        from nucleo import dispatch as _d
                        _d.inject_soon(which or "todo", msg)
                        worker_acted["v"] = "inject"
                        emit("brain", "↪️ inyección a worker", text=f"{which}: {msg}"[:120], role="system")
                        # Observability (V2-090 gap): this correction continues a LIVE task — its own dialogue
                        # exchange should show up INSIDE that task's flow instead of opening a fresh one. Only
                        # when the target is unambiguous (resolve_sessions picks exactly one): with several live
                        # sessions, forcing a merge would be guessing which one this belongs to.
                        try:
                            _targets = _d.resolve_sessions(which or "todo")
                            if len(_targets) == 1:
                                _target_trace = _d.trace_of(_targets[0])
                                if _target_trace:
                                    _trace.adopt(_target_trace)
                        except Exception:
                            pass
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"send_to_worker falló: {e}")
            elif name == "stop_worker":
                which = (args.get("which") or "").strip()
                # ── GUARD 1: NO SE MATA A QUIEN ACABAS DE CONTESTAR (2026-08-14, sesión b70a45d0) ──────────────
                # El fallo más caro de esa sesión, en un solo milisegundo: el turno emitió `answer_worker` con la
                # autorización que el worker llevaba 30 s esperando («Sí, autorizado: borra TODA la agenda») Y
                # `stop_worker` detrás, y la tarea murió `ok:False` con la respuesta ya entregada. Después le dijo
                # al operador «Vale, se lo digo» — falso en el instante en que lo dijo. La agenda nunca se vació.
                # Contestar y matar en el MISMO turno es incoherente por definición: si el operador acaba de dar la
                # respuesta que el proceso pedía, no está pidiendo que lo mates. Gana la respuesta (no destructiva).
                if worker_acted["v"] == "answer":
                    emit("brain", "🛡️ stop_worker ignorado — este turno ACABA de responder al worker",
                         text=f"{which or 'todo'}", role="system",
                         extra={"cat": "flash", "kind_diag": "stop_after_answer"})
                    return
                # ── GUARD 2: MATAR EXIGE QUE EL OPERADOR LO HAYA DICHO ────────────────────────────────────────
                # Mismo espíritu que el guarda de context-bleed de las data-ops (arriba, ~L797), pero para lo
                # irreversible: si en el turno del operador NO hay una orden de parar, el `stop_worker` es arrastre
                # del turno anterior. En la sesión, el stop nació de una queja de DOS TURNOS ANTES sobre widgets
                # («los dos navegadores no se tenían que haber abierto para nada»), y ese turno lo había cancelado
                # un barge-in. El modelo lo arrastró y lo convirtió en un hachazo.
                # OJO con «para»: en castellano es preposición mucho más a menudo que verbo («para nada», «para
                # ti»), y por eso no entra suelto — de hecho «para» a secas solo calla la voz, nunca para tareas
                # (regla del operador). Se piden formas inequívocas.
                if not _says_stop(text):
                    emit("brain", "🛡️ stop_worker ignorado — el operador no ha pedido parar nada (context-bleed)",
                         text=(text or "")[:120], role="system",
                         extra={"cat": "flash", "kind_diag": "stop_without_order", "which": which or "todo"})
                    return
                try:
                    from nucleo import dispatch as _d
                    # GUARD matar-TODO (sesión 23:15 2026-07-16, T49): ante «si solo es una tarea» el modelo llamó
                    # stop_worker(todo) y mató las DOS sesiones vivas — incluida la de la ITV que SÍ trabajaba
                    # (el operador se quejaba de VENTANAS duplicadas, no de procesos). Matar es irreversible →
                    # "todo" con VARIAS tareas de objetivos DISTINTOS exige que el operador lo haya dicho de
                    # verdad (todo/todas/ambos… en su turno, es/en); si no, se resuelve a la sesión que CASE con
                    # el texto (`resolve_sessions`) y, sin match claro, NO se mata nada (se pregunta).
                    import re as _re_stop
                    _w = which or "todo"
                    if _w == "todo":
                        _live = _d.pending_summaries()
                        _goals = {(s.get("request") or "")[:60] for s in _live}
                        _says_all = bool(_re_stop.search(r"\b(todo|todos|todas|ambos|ambas|all|both|everything)\b",
                                                         _norm_nfkd(text)))
                        if len(_goals) > 1 and not _says_all:
                            _match = _d.resolve_sessions(text)
                            if len(_match) == 1:
                                _w = _match[0]
                            else:
                                clarify["msg"] = ("Tengo varias tareas en marcha distintas — ¿cuál paro exactamente?")
                                worker_acted["v"] = "stop"      # atendido (preguntando), sin matar a ciegas
                                emit("brain", "🛑 stop_worker(todo) RETENIDO (varias tareas distintas, sin 'todo' "
                                     "explícito)", text=text[:100], role="system")
                                return
                    tids = _d.cancel_soon(_w)
                    worker_acted["v"] = "stop"
                    emit("brain", "🛑 stop worker", text=f"{_w} → {tids}"[:120], role="system")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"stop_worker falló: {e}")
            elif name == "answer_worker":
                ans = (args.get("answer") or "").strip()
                if ans:
                    try:
                        from nucleo import worker_api as _wapi
                        if _wapi.answer_active_soon(ans):
                            worker_acted["v"] = "answer"
                            emit("brain", "💬 respuesta a worker", text=ans[:120], role="system")
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"answer_worker falló: {e}")

        def _finish_web_auth() -> None:
            """El operador dijo por voz que ya inició sesión → encola `auth_done` a la tarea que esperaba login
            (mismo desenlace que el botón «Ya he iniciado sesión» de la tarjeta). Operator-only por construcción."""
            from nucleo.flash import web_auth as _wa_f
            _wa_f.finish("voz")     # V2-176: un solo cuerpo, compartido con el canal de texto

        def _start_web_auth(site: str) -> bool:
            """Abre la ventana REAL del navegador para que el operador inicie sesión en `site` (operator-only por
            construcción: es un tool del FlashBrain, y el canal de cluster no tiene tools). Crea la tarjeta de la
            tarea, la muestra y encola `authenticate` al owner del navegador. El owner relanza headed y, al terminar
            (auth_done), vuelve a headless con la sesión en el perfil. NUNCA tecleamos credenciales aquí.
            Bug 2026-07-23: sin `site` (el backstop no reconoció ningún sitio en el texto) esto abría SIEMPRE
            wallapop.com por defecto — un login a un sitio que nadie pidió. Sin sitio reconocido, no hay NADA que
            abrir: no adivinamos. Devuelve False (no se abrió nada) para que el llamador no cante "login por
            fallback" sobre una acción que no ocurrió."""
            from nucleo.flash import web_auth as _wa_s
            return bool(_wa_s.start(site))   # V2-176: un solo cuerpo, compartido con el canal de texto

        def take(final: bool) -> str:
            nonlocal buf
            out, buf = strip_tags(buf, _tag_emit, final)
            return out

        # Security-config voice command + spoken-secret interception (V2-060), both DETERMINISTA before the model
        # ever sees the text — moved to vault_intercept.py (2026-08-17 modularization pass, extraction step 1 of
        # the plan from this session's architecture audit). `send`/`emit` passed through as-is: `emit` may have
        # been locally overridden to a no-op above, and `send` is this closure's own turn-state accumulator.
        from voice.engine.llm.providers.vault_intercept import try_vault_intercept
        _vault_done, text = await try_vault_intercept(text, first_turn, send, emit)
        if _vault_done:
            return

        errored = False
        stalled = False          # se atascó UN turno (≠ el cerebro está caído) — cambia lo que se le cuenta al operador
        err_text = ""
        llm_metrics: dict = {}   # totalizadores de tamaño/tokens/latencia del modelo (observabilidad, FASE 0)
        # SET CONTEXTUAL DE TOOLS (V2-035): omite las situacionales que no aplican este turno (confirmar-borrado sin
        # borrado en el aire, login-hecho sin login en curso) → prompt más corto y menos ruido de decisión.
        try:
            from widgets.navegador import tasks as _nt
            _auth_pending = bool(_nt.login_waiting_id())
        except Exception:
            _auth_pending = False
        # V2-038: ofrece send/stop_worker solo si hay Brain Workers vivos, y answer_worker solo si alguno espera.
        try:
            from nucleo import dispatch as _dispatch, worker_api as _wapi
            _has_workers = _dispatch.has_active()
            _ask_pending = _wapi.has_pending_ask()
        except Exception:
            _has_workers = _ask_pending = False
        # V2-086: las tools de cluster YA NO dependen de tener un widget delante. El gate de V2-064
        # (`cluster-registro` abierto) hacía la capacidad INDESCUBRIBLE — para conectar un cluster NUEVO había que
        # saber de antemano que primero tocaba abrir un widget concreto (pez que se muerde la cola: comprobado en
        # el turno 766 del 2026-08-01, donde `connect_cluster` simplemente no estaba en el set ofrecido y el
        # modelo no pudo hacer nada). La protección real contra el disparo espurio no era ese gate sino la
        # CONFIRMACIÓN Sí/No determinista con el cluster_id a la vista, que sigue intacta.
        _cluster_open = True
        # `cluster_send` sí es situacional, pero por ESTADO REAL: sin cluster conectado no hay a quién escribir.
        try:
            from connectors import meshkore as _mk0
            _cluster_conn = any(c.get("connected") for c in _mk0.get_manager().clusters())
        except Exception:
            _cluster_conn = False
        # V2-085 — tres CAPACIDADES reales más (nunca palabras del turno: hechos del sistema). Todas fail-OPEN:
        # si el sondeo peta, la tool se ofrece igual y no le quitamos nada al operador.
        try:
            from connectors.whatsapp import service as _wa1
            _msg_on = _wa1.enabled()
        except Exception:
            _msg_on = False
        if not _msg_on:
            try:
                from connectors.telegram import service as _tg1
                _msg_on = _tg1.enabled()
            except Exception:
                _msg_on = True                  # no se pudo sondear ninguno → fail-open
        try:
            from memory import vault as _vault1
            _has_vault1 = _vault1.exists()
        except Exception:
            _has_vault1 = True
        try:
            from widgets import runtime as _rt_cap
            _has_video1 = _rt_cap.get("youtube") is not None
        except Exception:
            _has_video1 = True
        _tool_ctx = _router.tool_context(confirm_pending=had_pending_confirm, auth_pending=_auth_pending,
                                         has_workers=_has_workers, ask_pending=_ask_pending,
                                         cluster_widget_open=_cluster_open, messaging_on=_msg_on,
                                         has_vault=_has_vault1, has_video_widget=_has_video1,
                                         cluster_connected=_cluster_conn)
        _turn_tools = _router.tools(_tool_ctx)
        # KICKOFF = saludo PURO, sin tools (fix 2026-07-19): el texto del kickoff ("Salúdame en 1-2 frases, cálido y
        # breve…") lo interpretaba el modelo como `set_style_directive` → guardaba una regla y respondía "Hecho." en
        # vez de saludar. El saludo no necesita ninguna tool → no las ofrecemos y no hay nada que mis-rutear.
        if first_turn:
            _turn_tools = []
        # SELECCIÓN PROGRESIVA (V2-096 F2): el turno lleva la DIRECCIÓN hacia la que va, no el catálogo entero.
        # «Cuando alguien dice "hola, ¿qué tal?" no le vamos a mandar todos los widgets, todas las tools.»
        # Va DESPUÉS del gate por estado (que decide qué capacidades EXISTEN) porque son cosas distintas: el gate
        # niega, esto solo recupera candidatos — y por eso puede mirar las palabras del turno sin romper el
        # invariante de V2-085. Medido sobre los 14 casos del nodo 2.13: **−51,4% de chars de catálogo** y CERO
        # casos que se queden sin ninguna tool aceptable.
        _tool_report: dict = {}
        if not first_turn:
            try:
                from nucleo.flash import tool_selection as _tsel
                # «Lo que tiene DELANTE» sale del ESTADO, no de las palabras — es la capa que no se puede recortar
                # (V2-085). Lectura directa de µs, ya cacheada; si falla, se degrada a las otras capas.
                try:
                    from memory import api as _mem_sel
                    _open_now = (_mem_sel.state() or {}).get("open_widgets") or []
                except Exception:
                    _open_now = []
                _turn_tools, _tool_report = _tsel.select(
                    _turn_tools, turn_text=text, open_widgets=_open_now,
                    recent_families=getattr(brain, "_recent_tool_families", None),
                    force=getattr(self, "_force_families", None))
                if _tool_report.get("omitted"):
                    emit("brain", "🎯 tools recortadas al rumbo del turno", role="system",
                         extra={"cat": "flash", **_tool_report})
            except Exception as e:  # noqa: BLE001
                emit("brain", "⚠️ selección de tools falló — catálogo completo", role="system",
                     extra={"cat": "flash", "err": repr(e)[:120]})
        # OBSERVABILIDAD del presupuesto de tools (V2-085): no solo cuántas — cuánto ocupan, qué familias entraron
        # y cuáles se podaron. Junto a los `sz_*`/`widgets_*` del prompt cierra el desglose completo del turno.
        try:
            llm_metrics.update(_router.tools_report(_turn_tools))
        except Exception:
            llm_metrics["n_tools_offered"] = len(_turn_tools)
        # LEAD-IN FILLER (naturalidad, 2026-07-19; extraído a su propio módulo V2-114, 2026-08-17): el TTFT del
        # modelo (~1.1s medido) deja un silencio que no parece charla. Si a los ~ZAELAR_FILLER_MS ms NO ha
        # empezado la respuesta REAL, `LeadInFiller` suelta UN sonido de pensar neutro y variado ("a ver…",
        # "mmm…") en paralelo — rellena SOLO los turnos que tardan de verdad; las respuestas rápidas salen
        # limpias. Voz-only (el probe no monta esto). Kill-switch ZAELAR_FILLER_MS=0. Ver
        # `voice/engine/llm/providers/lead_in_filler.py` para el mecanismo completo.
        try:
            _filler_ms = int(os.getenv("ZAELAR_FILLER_MS", "600"))
        except Exception:
            _filler_ms = 600

        # NO en el kickoff: el saludo lo inicia zaelar (nadie espera) → un "Pues…" antes de saludar suena raro.
        # Último corte ANTES de pagar el modelo: si la frase ya creció, este fragmento no tiene nada que decir.
        if self._superseded():
            self._death_logged = True
            emit("brain", "🧩 fragmento descartado — la frase seguía", text=text[:200], role="system",
                 extra={"cat": "flash", "phase": self._phase, "spent_model": False})
            return

        from voice.engine.llm.providers.lead_in_filler import LeadInFiller
        _filler = (LeadInFiller(delay_ms=_filler_ms, brain=brain, superseded=self._superseded,
                                 event_ch=self._event_ch, emit=emit)
                   if (_filler_ms > 0 and not first_turn) else None)
        if _filler is not None:
            _filler.start()
        self._phase = "generando la respuesta"
        try:
            # PLAZO DE SILENCIO — el FlashBrain NUNCA se queda parado (2026-08-10, regla dura del operador).
            # Sesión 14:08:26: 23 turnos seguidos sin respuesta durante 5 minutos. El operador llegó a preguntar
            # «¿me estás escuchando?», «¿estás operativo, sí o no?» y tampoco obtuvo nada. La medida del log:
            # turnos de 35,7 s · 31,8 s · 32,2 s y uno de 60,5 s, todos con `partial_chars=0` y `ttft=None`, o sea
            # el modelo NO emitió un solo token hablable. No era razonamiento ni contención de los workers: la
            # llamada se quedaba colgada y el único plazo que existía era el timeout de red de httpx —60 s—, una
            # eternidad en el camino de tiempo real. Mientras, cada frase nueva del operador cancelaba el turno en
            # vuelo, así que el siguiente empezaba de cero: inanición perfecta, el sistema no podía contestar nunca.
            # El plazo se mide sobre el SILENCIO, no sobre la duración total: cada trozo hablable lo reinicia, así
            # una respuesta larga y legítima se transmite entera y solo se corta lo que de verdad no avanza.
            # EL PLAZO MIDE QUE EL STREAM NO AVANZA, no que no salga voz (corregido 2026-08-12, con tres turnos
            # SANOS muertos en dos minutos). Un turno cuya respuesta es una ACCIÓN —«muéstrame los resultados»,
            # «cierra eso»— no emite NI UN carácter hablable: los chunks de la tool-call los consume `stream()` sin
            # yieldear nada, así que desde aquí un turno de acción y un modelo colgado se veían IGUAL. Medido en el
            # corte de las 13:49: `ttft=1.50s` —el modelo había contestado en segundo y medio— con `spoken_chars=0`;
            # el plazo lo mataba a los 9 s, el operador oía «se me ha ido un momento» y seguía sin ver sus
            # resultados. Ahora `fast_client` sella `last_chunk_ts` en CADA chunk y aquí se consulta antes de
            # declarar nada: un stream que avanza es un turno vivo, aunque calle.
            #
            # Y se recorre con una TAREA BOMBA en vez de un `wait_for` sobre `__anext__()`: cancelar un `__anext__`
            # a mitad y llamar luego a `aclose()` deja el generador en un estado indefinido —carrera conocida, y
            # candidata a los cuelgues del hilo de voz—. Cancelar la TAREA sí es limpio: es la única dueña del
            # `async for`, y el `finally` de `stream()` cierra y dispara sus tool-calls acumuladas igual que en
            # cualquier otro cierre.
            _quiet_ms = _turn_budget_ms()
            _chunks: asyncio.Queue = asyncio.Queue()
            _stream = FastClient().stream(messages, spec=spec, tools=_turn_tools,
                                          on_tool_call=_on_tool_call, metrics=llm_metrics)

            async def _pump() -> None:
                try:
                    async for _d in _stream:
                        await _chunks.put(("d", _d))
                except asyncio.CancelledError:
                    raise
                except BaseException as _e:  # noqa: BLE001
                    await _chunks.put(("err", _e))
                    return
                await _chunks.put(("end", None))

            _pump_task = asyncio.create_task(_pump(), name="flash-stream-pump")
            try:
                while True:
                    try:
                        _kind, _val = await asyncio.wait_for(_chunks.get(), timeout=_quiet_ms / 1000.0)
                    except asyncio.TimeoutError:
                        # ¿Llega algo por debajo (argumentos de una tool-call)? Entonces NO es un atasco.
                        if stream_advancing(llm_metrics, _quiet_ms):
                            continue
                        # Atasco de verdad: ni texto ni chunks. Se trata como fallo del cerebro (rama `errored`):
                        # frase corta y honesta + aviso — nunca un minuto de silencio que parece un cuelgue.
                        errored = True
                        stalled = True
                        err_text = f"flash brain stalled: {_quiet_ms} ms sin un solo chunk"
                        emit("brain", "⏱️ turno ATASCADO — el modelo no emitía nada, lo corto", role="system",
                             extra={"cat": "flash", "quiet_ms": _quiet_ms, "spoken_chars": len("".join(spoken)),
                                    "chunks": int(llm_metrics.get("chunks") or 0), "phase": self._phase})
                        break
                    if _kind == "err":
                        raise _val
                    if _kind == "end":
                        break
                    delta = _val
                    if delta and _filler is not None:
                        _filler.mark_real_started()         # primer token REAL → corta el timer del filler
                    buf += delta
                    if delta:
                        _quiet_ms = _turn_budget_ms()      # hay avance real → el plazo se renueva
                    send(speech.inline(take(False)))
            finally:
                if not _pump_task.done():
                    _pump_task.cancel()
            if not errored:
                send(speech.sanitize(take(True), drop_metadata=False))
        except asyncio.CancelledError:
            # BARGE-IN / turno superpuesto: el stream se cancela. NO reinyectamos la respuesta parcial a la ventana
            # (el `raise` salta el append de más abajo) → sin respuestas zombie. PERO lo que dijo el OPERADOR sí se
            # conserva (fix 2026-08-02): cancelar la RESPUESTA no borra la FRASE, y hasta hoy el `raise` se llevaba
            # por delante el turno de usuario → el siguiente turno llegaba al modelo sin el contexto que el operador
            # acababa de dar (ver dialog.push_user para el caso real de la piscina). Coalesce por prefijo, así los
            # trozos acumulativos del STT no duplican la frase.
            _dialog.push_user(brain._window, text)
            del brain._window[:-_WINDOW_MAX]
            # El relleno de ESTE turno se va con él. Un turno cancelado por barge-in es el operador tomando la
            # palabra, y seguir soltando su «a ver…» encima es precisamente hablarle encima.
            if _filler is not None:
                _filler.cancel_for_barge_in()
            self._death_logged = True   # ya se relata aquí, con métricas; la envoltura de `_run` no duplica
            emit("brain", "✂️ turno cancelado (barge-in/overlap)", role="system",
                 extra={"cat": "flash", "partial_chars": len("".join(spoken)),
                        "ttft_ms": first_ms, "cut_after_ms": round((time.time() - t0) * 1000)})
            raise  # barge-in
        except Exception as e:
            errored = True
            err_text = str(e)
            logger.warning(f"nucleo fast brain error (not spoken raw): {e}")
        finally:
            # el stream terminó (ok/tool-only/error): corta el timer del filler para que no suelte uno tardío
            if _filler is not None:
                _filler.stop()

        if errored:
            # DEGRADED: sin Hermes al que caer — frase de reserva segura (nunca el error crudo, nunca mudo).
            # CLASIFICA el error (V2-043): SIN SALDO/cuota (credit) · credencial (auth) · caída (outage) — así el
            # diálogo de estado muestra la alerta REAL en vez de un genérico "no responde". Fail-open a "error".
            # UN TURNO ATASCADO NO ES «EL CEREBRO ESTÁ CAÍDO» (fix 2026-08-12). El plazo de silencio reutilizaba esta
            # rama entera, así que un corte aislado —del que la sesión se recupera al turno siguiente— pintaba el ◉ en
            # rojo con «no responde» y gritaba «Cerebro rápido caído». Visto en vivo: el modelo contestaba bien antes y
            # después, y el operador se queda mirando un LLM en rojo que funciona. Se distingue el HECHO (este turno no
            # salió, y eso hay que decirlo) del DIAGNÓSTICO (el proveedor está caído, que es otra cosa y más grave).
            # V2-252 — la DECISIÓN (¿atasco o fallo duro? ¿a qué escalón se releva? ¿queda alguno?) vive ahora en
            # `nucleo/flash/provider_failure.py`, compartida con el canal de TEXTO. Estaba escrita dos veces y esa
            # duplicación mordió tres veces: la última dejó al arnés ocho horas sin poder medir, con el texto
            # devolviendo un 402 en el mismo segundo en que el log decía «relevo a aimlapi-failover». Lo que NO se
            # comparte, a propósito, es lo que cada canal DICE: esta habla, el otro devuelve un objeto.
            _v = {}
            try:
                from nucleo.flash import provider_chain as _pchain1
                from nucleo.flash import provider_failure as _pfail
                _v = _pfail.handle(err_text, role=_pchain1.ROLE_VOICE, stalled=bool(stalled), spec=spec)
            except Exception:
                pass
            # RELAY on a HARD failure, not just a slow one (2026-08-15 addendum to V2-094): `note_slow` below
            # already relays a titular that's merely lagging, but a real provider error — no balance, bad
            # credential, an outage — used to just repeat against the same broken tier turn after turn, because
            # `note_failure` was hardcoded to the CLUSTER role. Cooldown is sticky (`pick()` is O(1)), so this
            # only needs to fire once per failure — the NEXT turn already starts on the relay.
            # V2-243/246: el cooldown, el relevo y el «¿queda alguien?» los acaba de resolver `provider_failure`
            # (un atasco REPETIDO cuenta —`note_stall`—; uno aislado es ruido). Aquí solo se lee el veredicto.
            _dry = bool(_v.get("dry")) and not stalled
            if stalled:
                emit("alert", "Un turno se atascó y lo corté — sigo operativo.", text="flash turn stalled")
            elif _dry:
                emit("alert", "Sin proveedor de modelo — no es un tropiezo, no hay a quién preguntar.",
                     text=err_text[:200] or "provider chain exhausted")
            else:
                emit("alert", "Cerebro rápido caído — turno degradado.", text="flash layer error")
            emit("error", "nucleo flash brain error")
            # V2-243 — «¿ME LO REPITES?» ES UNA MENTIRA CUANDO NO QUEDA NINGÚN PROVEEDOR. Esa frase es la
            # correcta ante un tropiezo: el siguiente intento puede ir bien. Con la cadena entera seca, el
            # siguiente intento falla igual, y el operador se queda repitiéndose a una máquina que no puede
            # contestarle — sin enterarse de lo único que lo arregla, que es suyo y no del motor.
            # Medido en producción el 2026-08-21: `Insufficient Balance` (DeepSeek, 402) dos veces, «SIN RELEVO
            # disponible», y el canario del arnés MUDO en todos los turnos hasta que él paró de medir.
            _callados = []
            if _dry:
                try:
                    from nucleo.flash import provider_chain as _pchain2
                    _callados = _pchain2.suppressed_relays()
                except Exception:
                    _callados = []
            # V2-244: si HAY escalones con credencial y sanos que la regla de self-host está callando, el operador
            # tiene que oírlo — es la diferencia entre «no puedo seguir» y «no puedo seguir, y esto lo arregla».
            send("Uf, se me ha ido un momento. ¿Me lo repites?" if not _dry else
                 ("Me he quedado sin proveedor de modelo: no me queda ninguno al que preguntar, así que "
                  "repetírmelo no va a servir. Lo tienes en el panel de estado — hay que recargar o cambiar de "
                  "proveedor, y en cuanto lo hagas sigo." if not _callados else
                  f"Me he quedado sin proveedor de modelo. Tengo credencial de {', '.join(_callados)}, pero en "
                  f"self-host mi cadena de voz es solo el titular y no me paso sola a un proveedor que no hayas "
                  f"elegido. Si quieres que lo use, ponlo en `fast.providers`; si no, hay que recargar el titular."))
            return

        # SEGUNDO VIAJE de la selección progresiva (V2-096 F2), y SOLO aquí: la recuperación se equivocó y el modelo
        # lo dijo llamando a `need_capability`. Es el precio explícito y MEDIBLE de recortar el catálogo.
        #
        # Va DESPUÉS del stream, no dentro: ese bucle tiene tarea bomba, cola y plazo de silencio, y meterle un
        # reintento a media máquina es cómo se estropea el camino caliente. Aquí el primer stream ya cerró y el modelo
        # NO le dijo nada al operador (gastó el turno en pedir la familia), así que no hay voz que deshacer: se
        # repite la misma petición con la familia cargada. UNA sola vez — si con la familia delante tampoco resuelve,
        # no es un problema de catálogo y otro viaje solo añade segundos.
        _need = getattr(self, "_need_family", "")
        if _need and not getattr(self, "_retried_tools", False) and not "".join(spoken).strip():
            self._retried_tools = True
            try:
                from nucleo.flash import tool_selection as _tsel3
                _wider, _rep2 = _tsel3.select(_router.tools(_tool_ctx), turn_text=text, force={_need})
                emit("brain", "🔁 segundo viaje con la familia que faltaba", text=_need, role="system",
                     extra={"cat": "flash", "family": _need, **_rep2})
                _again: list[str] = []
                async for _piece in FastClient().stream(messages, spec=spec, tools=_wider,
                                                        on_tool_call=_on_tool_call, metrics=llm_metrics):
                    _again.append(_piece)
                if _again:
                    _txt2 = "".join(_again).strip()
                    spoken.append(_txt2)
                    send(_txt2)
            except Exception as e:  # noqa: BLE001
                emit("brain", "⚠️ el segundo viaje falló — sigo con lo que haya", role="system",
                     extra={"cat": "flash", "err": repr(e)[:120]})

        spoken_text = "".join(spoken).strip()

        # GUARD DETERMINISTA de SHOW puro (V2-023, ampliado 2026-07-14). "muéstrame el de mensajería" / "abre la
        # agenda" / "muéstrame el widget de fútbol": si el modelo rápido ESCALÓ (→ widget basura) o disparó
        # web_search (las palabras-tema «fútbol/resultados» ceban la búsqueda, hallazgo del test post-P1/P2) una
        # petición que en realidad es MOSTRAR un widget que YA EXISTE, lo resolvemos aquí: `_show_guard_target`
        # exige verbo de show + NO-crear + que `runtime.identify` (fuzzy por keywords, GENÉRICO) case un widget
        # real → override determinista de la tool espuria. Solo si no hubo ya una data-op efectiva.
        # Solo si el modelo emitió una tool ESPURIA (escalate/search) para lo que en realidad es MOSTRAR un widget
        # existente. (Se probó ampliarlo a CHARLA en el mar de testing 2026-07-19, pero los verbos 'pon/ver' del
        # guard colisionan con 'pon música'/'va a poner el tiempo'/'a ver si…' → hijack de web/deep/música. La cola
        # de show-promesa-en-charla la captura el Susurro, no un guard sobre-amplio.)
        if (escalate_req["v"] is not None or search_req["v"] is not None) and not acted["widget"]:
            _guard_wid = _show_guard_target(text, brain._window, brain._last_action)
            if _guard_wid:
                _was_search = search_req["v"] is not None
                escalate_req["v"] = None
                search_req["v"] = None
                acted["widget"] = True
                emit("widget", "show", extra={"id": _guard_wid, "src": "flash"})
                emit("brain", "🪟 show por guard determinista (tool espuria evitada)",
                     text=f"{_guard_wid} ({'search' if _was_search else 'escalate'}→show)", role="system")
                if not spoken_text:
                    try:
                        # V2-209 (impl PARALELA — cablear en AMBOS): abrir una tarjeta no es entregar un
                        # resultado. La decisión vive en `router_guards` para que los dos canales no puedan
                        # divergir.
                        from voice.engine.core import langs as _langs
                        from nucleo.flash import router_guards as _rg_show
                        spoken_text = _rg_show.show_ack(_langs.current_language(), _guard_wid)
                    except Exception:
                        spoken_text = "Aquí lo tienes."
                    send(speech.sanitize(spoken_text, drop_metadata=False))

        # BACKSTOP PROMESA-SIN-ACCIÓN UNIFICADO 2026-07-19 (mar de testing): ante fraseo CORTÉS/subjuntivo
        # («¿podrías…?», «deberías…», «sería genial que hicieras…», «me haría falta…») el modelo CHARLA una promesa
        # («me pongo con ello», «te lo abro», «voy a poner…») SIN llamar a la tool → causa nº1 de "dice que lo hace y
        # no lo hace". Gated por la promesa en la RESPUESTA (zaelar se comprometió) → re-derivamos la intención con
        # los clasificadores DETERMINISTAS. GENERALIZA sobre todas las conjugaciones (no se parchea verbo a verbo).
        # GUARD MARKETPLACE → NAVEGAR + MODIFICAR-WIDGET → GENERADOR (V2-057 2026-07-21): dos modos de fallo FIABLES
        # del no-razonador. (a) un marketplace NOMBRADO + intención de buscar exige ENTRAR y navegar (worker), no un
        # dato puntual de web_search. (b) cambiar el CÓDIGO/aspecto de un widget (color/columna/estilo) es trabajo
        # del generador, no una data-op ni un "no puedo". En ambos, si el turno no escaló ni tocó otra tool, escala.
        if (escalate_req["v"] is None and not acted["widget"] and not data_done["v"] and not music_req["v"]
                and (_router.looks_like_marketplace_nav(text) or _router.looks_like_modify_widget(text))):
            if search_req["v"] is not None:
                search_req["v"] = None
            escalate_req["v"] = text
            emit("brain", "🧭 escalada por guard (marketplace→navegar / modificar-widget→generador)",
                 text=text[:80], role="system")

        # BACKSTOP DE AVISO PROMETIDO (V2-146, impl PARALELA con el probe — cablear en AMBOS): el modelo prometió
        # el recordatorio en PROSA y no emitió la tag, así que `scheduled_jobs.created` salió vacío mientras el
        # turno decía «te avisaré el miércoles». El ejecutor de tags funciona y el prompt lo pide con todas las
        # letras: faltaba hacerlo cuando el modelo no lo hace. Solo con un momento RESOLUBLE — la función
        # devuelve "" ante cualquier expresión que no sea inequívoca, porque un aviso mal fechado no se nota
        # hasta el día que no suena.
        if spoken_text and not cron_seen["v"]:
            try:
                # V2-153: misma función que el probe. Ver su docstring — el duplicado nació justamente de que
                # cada canal decidía por su cuenta.
                _cron = _router.dated_reminder_backstop(spoken_text, operator_text, window=brain._window)
                if _cron:
                    from nucleo import scheduler as _sched_bk
                    _r = _sched_bk.create(_cron["prompt"], _cron["schedule"], name=_cron["name"])
                    emit("cron", "⏰ aviso programado por backstop (lo prometió sin emitir la tag)"
                         if _r.get("ok") else "⚠️ schedule no reconocido",
                         text=_r.get("display") or _r.get("error") or "", role="system",
                         extra={"ok": bool(_r.get("ok")), "op": "cron.create", "backstop": True})
            except Exception:
                pass

        # BACKSTOP DEL APUNTE CON FECHA (V2-159, espejo del probe — cablear en AMBOS). La OTRA mitad del mismo
        # encargo: el caso pide las dos cosas —el compromiso registrado y el aviso— y la corrida salió con el
        # cron puesto y ninguna cita. Solo si el turno no hizo ya una data-op.
        if spoken_text and not data_done["v"]:
            try:
                _note = _router.dated_note_backstop(spoken_text, operator_text, window=brain._window)
                if _note:
                    import widgets as _w_note
                    await _w_note.dispatch_tag("widget.data", {"id": "agenda", "data": {
                        "action": "add_meeting", "payload": _note}})
                    emit("widget", "🗓️ cita apuntada por backstop (lo prometió sin emitir la data-op)",
                         text=f"{_note['date']} · {_note['title']}", role="system",
                         extra={"id": "agenda", "act": "add_meeting", "backstop": True})
            except Exception:
                pass

        _no_tool = (not acted["widget"] and not data_done["v"] and not music_req["v"] and not worker_acted["v"]
                    and escalate_req["v"] is None and search_req["v"] is None)
        if _no_tool and spoken_text and _router.promises_action(spoken_text):
            _win_goal = ""
            if not (_router.looks_like_create_widget(text) or _router.looks_like_escalate_task(text)):
                # V2-132 — la petición puede ser de HACE UNOS TURNOS: zaelar pidió el dato que faltaba (correcto),
                # el operador se lo dio, y la promesa cayó en un turno cuyo texto por sí solo no describe tarea
                # ninguna («vale, avísame»). El backstop miraba solo ESTE turno, así que no podía dispararse — y
                # la corrida se fue en ocho turnos narrando una búsqueda que nunca arrancó. Solo con NADA vivo:
                # con una tarea en marcha, «sigo con ello» es honesto y re-escalar haría el trabajo dos veces.
                #
                # V2-176: «nada vivo» era la pregunta equivocada — la que decide es «nada vivo PARA ESTO».
                # Medido en `book-hotel-night-known__es`: el encargo del hotel no escaló porque seguía vivo un
                # worker del encargo ANTERIOR, y zaelar pasó cuatro turnos diciendo «la reserva sigue en marcha»
                # sobre una tarea de Ticketmaster ya cancelada. Espejo exacto del canal de texto; el predicado es
                # compartido (`router_guards.nothing_running_for`) y es CONSERVADOR: ante la duda, se comporta
                # como antes.
                try:
                    from nucleo import dispatch as _disp_wg
                    _cand = _router.escalate_goal_from_window(brain._window, text)
                    if _cand:
                        _live = [str(r.get("request") or "") for r in _disp_wg.pending_summaries()]
                        if not _disp_wg.has_active() or _router.nothing_running_for(_cand, _live):
                            _win_goal = _cand
                except Exception:
                    _win_goal = ""
            if _router.looks_like_create_widget(text) or _router.looks_like_escalate_task(text) or _win_goal:
                # crear widget (o sinónimo: panel/gadget) = código → escala; marketplace/informe = navegador → escala
                escalate_req["v"] = _win_goal or text
                emit("brain", "🧭 escalada por backstop (prometió crear/gestionar sin escalar)",
                     text=(_win_goal or text)[:80], role="system")
            elif _router.looks_like_show_strict(text):    # abrir/mostrar/enseñar un widget existente → show
                _pw = _identify(text)
                if _pw:
                    acted["widget"] = True
                    emit("widget", "show", extra={"id": _pw, "src": "flash"})
                    emit("brain", "🪟 show por backstop de promesa (prometió mostrar sin tool)", text=_pw, role="system")
            elif _router.promises_music(spoken_text):     # 'voy a poner algo de rock' sin tool → reproduce
                music_req["v"] = {"query": text, "action": "play"}
                emit("brain", "🎵 música por backstop de promesa (prometió poner música sin tool)", text=text[:80], role="system")

        # BACKSTOP DE TRABAJO DEVUELTO (V2-142). Distinto del de promesa: aquí el modelo no promete nada, MANDA
        # AL OPERADOR a buscar en Google/Maps lo que él acaba de pedir. Medido en `reorder-prescription`: «¿puedes
        # buscar tú el teléfono?, para eso te pido ayuda» → «la forma más fiable es que tú busques "farmacia" en
        # Google Maps y me pases el teléfono». Una regla de prompt no basta: lo que hace falta es HACER la
        # búsqueda. Solo si NADA corre (con una tarea viva la frase puede ser una sugerencia mientras se trabaja,
        # y re-escalar duplicaría el trabajo, V2-123).
        if (_no_tool and spoken_text and escalate_req["v"] is None
                and _router.hands_public_lookup_back(spoken_text)):
            try:
                from nucleo import dispatch as _disp_hb
                _busy = _disp_hb.has_active()
            except Exception:
                _busy = False
            if not _busy:
                escalate_req["v"] = _router.escalate_goal_from_window(brain._window, text) or text
                emit("brain", "🧭 escalada por backstop (devolvió la búsqueda al operador)",
                     text=text[:80], role="system")

        # BACKSTOP DETERMINISTA de CIERRE corto (sesión 22:40 2026-07-16): «Vale, ciérralo» → el modelo respondió
        # "Listo, cerrado" SIN emitir [[close]] ni tool alguna — la tarjeta quedó abierta y el operador tuvo que
        # repetirlo (T10 muteó, luego "no se está cerrando nada"). Orden CORTA que es claramente CERRAR (verbo de
        # cerrar, sin verbo de borrar, ≤5 palabras — `looks_like_close`, mismo guard que cerrar≠borrar) y el turno
        # NO cerró nada → cerramos AQUÍ: el widget que nombre el texto, o el ÚNICO abierto. Con varios abiertos y
        # sin nombre no adivinamos ("cierra todo" ya lo cubre `hard_interrupt`). Post-stream (la voz ya salió):
        # la lectura µs de `state.open_widgets` no toca la latencia del turno.
        # AMPLIADO (sesión absurda 2026-07-19): «Cierra el widget de música. Has puesto un videoclip…» (>5 palabras,
        # con queja) NO cazó el guard corto → el modelo ESCALÓ, y una escalada de "cerrar" cayó en el worker de
        # MODIFICAR código («modificando el widget musica…»), que giró 3 min leyendo fuentes mientras zaelar repetía
        # "sigo procesando el cierre" e ignoraba "ya está cerrado". Cerrar un widget NUNCA es tarea de código
        # (V2-017). Por eso: si hay verbo de CERRAR (sin borrar/crear) Y se NOMBRA un widget ABIERTO concreto,
        # cerramos AQUÍ aunque el turno sea largo, y CANCELAMOS cualquier escalada que el modelo haya pedido.
        # guardas contra verbos AMPLIOS ('apaga/quita'): si el turno ya disparó MÚSICA ('apaga la música'=stop
        # audio) o una data-op ('quita la tarea X'), NO cerramos el widget además (evita doble-acción).
        # BUG real 2026-07-23: "quita la pantalla completa" (verbo amplio 'quita' + turno corto + 1 solo widget
        # abierto) disparaba ESTE backstop y CERRABA el widget entero — el operador solo quería salir de
        # fullscreen. `fullscreen_widget` YA resolvió la intención real este turno; no lo pisa un cierre espurio
        # (mismo criterio que música/data-op de arriba: una acción real explícita gana sobre el backstop genérico).
        if (not acted.get("closed")) and _router.looks_like_close(text) \
                and not _router.looks_like_create_widget(text) \
                and not music_req["v"] and not data_done["v"] \
                and "fullscreen_widget" not in _tool_fired:
            try:
                from memory import api as _memapi
                _openw = list((_memapi.state() or {}).get("open_widgets") or [])
            except Exception:
                _openw = []
            _cw = None
            try:
                from widgets import runtime as _rt_close
                # los ABIERTOS desempatan ("cierra el vídeo": vídeo empata navegador↔youtube; gana el abierto)
                _idc = _rt_close.identify(text, open_ids=_openw) or {}
                # NOMBRE resuelto y NO ambiguo = cerramos aunque el turno sea largo (señal fuerte: cerrar + widget
                # nombrado). No exigimos que esté en open_widgets: el frontend puede no haberlo reportado y cerrar
                # uno ya cerrado es no-op inofensivo; el valor real es CANCELAR la escalada espuria.
                if not _idc.get("ambiguous"):
                    _cw = _idc.get("match")
            except Exception:
                _cw = None
            # sin nombre resuelto: solo el caso corto genérico ("ciérralo") con un único widget abierto.
            if not _cw and len(text.split()) <= 5 and len(_openw) == 1:
                _cw = _openw[0]
            if _cw:
                _t = _close_target(_cw)
                if _t["ask"]:                           # V2-259 F3
                    clarify["msg"] = _t["ask"]
                    emit("brain", "❓ cerrar: varias tarjetas abiertas", text=_cw, role="system",
                         extra={"options": _t["options"]})
                    if escalate_req["v"] is not None:
                        escalate_req["v"] = None
                    _cw = None
            if _cw:
                acted["widget"] = True
                acted["closed"] = True
                emit("widget", "close", extra={"id": _t["id"] or _cw, "src": "flash"})
                emit("brain", "🙈 close por backstop (cerrar widget nombrado sin [[close]])",
                     text=_cw, role="system")
                # cerrar un widget NO es tarea de worker → cancela la escalada espuria (evita el bucle de 3 min)
                if escalate_req["v"] is not None:
                    escalate_req["v"] = None
                    emit("brain", "🚫 escalada de cierre cancelada (cerrar ≠ tarea de código)", role="system")

        # REVELAR UN SECRETO (V2-060): el operador pidió un secreto guardado (reveal_secret). El valor se descifra
        # FUERA del event loop y se entrega OUT-OF-BAND: NUNCA entra en un prompt del modelo NI en el observer/logs.
        # En F1b zaelar IDENTIFICA el secreto y confirma/pide passphrase por voz (SIN el valor); el valor lo sirve la
        # API `/api/vault/reveal` (loopback) al frontend/tester. (Lectura del valor POR VOZ con redacción = F2.)
        if reveal_req["v"] is not None and escalate_req["v"] is None:
            _lblq = reveal_req["v"]
            emit("brain", "🔐 reveal_secret", text=_lblq, role="system")
            try:
                from nucleo.flash import vault_flow as _vf
                rv = await asyncio.to_thread(_vf.reveal, _lblq)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"reveal_secret falló (voz sigue): {e}")
                rv = {"status": "error"}
            from voice.engine.core import langs as _lgv
            _L = _lgv.current_language()
            _st = rv.get("status")
            if _st == "ok":
                # UI: muestra el valor (el frontend lo pide a /api/vault/reveal). El observer NO lleva el valor.
                # (claves `slabel`/`mid` — NO `label`, que pisaría el label del evento en observer.emit)
                emit("secret", "reveal", role="system",
                     extra={"slabel": rv["label"], "mid": rv.get("memory_id")})
                # F2: modo cómodo (default, el operador lo pidió) → lo DICE por voz; user rule dura
                # `secrets_voice=False` («no me digas los secretos por voz») → solo pantalla.
                try:
                    from memory import state as _stsec
                    _voice_ok = bool(_stsec.security_flag("secrets_voice", True))
                except Exception:
                    _voice_ok = True
                _line = (_L.secret_reveal.format(label=rv["label"], value=rv["value"]) if _voice_ok
                         else _L.secret_shown.format(label=rv["label"]))
            elif _st == "locked":
                emit("secret", "locked", role="system",
                     extra={"slabel": rv.get("label"), "mid": rv.get("memory_id")})   # → el frontend abre el modal
                _line = _L.secret_locked
            elif _st == "no_vault":
                emit("secret", "no_vault", role="system")
                _line = _L.secret_no_vault
            elif _st == "not_found":
                _cands = rv.get("candidates") or []
                _line = _L.secret_not_found + (f" Tengo: {', '.join(_cands)}." if _cands else "")
            else:   # empty | error
                _line = _L.secret_not_found
            buf = ""   # descarta restos de tags del 1er pase
            send(speech.sanitize(_line, drop_metadata=False))
            spoken_text = "".join(spoken).strip()

        # RECALL DE MEMORIA por tool (V2-056): ruta LIGERA hermana de web_search — memory.query FUERA del event
        # loop (to_thread, V2-011) + 2º pase con los recuerdos (el modelo que el turno ya paga). Solo si el turno
        # no escaló (el worker recibe su propio dossier) ni buscó (una sola respuesta compuesta por turno).
        if recall_req["v"] is not None and escalate_req["v"] is None and search_req["v"] is None \
                and reveal_req["v"] is None:
            rquery = recall_req["v"]
            emit("brain", "🧠 recall por tool", text=rquery, role="system")
            _t_r = time.time()
            try:
                rblock, _rids = await asyncio.to_thread(_prompt_mod.compose_recall, rquery)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"recall tool falló (voz sigue): {e}")
                rblock = ""
            emit("memory", "recall (tool del modelo)", role="system", text=rquery,
                 extra={"layer": "long", "chars": len(rblock or ""),
                        "mem_ms": round((time.time() - _t_r) * 1000)})
            sys2r = (
                _prompt_mod._lang_lock()
                + "\nNecesitabas RECORDAR cosas del operador para este turno; aquí están tus recuerdos "
                "relevantes. Responde a su petición en 1-3 frases HABLADAS y naturales usando SOLO lo que dan de "
                "sí los recuerdos y la conversación; si falta algo, dilo con naturalidad y pregunta lo que "
                "necesites. JAMÁS menciones «memoria», «recuerdos guardados» ni capas internas — hablas como "
                "quien simplemente se acuerda.\n\n"
                f"PETICIÓN DEL OPERADOR: {text}\n\nLO QUE SABES DE ÉL:\n{rblock or '(nada relevante guardado)'}"
            )
            buf = ""   # descarta restos de tags del 1º pase
            try:
                async for delta in FastClient().stream(
                        [{"role": "system", "content": sys2r}, {"role": "user", "content": text}],
                        spec=spec, max_tokens=260):
                    buf += delta
                    send(speech.inline(take(False)))
                send(speech.sanitize(take(True), drop_metadata=False))
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning(f"recall compose falló (voz sigue): {e}")
            spoken_text = "".join(spoken).strip()

        # BÚSQUEDA WEB FACTUAL (V2-022): ruta LIGERA — se resuelve EN ESTE turno (NO es el navegador pesado del
        # SlowBrain). La búsqueda es I/O de red → FUERA del event loop (to_thread). La EXTRACCIÓN reusa el MISMO
        # modelo rápido que el turno ya paga (coste marginal ≈0): 2º pase con los snippets como contexto →
        # respuesta hablada. Proveedor por capas (calidad primero): respuesta-IA (Perplexity/Tavily) → snippets
        # (Brave) → gratis (DDG). Compartido con el SlowBrain. Ver nucleo/websearch.py.
        # V2-210 — AQUÍ NO. El backstop de «un dato del mundo no se improvisa» vive en el canal de texto
        # (`probe.py`) y este canal se queda FUERA a propósito, que es lo contrario de lo que pide la regla de
        # implementación paralela y por eso se escribe.
        #
        # La razón es una asimetría real entre los dos canales: la voz EMITE los deltas del modelo según llegan,
        # así que cuando el turno llega hasta aquí la frase inventada YA SE HA DICHO. Sustituirla es imposible y
        # añadir la versión con fuente detrás significa hablar dos veces en toda pregunta de horarios o precios
        # — una regresión en el canal del operador, cambiada por un defecto que en este canal nadie ha medido.
        #
        # El arreglo BUENO para la voz es el mismo disparo pero ANTES de generar (si la pregunta es de un dato
        # del mundo, se busca primero y el modelo compone con los resultados), que es además lo que el modelo
        # hace cuando acierta. Eso toca `_run_inner` antes del stream y quiere su propia medición de latencia.
        if search_req["v"] is not None and reveal_req["v"] is None:
            query = search_req["v"]
            emit("brain", "🔎 búsqueda web", text=query, role="system")
            _t_s = time.time()
            try:
                from nucleo import websearch as _ws
                res = await asyncio.to_thread(_ws.search, query)
                ctx = _ws.format_results(res)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"web_search falló (voz sigue): {e}")
                res, ctx = {"source": "none", "results": []}, ""
            # EVIDENCIA (2026-08-10): además del proveedor y el número, se guarda QUÉ VOLVIÓ — título, URL y un
            # trozo del snippet de cada resultado, más la respuesta sintetizada si el proveedor la dio. Sin esto
            # se podía auditar que el sistema BUSCÓ, nunca si respondió con lo que traía: la fila decía «7
            # resultados» y el contenido que el modelo leyó se perdía para siempre. Presupuestada en
            # `observability.evidence` (se recorta, no se resume) y best-effort: si falla, el evento sale igual.
            _ev = {"source": res.get("source"), "ai": bool(res.get("ai")),
                   "n": len(res.get("results", [])), "ms": round((time.time() - _t_s) * 1000)}
            try:
                from observability import evidence as _evd
                _ev["evidence"] = _evd.web_results(res.get("results"))
                _ans = _evd.body(res.get("answer"))
                if _ans:
                    _ev["evidence"]["answer"] = _ans
            except Exception:
                pass
            emit("search", "🔎 resultados web", text=query, role="system", extra=_ev)
            _hoy = time.strftime("%A %d %b %Y (%Y-%m-%d)")
            sys2 = (
                _prompt_mod._lang_lock()
                + f"\nHOY es {_hoy}. El operador preguntó algo que requería BUSCAR en la web. Con estos RESULTADOS, "
                "responde a su pregunta en 1-2 frases HABLADAS: natural, sin markdown, sin emojis, sin leer URLs ni "
                "números de fuente. Si la pregunta es SENSIBLE A LA FECHA (el tiempo, una cotización, un resultado, "
                "algo «de hoy/ahora»): da el dato VIGENTE anclado a HOY y de aquí en adelante (nunca uno caducado; "
                "el tiempo, de ahora en adelante, no el de ayer), y si procede menciona el día. Si los resultados "
                "NO contienen la respuesta clara o no son de la fecha correcta, dilo con naturalidad y ofrécete a "
                "mirarlo a fondo — NO inventes datos que no estén en los resultados. "
                # V2-135 (impl PARALELA con el probe — cablear en AMBOS): este pase veía la QUERY como si fuera
                # la pregunta, y la query es la reformulación del propio modelo. «¿A qué hora abre mañana el
                # Museo del Prado Y cuánto cuesta la entrada general?» buscado como «horario Museo del Prado»
                # llegaba aquí como una pregunta de UN dato: la mitad del precio ya no existía antes de componer.
                "Contesta TODO lo que preguntó (si pidió dos datos, los dos); si los resultados solo cubren una "
                "parte, di CUÁL falta y ofrécete a mirarla — no la dejes caer en silencio.\n\n"
                f"PREGUNTA DEL OPERADOR: {operator_text}\n"
                f"BÚSQUEDA REALIZADA: {query}\n\nRESULTADOS DE BÚSQUEDA:\n{ctx or '(sin resultados)'}"
            )
            buf = ""   # descarta cualquier resto de tags del 1º pase antes de componer la respuesta
            try:
                async for delta in FastClient().stream(
                        [{"role": "system", "content": sys2},
                         {"role": "user", "content": operator_text or query}],
                        spec=spec, max_tokens=240):
                    buf += delta
                    send(speech.inline(take(False)))
                send(speech.sanitize(take(True), drop_metadata=False))
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning(f"web_search compose falló (voz sigue): {e}")
            spoken_text = "".join(spoken).strip()
            brain._last_action = "search"

        # MÚSICA (V2-041/V2-042): ruta LIGERA como web_search, ahora con la CADENA resolver→validar→actuar
        # (`nucleo/flash/music_flow`): intento directo → si no_track, websearch (Chromium CALIENTE del prewarm) +
        # 2º pase del modelo que el turno ya paga (extractor 'Artista - Título') → reintento. El estado del intento
        # vive en las ACTIVIDADES (buscando / sonando / sin_resolver AISLADA con intentos → el turno siguiente la
        # continúa con más datos) y cada reproducción se vuelca a memoria (source="music" → gustos/historial).
        # Todo el I/O va FUERA del event loop (to_thread, V2-011). Se dice el mensaje si (a) falló, (b) el modelo
        # no habló (nunca mudo), o (c) la cadena RESOLVIÓ otra cosa que lo dicho (validación por anuncio).
        if music_req["v"] is not None:
            mq = music_req["v"]
            emit("brain", "🎵 música", text=f"{mq.get('action')} {mq.get('query')}".strip(), role="system")
            _t_m = time.time()

            async def _extract(sys2: str, user2: str) -> str:
                """2º pase INTERNO (no se habla): mismo modelo del turno, respuesta corta y estricta."""
                out: list[str] = []
                async for d in FastClient().stream([{"role": "system", "content": sys2},
                                                    {"role": "user", "content": user2}],
                                                   spec=spec, max_tokens=40):
                    out.append(d)
                return "".join(out)

            try:
                from nucleo.flash import music_flow as _mflow
                res = await _mflow.run(mq.get("action") or "play", mq.get("query") or "", extract=_extract)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"play_music falló (voz sigue): {e}")
                res = None
            # Ejecuta el FOLLOWUP de control (volumen/pausa) tras un play/queue OK — en SECUENCIA, nunca antes
            # (bug real 2026-07-23, ver comentario en el collapse de arriba). Fail-open: si falla, el play ya
            # dicho/hecho no se deshace; solo no se aplica el ajuste.
            if music_req.get("followup") and bool(getattr(res, "ok", False)):
                try:
                    await _mflow.run(music_req["followup"]["action"], "", extract=None)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"play_music followup falló: {e}")
            ok = bool(getattr(res, "ok", False))
            msg = (getattr(res, "message", "") or "").strip()
            _extra = getattr(res, "extra", {}) or {}
            _resolved = bool(_extra.get("resolved_from"))
            emit("music", "🎵 acción de música", text=mq.get("query") or mq.get("action"), role="system",
                 extra={"provider": getattr(res, "provider", ""), "action": mq.get("action"),
                        "ok": ok, "reason": getattr(res, "reason", ""), "surface": _extra.get("surface", ""),
                        "resolved_from": _extra.get("resolved_from", ""),
                        "ms": round((time.time() - _t_m) * 1000)})
            # Audio EN EL NAVEGADOR (fallback YouTube): la reproducción vive en el widget `musica` → hay que
            # MOSTRARLO para que su iframe oculto se monte y suene (Spotify no lo necesita: suena en el dispositivo).
            if ok and _extra.get("surface") == "widget" and _extra.get("widget"):
                emit("widget", "show", extra={"id": _extra["widget"], "src": "flash"})
            # No re-anunciar un no-op (F5): si la reproducción fue "ya suena eso", el modelo ya habló; no encajes
            # el "ya está sonando" salvo que el modelo callara.
            _is_noop = bool(_extra.get("noop"))
            if msg and (not ok or not spoken_text or _resolved) and not (_is_noop and spoken_text):
                _clean = speech.sanitize(msg, drop_metadata=False)
                # HIGIENE (V2-047 F11, sesión 23:15 «…sin pausa.Con esta fuente gratis…»): el msg del conector se
                # concatenaba al texto del modelo SIN separador → dos frases pegadas. Si ya hay locución y no cierra
                # con espacio/puntuación, antepón un separador.
                if spoken_text and _clean and spoken_text[-1:] not in " \n.,;:!?¡¿—-":
                    _clean = " " + _clean
                elif spoken_text and _clean and not _clean[:1].isspace():
                    _clean = " " + _clean
                send(_clean)
                spoken_text = "".join(spoken).strip()

        # RED DETERMINISTA de confirmación (V2-017): si había un borrado pendiente y el modelo NO lo resolvió por
        # tool, pero el operador dijo claramente sí/no → resuélvelo igual (no depende del LLM, como hard_interrupt).
        if had_pending_confirm and not confirm_state["handled"]:
            try:
                from widgets import confirm as _confirm_mod
                verdict = _confirm_mod.classify_reply(text)
                if verdict:
                    _resolve_confirm(verdict == "yes")
            except Exception:
                pass

        # …y lo mismo para una TAREA irreversible parada por el confirm-gate (V2-126). MISMO clasificador
        # determinista, distinto registro: aquel resuelve una acción de widget, este re-lanza la tarea. Va
        # DESPUÉS y solo si no había confirmación de widget, para que un único «sí» no resuelva dos cosas.
        # Sin esto el gate era un callejón sin salida: nadie ponía nunca `context["confirmed"]`, así que el sí
        # del operador no tenía a qué volver y la acción quedaba parada para siempre sin decirlo.
        if not had_pending_confirm and not worker_acted["v"]:
            try:
                from nucleo import dispatch as _disp_cc
                if _disp_cc.pending_confirm():
                    from widgets import confirm as _confirm_mod2
                    _v = _confirm_mod2.classify_reply(text)
                    if _v:
                        _r = _disp_cc.resolve_confirm(_v == "yes")
                        if _r:
                            escalate_req["v"] = None      # el sí NO abre una tarea nueva: reanuda la parada
                            escalate_req["more"] = []
                            emit("brain", "✅ confirmación de tarea resuelta" if _r.get("ok")
                                 else "🚫 tarea irreversible descartada por el operador",
                                 text=_r.get("request", "")[:120], role="system", extra={"cat": "flash"})
            except Exception:
                pass

        # …y la TERCERA puerta con la misma llave (V2-202): el navegador parado en un clic irreversible. Aquel
        # re-lanza una tarea; este desbloquea un clic que está esperando AHORA MISMO dentro del navegador. Mismo
        # orden y misma razón: solo si el «sí» no ha resuelto ya otra cosa.
        if not had_pending_confirm and not worker_acted["v"]:
            try:
                from widgets.navegador import tasks as _nt_cc
                _ra = _nt_cc.answer_from_turn(text)
                if _ra:
                    escalate_req["v"] = None          # contesta a lo parado; no abre nada nuevo
                    escalate_req["more"] = []
                    emit("brain", "✅ clic confirmado por el operador" if _ra["ok"]
                         else "🚫 clic descartado por el operador",
                         text=_ra["task_id"], role="system", extra={"cat": "flash"})
            except Exception:
                pass

        # RED DETERMINISTA V2-038 (§v3·M): precedencia confirm > ask-activo > stop-worker. Si un worker ESPERABA
        # respuesta y el modelo NO llamó answer_worker → enruta el turno como la respuesta (el estado ya lo marcaba).
        # SOLO una "respuesta libre CORTA" (§v3·M): si el turno YA disparó otra acción (widget/búsqueda/escalada/
        # data-op), es largo, o hay un login pendiente (rango superior en la precedencia), NO se lo tragamos como
        # respuesta al worker — el modelo siempre puede enrutar explícito con answer_worker.
        # PRECEDENCIA (2026-07-17, ronda 3): si un worker ESPERA respuesta, un turno corto ES esa respuesta —
        # AUNQUE el modelo haya mis-ruteado a escalate (gpt-4o-mini escaló "sí, el jueves para dos" en vez de
        # answer_worker). Coincide con la doctrina del propio prompt (_flash_layer: "lo que diga el operador es esa
        # respuesta"). Se responde al worker Y se CANCELA la escalada espuria (no abrir una tarea nueva). No aplica
        # si el turno disparó otra acción clara (widget/data/confirm/auth) o es largo (posible tarea nueva genuina).
        if _ask_waiting and worker_acted["v"] != "answer" and not had_pending_confirm \
                and search_req["v"] is None and not acted["widget"] \
                and not data_done["v"] and not _auth_pending and len(text) <= 140:
            try:
                from nucleo import worker_api as _wapi2
                if _wapi2.answer_active_soon(text):
                    worker_acted["v"] = "answer"
                    escalate_req["v"] = None        # respondía al worker, no pedía tarea nueva → no escalar
                    if not spoken_text:
                        spoken_text = "Vale, se lo digo."
                        send(speech.sanitize(spoken_text, drop_metadata=False))
            except Exception:
                pass
        # Backstop de PARADA: hay workers vivos, el operador pidió parar trabajo y el modelo NO llamó stop_worker.
        if worker_acted["v"] not in ("stop",) and escalate_req["v"] is None:
            try:
                from nucleo import dispatch as _disp2
                if _disp2.has_active() and _router.looks_like_stop_work(text):
                    tids = _disp2.cancel_soon(text)
                    if tids:
                        worker_acted["v"] = "stop"
                        emit("brain", "🛑 stop worker (backstop determinista)", text=str(tids), role="system")
                        # Un kill SIEMPRE se anuncia por voz (demo 2026-07-14: se mató el worker del widget en
                        # silencio mientras la voz decía "no te he entendido" — incoherente). Si el modelo ya
                        # habló otra cosa, se AÑADE la frase; nunca un kill mudo.
                        _ack = "Vale, lo paro." if not spoken_text else " He parado esa tarea."
                        send(speech.sanitize(_ack, drop_metadata=False))
                        spoken_text = (spoken_text + _ack) if spoken_text else _ack.strip()
            except Exception:
                pass

        # Confirmación abierta este turno sin que el modelo formulara la pregunta → la decimos nosotros (nunca
        # mudo; el overlay Sí/No ya está en la tarjeta). Cubre borrado y data-op irreversible (V2-025).
        if confirm_state.get("opened") and not spoken_text and escalate_req["v"] is None \
                and search_req["v"] is None:
            spoken_text = confirm_state["opened"]
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # Referencia a item sin resolver (V2-026) → preguntamos SIEMPRE, aunque el modelo ya haya dicho algo.
        # Bug real (maratón de testing 2026-07-22): la condición exigía `not spoken_text` — si el turno NO
        # resolvió a qué item se refería (agenda:done:"comprar pan" cuando esa tarea nunca se creó) pero el
        # modelo YA había soltado una frase confiada ("Entendido, marca la tarea como hecha"), esa frase
        # FALSA ganaba y la pregunta real ("¿cuál? no lo tengo claro") nunca llegaba a hablarse — la señal
        # determinista de "no sé a qué te refieres" quedaba silenciada por la propia alucinación del modelo,
        # justo el "nunca mudo" que el comentario original quería garantizar. `clarify["msg"]` solo se fija
        # cuando la referencia genuinamente NO resolvió — es un hecho duro, nunca debe perder frente a lo que
        # el modelo diga por su cuenta.
        if clarify["msg"] and escalate_req["v"] is None and search_req["v"] is None:
            spoken_text = clarify["msg"]
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # Data-op despachada por tool sin frase hablada (el modelo fue directo a la tool) → ack corto (no mudo).
        # V2-038 (test post-P1/P2): dos data-ops seguidas con el MISMO "Hecho." disparaban el loop-detector — se
        # elige una variante que NO repita el último ack hablado (funcional consecutivo = se dice distinto).
        if data_done["v"] and not spoken_text and escalate_req["v"] is None and search_req["v"] is None:
            try:
                from voice.engine.core import langs as _langs
                _lg = _langs.current_language()
                _acks = list(getattr(_lg, "data_acks", None) or (_lg.data_ack,))
                _last = _dialog.sanitize_reply(brain._last_spoken or "").strip().lower()
                spoken_text = next((a for a in _acks if a.strip().lower() != _last), _acks[0])
            except Exception:
                spoken_text = "Hecho."
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # Regla de usuario fijada/retirada SIN frase hablada → ack corto (V2-046 A1, visto en el probe: la
        # RETIRADA dejaba el turno MUDO). Nunca mudo al aceptar/quitar una regla.
        if style_fired["v"] and not spoken_text and escalate_req["v"] is None and search_req["v"] is None:
            try:
                from voice.engine.core import langs as _langs
                spoken_text = _langs.current_language().data_ack
            except Exception:
                spoken_text = "Vale, lo tengo."
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # SHOW/CLOSE de canvas por tag SIN frase hablada → ack corto (bug 2026-07-13: el modelo emitía [[show:agenda]]
        # sin decir nada → turno MUDO; el operador no oía NI veía nada y creía que estaba roto). Nunca mudo al abrir/
        # cerrar un widget.
        if acted["widget"] and not spoken_text and escalate_req["v"] is None and search_req["v"] is None \
                and not confirm_state.get("opened") and not clarify["msg"]:
            try:
                from voice.engine.core import langs as _langs
                from nucleo.flash import router_guards as _rg_show2
                spoken_text = _rg_show2.show_ack(_langs.current_language(), str(acted.get("widget_id") or ""))
            except Exception:
                spoken_text = "Aquí lo tienes."
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # Escalada sin texto hablado en el mismo turno → frase de espera neutral (no mudo). V2-029: si YA había una
        # tarea de fondo en curso al empezar el turno, VARÍA la frase ("sigo con ello") en vez de repetir la misma.
        if escalate_req["v"] is not None and not spoken_text:
            # el lead-in ("a ver…") NO cuenta como contenido → aquí sí decimos la frase de espera CON sentido
            # ("vale, dame un momento que lo miro"): juntas suenan naturales ("a ver… vale, dame un momento").
            try:
                from voice.engine.core import langs
                _lg = langs.current_language()
                # V2-189: nunca la MISMA frase dos veces (espejo del probe — cablear en AMBOS). `_prev_pending`
                # solo distinguía la primera de las demás; a partir de la tercera, todas eran idénticas.
                from nucleo.flash import router_guards as _rg_hold
                spoken_text = _rg_hold.holding_line(brain._window, _lg)
            except Exception:
                spoken_text = "Sigo con ello." if _prev_pending else "Vale, dame un momento."
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # BACKSTOP GENÉRICO — turno de CHARLA pura que salió MUDO: ninguna tool se disparó (ninguno de los
        # backstops de arriba — widget/data/style/confirm/clarify/escalada — encontró algo que resolver) Y el
        # modelo no dijo NADA. Live bug (search-buy-used-car, 2026-08-17): tras varios check-ins con un worker
        # corriendo, un turno de charla pura ("¿pudiste relanzarla?") volvió del modelo genuinamente vacío; como
        # todo backstop anterior está gateado a SU propia acción, ninguno cubría este caso — el operador se
        # quedó sin respuesta, y el turno SIGUIENTE, viendo ese hueco en la ventana, acabó ECOANDO la propia
        # pregunta del operador palabra por palabra. Último recurso: si a estas alturas sigue sin haber nada
        # que decir, dilo con sentido según si hay trabajo de fondo en marcha. Espejo del backstop genérico de
        # `probe.py` (impl PARALELA, cablear en AMBOS).
        if not spoken_text:
            try:
                from voice.engine.core import langs
                spoken_text = langs.current_language().filler_still_working if _prev_pending \
                    else "Perdona, ¿me lo repites?"
            except Exception:
                spoken_text = "Sigo con ello." if _prev_pending else "Perdona, ¿me lo repites?"
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # push_user (no append pelado): si el turno ANTERIOR se canceló por solape, su frase ya está registrada y
        # ésta suele ser su versión acumulada por el STT → se sustituye en vez de duplicar el prefijo.
        _dialog.push_user(brain._window, text)
        if spoken_text:
            # Guarda la respuesta SANEADA (anti-degeneración V2-032): si el modelo empalmó/repitió, no reinyectamos
            # esa basura al turno siguiente → cortamos el bucle de realimentación que degrada al modelo pequeño.
            brain._window.append({"role": "assistant", "content": _dialog.sanitize_reply(spoken_text)})
        del brain._window[:-_WINDOW_MAX]
        if not first_turn:
            brain._turn_count += 1   # INI-018 T6: solo turnos conversacionales reales cuentan para el cap demo

        # GATE de los FALLBACKS deterministas: el safety-net de widget y el login-fallback son SOLO para PURA CHARLA
        # en la que el modelo se olvidó de emitir la tag. Si el turno YA se resolvió por CUALQUIER tool (música,
        # vídeo, data-op, escalada, búsqueda, worker, estilo, confirm), NO deben re-adivinar nada — ese doble-disparo
        # abría un widget que nadie pidió (bug 17-jul: «necesito que PONgas a Bruce Springsteen» → play_music OK,
        # pero el safety-net corrió igual, el regex `\bpon` casó "pongas" e `_identify` fuzzy-casó ruido → show:clock
        # espurio). music/video no marcaban acted["widget"], por eso hay que mirar TODAS las señales de tool.
        _tool_handled = bool(
            acted["widget"] or data_done["v"] or worker_acted["v"] or style_fired["v"]
            or escalate_req["v"] is not None or search_req["v"] is not None
            or music_req["v"] is not None or "play_video" in _tool_fired
            or confirm_state.get("opened") or confirm_state.get("handled"))

        # SAFETY NET (PRIMERO): el modelo a veces DICE que abre/cierra un widget sin emitir la tag → la emitimos
        # nosotros. Va ANTES del login-fallback a propósito (V2-023): "abre mensajería y dime si WhatsApp está
        # conectado" es un SHOW de widget, NUNCA un login — así el login-fallback no roba un turno de widget.
        if not _tool_handled:
            if _widget_fallback(text, emit, ask=lambda m: clarify.__setitem__("msg", m)):
                acted["widget"] = True

        # LOGIN FALLBACK (V2-022): "conéctame a X" / "inicia sesión en mi Y" que el modelo NO accionó (se despistó
        # y solo charló) → abrimos el login igualmente (determinista, espejo del guard auth-vs-tarea). Solo si no
        # hubo ya otra acción de widget (el safety-net de arriba ya resolvió un show/close) y NO es una tarea.
        _login_started = False
        if not _tool_handled and not acted["widget"]:
            try:
                from nucleo.flash import router as _router
                if _router.looks_like_login_request(text) and _start_web_auth(_router.login_site(text)):
                    _login_started = True
                    emit("brain", "🔐 login por fallback (el modelo no disparó la tool)", text=text[:80], role="system")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"login fallback skipped: {e}")

        # BUFFER CONVERSACIONAL de CORTO (V2-013 T131): guardamos el par turno↔respuesta como working set EFÍMERO
        # (`kind='conv'`, TTL corto, importancia baja) — alimenta la ruta de lectura entera de CORTO (T146,
        # `recent_short`) para que el FlashBrain vea "de qué hablábamos", pero NO es un recuerdo durable. El
        # CORAZÓN que DESTILA lo memorable (nombre, hechos, preferencias) es `memory_agent.ingest_utterance`
        # (arriba, off-hot-path). El consolidador (V2-019) poda este buffer por TTL. Reemplaza el write crudo 0.3
        # a ciegas que inflaba la memoria. Best-effort: la memoria no está en el camino crítico de tiempo real.
        # V2-049: se escribe TAMBIÉN en los turnos que ESCALAN (antes se excluían con `escalate_req is None`) — así
        # el turno que LANZA la tarea (y el dato que el operador soltó en él: matrícula, email…) entra en
        # `recent_window` y el worker lo VE en su bloque de CONVERSACIÓN RECIENTE. Ese hueco hacía que el worker
        # investigara sin el dato y lo re-preguntara (bug ITV 17-jul). Si escaló sin hablar, guardamos igual el
        # turno del operador (con lo que dijera zaelar, aunque sea un filler).
        if spoken_text or escalate_req["v"] is not None:
            try:
                from memory import api as memory
                _a = spoken_text or "(me pongo con ello)"
                memory.write(f"Operador: {text[:200]} · zaelar: {_a[:200]}",
                             kind="conv", level="short", importance=0.2, ttl_days=2.0,
                             # u/a estructurados → `memory.recent_window` reconstruye la ventana verbatim sin
                             # parsear el string (circuito de corto plazo, 2026-07-14).
                             meta={"source": "conv", "u": text[:400], "a": _a[:400]})
            except Exception:
                pass

        # (el `health_state.clear("llm")` que había aquí se movió a `fast_client.stream`, al primer chunk que llega:
        #  este punto solo lo alcanza el turno CONVERSACIONAL, y los de solo-tool/show/fragmento se lo saltaban)
        # OBSERVABILIDAD DEL MODELO (FASE 0): TTFT + latencia + TOTALIZADORES de tamaño (chars/tokens de entrada y
        # salida) + cold/warm. Con esto distinguimos «lento por el modelo» de «lento por prompt gigante» y «frío por
        # cold-start». El desglose de QUÉ infla el prompt (system/memoria/reciente/recall/recursos) va en `timings`.
        _fast_ms = round((time.time() - t0) * 1000)
        _reply_extra = {
            "ttft_ms": first_ms, "fast_ms": _fast_ms,
            "gen_ms": llm_metrics.get("total_ms"),
            "prompt_ms": timings.get("prompt_ms"), "mem_state_ms": timings.get("mem_state_ms"),
            "mem_query_ms": timings.get("mem_query_ms"), "briefs_ms": timings.get("briefs_ms"),
            "live_ms": timings.get("live_ms"),
            # TOTALIZADORES de tamaño (premisa del operador)
            "prompt_chars": llm_metrics.get("prompt_chars"), "system_chars": llm_metrics.get("system_chars"),
            "prompt_tokens": llm_metrics.get("prompt_tokens", llm_metrics.get("prompt_tokens_est")),
            "completion_tokens": llm_metrics.get("completion_tokens", llm_metrics.get("completion_tokens_est")),
            "completion_chars": llm_metrics.get("completion_chars"),
            "n_tools": llm_metrics.get("n_tools"), "tools_chars": llm_metrics.get("tools_chars"),
            "n_msgs": llm_metrics.get("n_msgs"), "usage_source": llm_metrics.get("usage_source"),
            # desglose de QUÉ hace grande el prompt (chars por bloque)
            "sz_memory": timings.get("sz_memory"), "sz_recent": timings.get("sz_recent"),
            "sz_recall": timings.get("sz_recall"), "sz_resources": timings.get("sz_resources"),
            "sz_live": timings.get("sz_live"), "window_msgs": len(brain._window),
            # cold-start (FASE 1)
            "cold_estimate": llm_metrics.get("cold_estimate"), "gap_since_last_s": llm_metrics.get("gap_since_last_s"),
            # tokens/seg (throughput del modelo, independiente del tamaño)
            "tok_per_s": (round((llm_metrics.get("completion_tokens") or llm_metrics.get("completion_tokens_est") or 0)
                                / max(0.001, (llm_metrics.get("total_ms") or 0) / 1000.0), 1)
                          if llm_metrics.get("total_ms") else None),
            "escalated": bool(escalate_req["v"] is not None),
            "searched": bool(search_req["v"] is not None),
            "recent_fired": timings.get("recent_fired"), "recall_fired": timings.get("recall_fired"),
            # FASE 3: contención local activa al arrancar el turno (para correlacionar con el TTFT)
            "busy_at_start": _busy_at_start or None, "contended": bool(_busy_at_start),
            "engine": spec.provider, "model": spec.model,
        }
        emit("brain", "⚡ Nucleo(flash): reply", text=spoken_text, role="assistant", extra=_reply_extra)
        # …y el VEREDICTO en una línea legible: si el turno pasó del listón, POR QUÉ (prompt grande / proveedor /
        # frío / trabajo real). Los números ya estaban todos en `_reply_extra`, pero enterrados en el extra: había
        # que exportar el jsonl para saber si un turno de 8 s fue culpa nuestra o del proveedor.
        try:
            from nucleo.flash import turn_perf as _perf
            _v_perf = _perf.emit_verdict({**_reply_extra, "total_ms": _fast_ms})
            # …y ese veredicto ALIMENTA el relevo por latencia (V2-094). El circuito no vuelve a medir nada: lee la
            # causa que acaba de decidirse. `note_slow` exige turnos lentos SEGUIDOS, tiene cooldown corto y techo
            # de turnos en el escalón de relevo — un turno lento no puede convertirse en una factura sorpresa.
            # Cambia el titular para los turnos SIGUIENTES; el actual ya está entregado.
            from nucleo.flash import provider_chain as _pchain
            _pchain.note_slow(_v_perf, role=_pchain.ROLE_VOICE)
        except Exception:
            pass

        # CAPTURA FORENSE del turno (V2-040): prompt + ventana + tools + decisión, en categoría `system` (fichero,
        # no floodea el visor) — para diagnosticar a futuro cosas como la re-escalada en un turno ambiente.
        try:
            emit_turn = getattr(__import__("voice.observer", fromlist=["turn_detail"]), "turn_detail")
            emit_turn(system=system, window=_dialog.prune_window(brain._window)[-_WINDOW_MAX:], tools=_turn_tools,
                      user=text, decision={
                          "escalated": bool(escalate_req["v"] is not None), "escalate_req": (escalate_req["v"] or "")[:200],
                          "searched": bool(search_req["v"] is not None), "widget_acted": acted["widget"],
                          "worker_acted": worker_acted["v"], "data_done": data_done["v"],
                          "confirm_opened": bool(confirm_state.get("opened")), "clarify": bool(clarify["msg"]),
                          "shown_ids": sorted(_shown_ids), "reply": (spoken_text or "")[:400]},
                      extra={"turn_ms": _reply_extra.get("total_ms")})
        except Exception:
            pass

        # BACKSTOP DE ORDEN IRREVERSIBLE (V2-128, medido). «Paga la factura de la luz antes del día 5» acabó
        # creando un RECORDATORIO: el operador tuvo que corregir («no quiero un recordatorio, quiero que la
        # pagues tú»). Una orden de pagar/comprar/cancelar es del mundo real y su sitio es una tarea — que
        # además pasa por el confirm-gate, que es la conducta que estos casos puntúan BIEN. Apuntarla en la
        # agenda no la ejecuta y deja al operador creyendo que sí.
        # `danger.is_dangerous` es el MISMO clasificador que decide el gate, así que backstop y puerta no pueden
        # discrepar; y ya recorta los recados («recuérdame pagar…» NO es una orden de pagar).
        if (escalate_req["v"] is None and not worker_acted["v"] and not confirm_state.get("opened")):
            try:
                from nucleo import danger as _danger_bk
                if _danger_bk.is_dangerous(text):
                    escalate_req["v"] = text
                    emit("brain", "🛑 orden irreversible sin escalar → tarea (pasará por el confirm-gate)",
                         text=text[:120], role="system", extra={"cat": "flash"})
            except Exception:
                pass

        # Escala DESPUÉS de que el texto del turno rápido va camino de TTS. NO escala si ya se dirigió a un worker
        # vivo (inject/stop/answer) este turno.
        if escalate_req["v"] is not None and not worker_acted["v"]:
            req = escalate_req["v"] or text
            # V2-038 §v3·G: si una tarea MUY parecida ya está EN CURSO, esto es un REFINAMIENTO → se INYECTA a esa
            # sesión (no se descarta como antes, ni se abre otra). Reemplaza el dedup-descartar de V2-029.
            if _similar_pending(req, _prev_pending):
                try:
                    from nucleo import dispatch as _disp3
                    _disp3.inject_soon(req, req)
                    emit("brain", "↪️ refinamiento → inyección a worker vivo (no relanza)", text=req, role="system")
                except Exception:
                    emit("brain", "🧭 escalada duplicada ignorada", text=req, role="system")
            else:
                # V2-113: mark THIS trace as just-escalated BEFORE publishing, so `_maybe_close_flow` (which runs
                # moments later, still inside this same turn) doesn't close the flow while `dispatch.run_listener`
                # hasn't had a scheduler turn to register/reject/dedup it yet — see `_flow_should_close`.
                try:
                    from voice import trace as _trace5
                    brain._escalated_trace_id = _trace5.current()
                except Exception:
                    pass
                _escalate_mod.escalate_to_slowbrain(
                    req, context={"src": "voice", "surface": escalate_req["surface"].get(req, "")})
                emit("brain", "🧭 Flash → Brain Worker (escalada registrada)", text=req, role="system")

            # …y las tareas ADICIONALES del mismo turno (V2-118). Van DESPUÉS de la principal y solo si esta
            # sobrevivió: los guards de arriba anulan `v` cuando el turno resulta no ser una tarea (era un show,
            # un cierre, la respuesta a un worker), y en ese caso las demás tampoco lo eran. Cada una pasa por el
            # MISMO dedup que la principal — dos peticiones parecidas se inyectan en la que ya corre en vez de
            # abrir una segunda sesión de lo mismo.
            # BACKSTOP CREATE-WIDGET (V2-118 ronda 2, medido): el operador pidió TRES cosas y una era «móntame
            # un widget de un juego». El modelo llamó a la tool UNA vez, por el informe, y las otras dos se
            # quedaron sin lanzar — el registro de tareas de la corrida no tiene NI UNA de kind `code` en los 14
            # turnos, mientras el turno decía «te cargo un juego de plataformas». La capacidad de abanicar ya
            # existe (arriba); lo que falla es que el modelo pequeño no la usa de forma fiable.
            # El guard de crear-widget YA existía pero solo cuando el turno no había disparado NADA
            # (`_no_tool`): en cuanto escalaba otra cosa, la petición de widget se caía en silencio. Aquí se
            # cubre justo ese hueco, con el MISMO clasificador determinista y solo si ninguna de las peticiones
            # que van a salir es ya una de crear widget.
            # V2-155 (espejo del probe — cablear en AMBOS): se añade la CLÁUSULA que pide el widget, no el turno
            # entero. Un turno que encarga tres cosas lleva las otras dos dentro, y con «informe» dentro el
            # dedup le asigna el mismo widget destino que la tarea del informe y se la come por su señal más
            # fuerte. Ver `router_guards.create_widget_request` para la medición.
            _w_req = (_router.create_widget_request(text)
                      if not any(_router.looks_like_create_widget(r)
                                 for r in [req, *escalate_req["more"]]) else "")
            if _w_req:
                escalate_req["more"].append(_w_req)
                emit("brain", "🏗️ crear-widget del mismo turno, sin lanzar → escalada añadida (backstop)",
                     text=_w_req[:120], role="system", extra={"cat": "flash"})

            _launched = list(_prev_pending) + [{"request": req}]
            for _extra_req in escalate_req["more"]:
                try:
                    if _similar_pending(_extra_req, _launched):
                        from nucleo import dispatch as _disp4
                        _disp4.inject_soon(_extra_req, _extra_req)
                        emit("brain", "↪️ tarea adicional → inyección a worker vivo", text=_extra_req, role="system")
                    else:
                        _escalate_mod.escalate_to_slowbrain(
                            _extra_req,
                            context={"src": "voice", "surface": escalate_req["surface"].get(_extra_req, "")})
                        emit("brain", "🧭 Flash → Brain Worker (tarea adicional del mismo turno)",
                             text=_extra_req, role="system")
                    _launched.append({"request": _extra_req})
                except Exception as _e_more:  # noqa: BLE001
                    logger.warning(f"escalada adicional falló (las demás siguen): {_e_more}")

        # TELEMETRÍA compromiso-sin-acción (V2-047 F3, sesión 23:15 ITV T22: «Me pongo con ello ahora mismo» con
        # decisión VACÍA — el modelo prometió y NO llamó a ninguna tool; el operador esperó 6 min). NO cambia el
        # comportamiento: solo emite un evento MEDIBLE (categoría flash) para cuantificar cuántas veces pasa con el
        # chain-suite. Si resulta frecuente, la Fase 2 añade un backstop; de momento, VISIBILIDAD. Señal, no tabla
        # de decisión: una promesa en 1ª persona ("me pongo/lo hago/ahora mismo/te lo reservo/arranco") + CERO
        # acción efectiva este turno.
        _did_act = bool(acted["widget"] or data_done["v"] or worker_acted["v"] or escalate_req["v"] is not None
                        or search_req["v"] is not None or music_req["v"] is not None or confirm_state.get("opened")
                        or clarify.get("msg"))
        if spoken_text and not _did_act:
            import re as _re_prom
            _committed = bool(_re_prom.search(
                r"\b(me pongo con|me pongo a|ahora mismo|lo hago|lo hago ya|te lo (?:reservo|busco|"
                r"miro|preparo|hago|gestiono)|arranco|voy (?:con|a por|alla|alli|ya)|me meto en|"
                r"enseguida|me encargo|lo pongo en marcha|voy alla|entro (?:en|a) la web)\b",
                _norm_nfkd(spoken_text)))
            if _committed:
                emit("brain", "⚠️ promesa sin acción (dijo que lo haría, no disparó tool)", text=spoken_text[:120],
                     role="system", extra={"cat": "flash", "kind_diag": "promise_no_tool"})
                # BACKSTOP V2-049 (arregla «¿por qué te has parado?», sesión ITV): si PROMETIÓ hacer una GESTIÓN WEB
                # y NO llamó a ninguna tool, la escalada la forzamos NOSOTROS — determinista, espejo del
                # login-fallback. Sin esto el operador oye "me pongo con ello" y no pasa NADA (el modelo rápido no
                # dispara `escalate_to_slowbrain` de forma fiable). Solo para tareas web reales (verbo de gestión),
                # nunca para charla; respeta el dedup/inject (no abre una 2ª sesión de lo mismo).
                try:
                    from nucleo.flash import router as _r_bk
                    if _r_bk.looks_like_web_task(text):
                        if _similar_pending(text, _prev_pending):
                            from nucleo import dispatch as _disp_bk
                            _disp_bk.inject_soon(text, text)
                            emit("brain", "↪️ promesa→inyección a worker vivo (backstop)", text=text[:120], role="system")
                        else:
                            # EL KIND LO DECIDE EL CLASIFICADOR, no este backstop (2026-08-14, sesión b70a45d0).
                            # Antes iba fijo a `"web"`, y eso convirtió una data-op LOCAL en una tarea de navegador:
                            # «lees lo que hay en la agenda, lo borras y compruebas» abrió DOS tarjetas de navegador
                            # que nadie pidió, se rotuló «Buscando en la web…», y —el daño de verdad— pasó a ser
                            # «la tarea del navegador», que es justo lo que hizo que un `stop_worker` equivocado la
                            # encontrara y la matara con la autorización del operador ya entregada.
                            # `looks_like_web_task` se queda solo como DISPARADOR (¿hay un verbo de gestión?): su
                            # propio docstring dice que existe para reclasificar una llamada errónea a
                            # `authenticate_web`, y sus raíces (`borr|lee|compr|…`) no exigen destino web ninguno.
                            # Quién es la tarea lo dice `dispatch._classify_kind`, que para ese mismo texto
                            # responde `generic` — sin navegador y con el rótulo honesto.
                            from nucleo import dispatch as _disp_kind
                            _bk_kind = _disp_kind._classify_kind(text)
                            _escalate_mod.escalate_to_slowbrain(
                                text, context={"src": "voice", "kind": _bk_kind})
                            emit("brain", f"🧭 promesa→escalada FORZADA (backstop · kind={_bk_kind})",
                                 text=text[:120], role="system", extra={"cat": "flash", "kind_task": _bk_kind})
                except Exception as _e_bk:  # noqa: BLE001
                    logger.warning(f"backstop promesa falló: {_e_bk}")


def _similar_pending(req: str, pendings: list[dict]) -> bool:
    """True si `req` se parece mucho a una escalada YA en vuelo (Jaccard de palabras de contenido ≥0.5) — el
    operador insiste/refina la MISMA petición mientras el SlowBrain trabaja (V2-029). Evita tareas y entregas
    duplicadas. Dos peticiones distintas (moto vs piso) NO se funden."""
    import re as _re
    import unicodedata as _ud

    def _w(s: str) -> set:
        n = "".join(c for c in _ud.normalize("NFKD", s or "") if not _ud.combining(c)).lower()
        return {t for t in _re.findall(r"\w+", n) if len(t) >= 4}

    g = _w(req)
    if not g:
        return False
    for p in (pendings or []):
        o = _w(p.get("request", ""))
        union = len(g | o)
        if union and len(g & o) / union >= 0.5:
            return True
    return False


def _action_is_negated(n: str) -> bool:
    """True si la frase NIEGA la acción de widget ("no necesito que abras nada", "no me muestres", "no cierres
    nada", "don't open") — para que el fallback NO dispare un show/close cuando el operador dice EXPLÍCITAMENTE que
    no lo haga (bug V2-023: "no necesito que abras nada" contenía "abras" → abría mensajería igual). Ventana corta
    (≤18 chars entre la negación y el verbo) para no pisar compuestos legítimos tipo "no quiero la agenda,
    muéstrame el reloj"."""
    import re as _re
    return bool(_re.search(
        r"(?:\b(?:no|sin|tampoco|nunca|ni)\b|don'?t|do not|no need|without)[^.?!¿]{0,18}\b"
        r"(?:abr|muestr|ensen|pon|saca|sube|cierr|cerr|quit|elimin|escond|ocult|close|hide|open|show)", n))


def _norm_nfkd(s: str) -> str:
    """Minúsculas sin acentos (para los guards deterministas de canvas)."""
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", s or "") if not _ud.combining(c)).lower()


def _is_meta_widget_question(n: str) -> bool:
    """True si la frase PREGUNTA/COMENTA sobre una acción de widget YA ocurrida ("¿por qué has abierto el widget de
    proyectos?", "¿por qué se abrió eso?", "no deberías haber abierto nada") en vez de ORDENAR una — para que NUNCA
    se dispare un show/close por mencionar un widget en una queja o pregunta META (bug de la sesión 2026-07-12: el
    operador preguntando "¿por qué abriste X?" hacía que zaelar ABRIERA X). `n` ya viene normalizado (sin acentos).
    NO pisa una orden educada tipo "¿me muestras la agenda?" (no lleva 'por qué' ni verbo en pasado)."""
    import re as _re
    # "por qué" + verbo de canvas → pregunta sobre el porqué de una acción, no una orden
    if _re.search(r"\bpor ?que\b|porque\b", n) and _re.search(
            r"\b(abr|abri|abrio|abierto|mostr|ensen|saca|cerr|cerro|abriste|se abrio)", n):
        return True
    # verbo de canvas en PASADO/participio (acción ya ejecutada, se habla DE ella)
    return bool(_re.search(
        r"\b(abriste|abrio|abrido|abierto|has abierto|habias abierto|deberias haber (abierto|mostrado)|"
        r"mostraste|ensenaste|cerraste|cerro|se abrio|se cerro|has mostrado|has cerrado|se ha abierto)\b", n))


def _close_target(wid: str) -> dict:
    """A QUÉ tarjeta va este cierre (V2-259 F3). Una sola decisión para los TRES puntos de este fichero que
    emiten `widget/close` con id — escribir la regla tres veces es cómo se llega a que falte en uno.

    Fail-soft hacia el comportamiento de SIEMPRE: si no se puede saber qué hay abierto, cierra como antes. Una
    pregunta espuria en cada cierre sería peor que el fallo que esto quita.
    """
    try:
        from server.voice_api import open_instances
        from widgets import instances as _inst
        return _inst.resolve_close(wid, open_instances())
    except Exception:  # noqa: BLE001
        return {"id": wid, "ask": "", "options": []}


def _widget_fallback(text: str, emit, ask=None) -> bool:
    """Si la frase es una orden clara de mostrar/cerrar un widget conocido y el modelo no emitió la tag, la
    emitimos nosotros (idempotente). Reutiliza el identificador de `widgets/runtime`. Devuelve True si ACTUÓ
    (para que el llamante marque acted["widget"] y el login-fallback no robe el turno — V2-023).

    `ask` es por dónde se PREGUNTA (V2-259 F3). Preguntar TAMBIÉN es haber actuado: el turno se resuelve con la
    pregunta, y devolver False aquí dejaría que el login-fallback se llevara el turno como si nadie hubiera
    hecho nada — que es el fallo que el comentario de arriba existe para evitar."""
    import re as _re
    import unicodedata as _ud
    n = "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c)).lower()
    if _action_is_negated(n):   # "no necesito que abras nada" → no dispares ningún widget
        return False
    if _is_meta_widget_question(n):   # "¿por qué abriste X?" es una PREGUNTA, no una orden
        return False
    try:
        if _re.search(r"\b(quit|cierr|cerr|elimin|escond|ocult|limpi|despej|close|hide|clear)", n):
            if _re.search(r"\b(todo|todos|todas|all|widgets|tarjetas|la pantalla|el escritorio)", n):
                emit("widget", "close", extra={"src": "flash"})
                return True
            wid = _identify(text)
            if wid:
                _t = _close_target(wid)
                if _t["ask"]:
                    if ask:
                        ask(_t["ask"])
                        emit("brain", "❓ cerrar: varias tarjetas abiertas", text=wid, role="system",
                             extra={"options": _t["options"]})
                        return True
                    return False        # sin canal para preguntar, mejor no cerrar a ciegas
                emit("widget", "close", extra={"id": _t["id"] or wid, "src": "flash"})
                return True
        elif _re.search(r"\b(abr|muestr|ensen|pon|saca|sube)|quiero ver|ver mi", n):
            wid = _identify(text)
            if wid:
                emit("widget", "show", extra={"id": wid, "src": "flash"})
                return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"widget fallback skipped: {e}")
    return False


def _human_confirm_question(wid: str, action: str, payload: dict) -> str:
    """Texto HUMANO de una confirmación de data-op irreversible (overlay + voz). Expone el ALCANCE real leído del
    MANIFEST — qué HACE la acción (`desc`) y sobre QUÉ item (etiqueta resuelta) — para que el operador vea si es
    MÁS de lo que pidió (p.ej. un PROYECTO entero en vez de una tarea). Genérico: sirve a cualquier widget. Fallback
    prudente si no hay manifest/desc."""
    # V2-051: RESPONDER un mensaje → la confirmación LEE el borrador (destinatario + texto), no la jerga de la
    # acción. Así el operador oye exactamente qué se va a enviar antes de decir sí.
    if wid == "mensajeria" and action == "reply":
        body = str((payload or {}).get("text") or "").strip()
        draft = (body[:180] + "…") if len(body) > 180 else body
        who = ""
        try:
            from widgets.mensajeria import data as _md
            v = _md.view_data()
            n = (payload or {}).get("n")
            if v.get("active_chat"):
                hit = next((it for it in v.get("active_items", []) if it.get("n") == n), None)
                who = (hit or {}).get("from") or ""
            else:
                hit = next((c for c in v.get("chats", []) if c.get("n") == n), None)
                who = (hit or {}).get("name") or ""
        except Exception:
            pass
        dest = f" a {who}" if who else ""
        return f"Voy a responder{dest}: «{draft}». ¿Lo envío?"

    desc = ""
    human = ""
    label = ""
    try:
        from widgets import refs, runtime
        spec = ((runtime.get(wid) or {}).get("actions") or {}).get(action) or {}
        human = str(spec.get("confirm_q") or "").strip()
        desc = str(spec.get("desc") or "").strip().rstrip(".")
        field = refs.id_field_for_action(wid, action)
        if field:
            label = refs.label_for(wid, field, (payload or {}).get(field, ""))
    except Exception:
        pass
    tail = f" («{label}»)" if label else ""
    # `confirm_q` MANDA: es la pregunta escrita PARA EL OPERADOR (2026-08-15, sesión 319252e7). El `desc` del
    # manifest es la descripción de la tool, o sea texto escrito PARA EL MODELO — y leerlo en voz alta es un error
    # de categoría que el operador oyó entero: «VACÍA la agenda entera de una vez: descarta todas las tareas…
    # **Úsala cuando el operador pida** dejarla vacía «del todo»/«por completo»…». Le estábamos recitando nuestras
    # instrucciones internas y pidiéndole que dijera «sí» a eso.
    if human:
        # `{item}` deja que el autor del widget coloque el elemento DONDE suena bien al oído, en vez de pegarlo
        # al final: «¿Congelo el proyecto «Reddit» entero?» en vez de «…entero. («Reddit»)». Si no hay item
        # resuelto, la frase se queda sin él antes que decir «el proyecto «»».
        if "{item}" in human:
            q = human.replace(" «{item}»", f" «{label}»" if label else "").replace("{item}", label)
        else:
            q = f"{human}{tail}"
        return q if "?" in q else f"{q} ¿Lo confirmo?"
    if desc:
        # Sin `confirm_q`, se cita SOLO la primera frase del desc: la guía de uso («Úsala cuando…») vive a partir
        # del primer punto y no es asunto del operador. Mejor que la jerga cruda de 2026-07-15 («¿Confirmas
        # drop_project?»), que es lo que esta rama vino a arreglar, y sin arrastrar el resto del prompt.
        primera = desc.split(". ")[0].rstrip(".")
        return f"Ojo, esto es permanente: «{primera}»{tail}. ¿Lo confirmo?"
    return f"Ojo, la acción «{action}»{tail} es permanente. ¿La confirmo?"


def _show_guard_target(text: str, context: list[dict] | None = None, last_action: str = "") -> str | None:
    """Si la frase es una orden clara de MOSTRAR un widget EXISTENTE y NO pide crear uno nuevo, devuelve su id;
    si no, None. Guard DETERMINISTA (V2-023, no depende del LLM) para que una escalada ERRÓNEA de "muéstrame el de
    mensajería" nunca genere un widget basura — espejo del guard de LOGIN. Con verbo de crear ("créame otro reloj")
    devuelve None → deja escalar a un CREATE legítimo."""
    import re as _re
    import unicodedata as _ud
    n = "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c)).lower()
    if _action_is_negated(n):   # "no necesito que abras nada" → no es una orden de mostrar
        return None
    if _re.search(r"\b(crea|crear|cree|haz|hacer|genera|generar|nuev|construy|dise|monta|make|create|build|new)", n):
        return None
    if not _re.search(r"\b(abr|muestr|ensen|pon|saca|sube)|quiero ver|ver mi|ense", n):
        return None
    # Pronouns such as "muéstramelo" deliberately omit the widget noun. Resolve their most recent topical
    # antecedent through the real catalogue; this preserves human continuity without a weather/agenda/etc table.
    try:
        from nucleo.flash import router as _router
        tail = (text or "").strip().lower().strip("¿?¡!.,;:")
        deictic = (bool(_re.search(r"\b(?:muestr|ensen|abre|saca)\w*(?:lo|la|los|las)\b", n))
                    or any(_router.looks_like_bare_ref(token) for token in tail.split() if token))
        if deictic:
            for message in reversed(context or []):
                if message.get("role") != "user":
                    continue
                prior = str(message.get("content") or "").strip()
                if prior:
                    match = _identify(prior)
                    if match:
                        return match
                    break
            if last_action == "search":
                try:
                    from widgets import runtime
                    if runtime.get("search") is not None:
                        return "search"
                except Exception:
                    pass
    except Exception:
        pass
    return _identify(text)


def _identify(text: str) -> str | None:
    """Resuelve una frase a un id de widget. V2-078: pasa el CONTEXTO (abiertos + usados hace poco) para que, ante
    un empate, gane el que el operador tiene DELANTE o tocó hace nada — no un homónimo del catálogo. Lectura µs del
    estado (sin retriever); best-effort (si el estado no está, resuelve sin contexto, como antes)."""
    try:
        from widgets import runtime
        try:
            from memory import api as _memapi
            _st = _memapi.state() or {}
            _open = _st.get("open_widgets") or []
            _recent = _st.get("recent_widgets") or []
        except Exception:
            _open, _recent = [], []
        return (runtime.identify(text, open_ids=_open, recent_ids=_recent) or {}).get("match")
    except Exception:
        return None


def _identify_is_widget(wid: str) -> bool:
    """¿`wid` es un id EXACTO del catálogo? (para decidir si hay que resolverlo flojito antes de borrar)."""
    try:
        from widgets import runtime
        return runtime.get(wid) is not None
    except Exception:
        return False
