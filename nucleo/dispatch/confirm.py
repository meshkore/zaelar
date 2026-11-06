"""nucleo/dispatch/confirm.py — the pending-confirmation gate for an IRREVERSIBLE task (V2-126).

Split out of `dispatch.py` in F3 of the 2026-08-23 architecture audit. It was already the cleanest seam in that
file — its own registry, its own TTL, its own vocabulary, and (measured before moving anything) **zero reads of
`_SESSIONS`**, which is what made it safe to move while the rest of the file's seams are not: that registry is
rebound by `monkeypatch` in 26 tests, so a module holding its own reference to it would silently keep the old
dict. Nothing here touches it.

Same contract as `widgets/confirm.py`, the sibling gate for irreversible WIDGET actions: remember the ask, expire
it rather than let it hang forever, and expose a line the FlashBrain can read in its live state. Two registries
on purpose — that one is keyed by widget id and executes through `apply_action`, this one RE-DISPATCHES a worker
task; fusing them would couple two unrelated execution paths for the sake of a shared TTL.

`dispatch.py` re-exports every public name here, so `dispatch.confirm_line()`, `dispatch.resolve_confirm(...)`
and the tests that mutate `dispatch._PENDING_CONFIRM` keep working untouched. Mutation survives a re-export
(same dict object); only REBINDING would not, and nothing rebinds these.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from nucleo.workers.session import SessionRecord

if TYPE_CHECKING:                      # runtime import would be circular; the annotation is a string
    from nucleo.dispatch import Task

logger = logging.getLogger("zaelar.dispatch.confirm")

# Same contract as `widgets/confirm.py` (the sibling gate for irreversible WIDGET actions): remember the ask,
# expire it rather than let it hang forever, and expose a line the FlashBrain can read in its live state. It is
# a separate registry on purpose — that one is keyed by widget id and executes through `apply_action`, this one
# re-dispatches a worker task; fusing them would couple two unrelated execution paths for a shared TTL.
_PENDING_CONFIRM: dict[str, dict] = {}
_CONFIRM_TTL = 300.0     # 5 min. Longer than the widget gate's 90 s: this question ("shall I really pay?")
                         # arrives mid-conversation and the operator may reasonably think about it.


# V2-190 — an expired confirmation is a FACT (renew-gym-membership: the entry was swept and the turn narrated work
# that never started). The gate still expires — a late «yes» cannot arm it — but the memory of it moves here.
_EXPIRED_CONFIRM: dict[str, dict] = {}
_EXPIRED_MEMORY_S = 900.0     # 15 min: long enough to outlive the conversation that asked

# A «no» that dropped a parked errand is a fact too, for the same reason as an expiry. three-tasks-at-once (EN,
# 2026-10-11 02:58): a «no» read off a sentence about the monitors dropped the parked game; the state then said
# nothing about the game at all, and asked about it, the agent explained «it got built and then everything got
# wiped in a reset» — no reset happened. What the state does not say, the model invents.
_DECLINED_CONFIRM: dict[str, dict] = {}


def _sweep_confirm(now: float | None = None) -> None:
    now = time.time() if now is None else now
    # A question on its row (`make_durable`) waits as every durable ask does (CRIT-T4): only the in-memory one expires.
    for k in [k for k, v in _PENDING_CONFIRM.items() if now - v["ts"] > _CONFIRM_TTL and not v.get("ask_id")]:
        _EXPIRED_CONFIRM[k] = {**_PENDING_CONFIRM.pop(k), "expired_at": now}
    for k in [k for k, v in _EXPIRED_CONFIRM.items() if now - float(v.get("expired_at") or 0) > _EXPIRED_MEMORY_S]:
        _EXPIRED_CONFIRM.pop(k, None)
    for k in [k for k, v in _DECLINED_CONFIRM.items() if now - float(v.get("declined_at") or 0) > _EXPIRED_MEMORY_S]:
        _DECLINED_CONFIRM.pop(k, None)


def _forget_declined_like(request: str) -> None:
    """Asked again for the same errand: the old «no» is no longer the fact about it."""
    from nucleo.turn.errands_of_a_turn import same_errand
    for k in [k for k, v in _DECLINED_CONFIRM.items() if same_errand(str(v.get("request") or ""), request)]:
        _DECLINED_CONFIRM.pop(k, None)


def remember_confirm(task_id: str, request: str, task: "Task", *, sheet: str = "", cls: str = "") -> None:
    """Keep the question the gate just asked, so a later «si» has somewhere to go.

    …AND the SHEET it had already opened (V2-508). The gate parks the errand and pops its record, but the
    sheet is on the operator's screen by then: `run_listener` opens it at the moment of the errand, on
    purpose, so nobody stares at a blank canvas. Without carrying it, the «si» relaunches through the normal
    door with no sheet in its context, mints a SECOND box beside the first, and leaves the first one empty
    for good — measured 2026-08-30 (`cheapest-monitor__us`, `results::101c0f-1` abandoned, `-2` filled).

    A CONFIRMED ERRAND IS A CONTINUATION, exactly like the provider relay and the context handoff that
    `_sheet_open` already inherits for: same errand, same request, and the operator is already looking at
    its box."""
    from nucleo import danger as _danger
    _sweep_confirm()
    _EXPIRED_CONFIRM.pop(str(task_id), None)      # se vuelve a preguntar: ya no es un caducado sin respuesta
    _forget_declined_like(request)
    _PENDING_CONFIRM[str(task_id)] = {
        "request": request, "kind": (task.kind or "generic"), "trusted": bool(task.trusted),
        "context": dict(task.context or {}), "question": _danger.confirm_question(request, cls=cls),
        "sheet": str(sheet or ""), "ts": time.time(), "asked": _SPOKEN.pop(str(task_id), False)}


def remember_code_change(task_id: str, request: str, task: "Task", *, sheet: str = "") -> None:
    """Park an errand that would BUILD OR REWRITE one of his cards, and keep the question (V2-757).

    Same registry as the irreversible gate on purpose — it already solves everything hard here: the yes/no
    arrives through `turn/confirm_gates.py`'s deterministic classifier, `confirm_line()` tells the brain
    something is stopped so it cannot narrate progress, `_sweep_confirm` turns a silence into «that never
    started» instead of into an execution, and `resolve_confirm` relaunches through the SAME door with
    `confirmed` set. What differs is the SENTENCE and what the brain is told about it: building a card is
    not a dangerous act, it is an expensive and visible one, and calling it «irreversible» to his face
    would make him answer a different question.
    """
    from nucleo.request import kind as _ek
    _sweep_confirm()
    _EXPIRED_CONFIRM.pop(str(task_id), None)
    _forget_declined_like(request)
    from nucleo.turn import declined_build as _db
    _db.asked(request)
    _PENDING_CONFIRM[str(task_id)] = {
        "request": request, "kind": (task.kind or "code"), "trusted": bool(task.trusted),
        "context": dict(task.context or {}),
        "question": _ek.code_change_question(request, _ek.code_change((task.context or {}).get("errand_kind"))),
        "sheet": str(sheet or ""), "code_change": _ek.code_change((task.context or {}).get("errand_kind")) or "modify",
        "ts": time.time(), "asked": _SPOKEN.pop(str(task_id), False)}


def remember_offer(request: str, *, context: dict, question: str) -> None:
    """Aparca un encargo que el turno OFRECIÓ en vez de lanzar (V2-655).

    Medido 2026-09-10: el modelo preguntó «¿Me pongo a revisar y dejar eso cableado?» y en el MISMO segundo el
    encargo ya existía, con un worker en camino. La pregunta era decoración sobre una decisión ya tomada, y el
    operador la leyó literalmente: contestó, y esperaba que su respuesta decidiera algo.

    Reusa el registro del confirm-gate a propósito, porque ya resuelve todo lo difícil: el «sí/no» llega por el
    clasificador determinista de `turn/confirm_gates.py`, `confirm_line()` le dice al cerebro que hay algo
    parado —para que no narre progreso— y `_sweep_confirm` hace que un silencio caduque en «esa tarea NUNCA
    empezó» en vez de en una ejecución. Lo único distinto es la PREGUNTA: aquí es la del modelo, con sus
    palabras, no la fórmula de `danger.confirm_question` — el operador tiene que reconocer lo que contestó."""
    _sweep_confirm()
    _forget_declined_like(request)
    key = f"offer:{int(time.time() * 1000)}"
    _PENDING_CONFIRM[key] = {
        "request": request, "kind": str((context or {}).get("kind") or "generic"), "trusted": True,
        "context": {k: v for k, v in dict(context or {}).items() if k != "asked"},
        "question": question, "sheet": "", "offered": True, "ts": time.time()}


def remember_unlicensed(task_id: str, request: str, task: "Task", *, question: str, sheet: str = "") -> None:
    """Park an errand started from a line that was not a clear request to the agent, and keep the question
    (V2-812 T-03). Same registry as the other gates — the yes/no, the brain's line («no has empezado nada»),
    the expiry and the relaunch with `confirmed` are all theirs; it is marked `offered` because what he is asked
    is whether HE wants it, not whether it is safe."""
    _sweep_confirm()
    _EXPIRED_CONFIRM.pop(str(task_id), None)
    _forget_declined_like(request)
    _PENDING_CONFIRM[str(task_id)] = {
        "request": request, "kind": (task.kind or "generic"), "trusted": bool(task.trusted),
        "context": dict(task.context or {}), "question": question, "sheet": str(sheet or ""),
        "offered": True, "unlicensed": True, "ts": time.time(), "asked": _SPOKEN.pop(str(task_id), False)}


def unlicensed_question(request: str) -> str:
    """The sentence he hears when an errand would start from a line that was not clearly his request to us —
    in HIS language, like every gate's question (V2-682)."""
    t = (request or "").strip()
    short = (t[:120] + "…") if len(t) > 120 else t
    from i18n import langs as _lg
    return _lg.current_language().errand_unaddressed_confirm.format(what=short)


async def unlicensed_gate(task: "Task", key: str, req: str, *, wait_s: float = 2.5) -> bool:
    """THE door a worker starts through asks the ONE consent rule whether the line behind it licensed it
    (V2-812 T-03). True when the errand was parked on a question; False when it may run.

    Measured in a car (session e52cd845): «Eso es.», said into an open window after a sentence that both stated
    something and offered to resume a failed booking, resumed it — a 144 s worker on the restaurant's website.
    The line was addressed; it was not a request. Every worker passes here — a commission from the model, a
    backstop's errand, a resumed row — so the rule is not one each caller has to remember.

    A confirmed relaunch is HIS yes to this very question: it licenses the line, so the worker's own later acts
    (a commit click, a reply) read a licensed trace instead of asking again."""
    from nucleo import consent
    from nucleo import dispatch as _d
    ctx = task.context or {}
    trace = str(ctx.get("trace") or "")
    if not trace or _d._dev_worker_params(ctx):     # the cluster dev worker brings its own authorisation
        return False
    try:
        from voice import attention as _attn
    except Exception as e:  # noqa: BLE001 — no voice layer: no line behind this errand, nothing to ask about
        logger.debug(f"unlicensed_gate: no attention layer ({e!r}) — the errand runs")
        return False
    if bool(ctx.get("confirmed")):
        _attn.grant_line(trace)
        return False
    lic = await _attn.wait_licence(trace, timeout_s=wait_s)
    verdict = consent.decide(level="standard", policy_key="errand.start", licensed=lic)
    if not verdict.get("unlicensed"):
        return False
    logger.info(f"dispatch: task {key} PARKED — its line was not a clear request: {req[:80]}")
    rec = _d._SESSIONS.get(key)
    question = unlicensed_question(req)
    if rec:
        rec.status = "done"
        rec.result_summary = question
        await _deliver_confirm(rec)
        _d._SESSIONS.pop(key, None)
        remember_unlicensed(key, req, task, question=question, sheet=_d.sheet_of(rec))
        make_durable(key, rec)                 # the row waits on the question (V2-857 P0-1)
        _d.sync_state()
    else:
        remember_unlicensed(key, req, task, question=question)
    return True


def parked_errands() -> list[tuple[str, str]]:
    """(task_id, request) of every errand PARKED on a question — the same shape `dispatch._live_errands()` hands
    the dedup, because a parked errand has to be VISIBLE to it (2026-09-29, session 81095d8d).

    The gate pops the session record when it parks (`_run_session` sets `done` and drops it from `_SESSIONS`),
    so the dedup — which only compares against `queued|running` — saw `live: 0` every time the operator
    repeated himself. Measured: «i want to buy Through the Moon (2020), gime the amazon link» → parked with
    the money question; «provide the link to the product» → `dedup_miss live:0` → a SECOND errand, a second
    sheet, the same question spoken again; «give me the link and don't ask me again» → a THIRD. Four tasks,
    four result boxes on his screen, one intention. A task that is waiting on him is not dead, and the dedup
    has to see it as what it is: the errand he is still talking about."""
    _sweep_confirm()
    return [(k, str(v.get("request") or "")) for k, v in _PENDING_CONFIRM.items()]


def absorb_refinement(task_id: str, text: str) -> str:
    """Fold a repeated/refined request into the errand parked as `task_id` instead of opening a second one.
    Returns the QUESTION still waiting for him ("" when nothing was parked under that id).

    The refinement travels with the «yes»: `resolve_confirm` re-escalates the request WITH what he added while
    waiting, so the worker that finally runs has all of it. The clock is refreshed on purpose — repeating the
    order is the opposite of forgetting it, and letting the ask expire under a still-talking operator is how
    a gated task turns into narrated work (V2-190)."""
    p = _PENDING_CONFIRM.get(str(task_id))
    if not p:
        return ""
    refs = list(p.get("refinements") or [])
    t = (text or "").strip()
    if t and t not in refs and t != p.get("request"):
        refs.append(t[:300])
    p["refinements"] = refs[-5:]
    p["ts"] = time.time()
    return str(p.get("question") or "")


def adopt_sheet(task_id: str, sheet: str) -> str:
    """The parked errand `task_id` takes `sheet` when it has none, so his «yes» relaunches it there (V2-843 S3).
    Returns the errand's sheet after the call ("" when nothing is parked under that id)."""
    p = _PENDING_CONFIRM.get(str(task_id))
    if not p:
        return ""
    if not str(p.get("sheet") or "").strip() and str(sheet or "").strip():
        p["sheet"] = str(sheet).strip()
    return str(p.get("sheet") or "")


def pending_confirm(task_id: str = "") -> dict | None:
    """The confirmation still waiting for a yes/no, or None. Most recent wins — a second irreversible ask
    supersedes the first, exactly like the widget gate — unless `task_id` names which one (the reply named it)."""
    _sweep_confirm()
    if not _PENDING_CONFIRM:
        return None
    tid = (str(task_id) if str(task_id or "") in _PENDING_CONFIRM
           else max(_PENDING_CONFIRM, key=lambda k: _PENDING_CONFIRM[k]["ts"]))
    return {"task_id": tid, **_PENDING_CONFIRM[tid]}


def confirm_line() -> str:
    """Line for the FlashBrain's live state. Without it the brain has NO idea a task is parked waiting on the
    operator — which is precisely how a gated task turned into narrated progress."""
    p = pending_confirm()
    if not p:
        # V2-190: nothing waiting — but maybe something EXPIRED waiting, and that is not the same as nothing.
        _sweep_confirm()
        if _DECLINED_CONFIRM and not p:
            _d = max(_DECLINED_CONFIRM.values(), key=lambda v: float(v.get("declined_at") or 0))
            if not _EXPIRED_CONFIRM or float(_d["declined_at"]) >= max(
                    float(v.get("expired_at") or 0) for v in _EXPIRED_CONFIRM.values()):
                return (f"UNA TAREA QUE LE PREGUNTASTE QUEDÓ DESCARTADA porque leí un NO en su respuesta: "
                        f"«{str(_d.get('request') or '')[:120]}». NUNCA EMPEZÓ y no está en marcha: no le des otra "
                        f"causa (ningún reinicio, ningún fallo). Si pregunta por ella, dile que la di por descartada "
                        f"y ofrece hacerla ahora.")
        if not _EXPIRED_CONFIRM:
            return ""
        _e = max(_EXPIRED_CONFIRM.values(), key=lambda v: float(v.get("expired_at") or 0))
        return (f"UNA CONFIRMACIÓN QUE LE PEDISTE CADUCÓ SIN RESPUESTA: «{str(_e.get('request') or '')[:120]}». "
                f"Esa tarea NUNCA EMPEZÓ y no va a empezar sola — no digas que sigue en marcha ni que esperas "
                f"novedades suyas. Si sale a colación, dilo y ofrece retomarla desde cero.")
    from nucleo import danger as _danger_line
    # If mueve DINERO is says here also (V2-129): the operator already oyo «no hago ningun cargo without decirte the
    # importe», and the turn siguiente no can contradecir esa promesa.
    money = (" MUEVE DINERO: le prometiste decirle el importe exacto ANTES de cobrar nada, así que ni lo pagues"
             " ni digas que está pagado hasta haber mirado la cifra y habértela confirmado él."
             if _danger_line.moves_money(p["request"]) else "")
    if p.get("code_change"):
        # V2-757 — not «irreversible»: a card being built or rewritten is expensive and visible, not
        # dangerous, and the brain must not dress the question up as a warning. What it MUST not do is
        # say it is under way: measured in session f84f91ef, the turn answered «lo dejo estar y sigo con
        # los ajustes del widget» while nothing of his had been touched.
        _what = ("CONSTRUIR una tarjeta nueva" if p["code_change"] == "create"
                 else "MODIFICAR una tarjeta suya")
        return (f"LE HAS PREGUNTADO SI {_what} y AÚN NO ha contestado: «{p['request'][:120]}». No has "
                f"tocado NI UNA LÍNEA de esa tarjeta, así que no digas que estás con ello ni que va en "
                f"marcha. Si dice que SÍ, arranca; si dice que NO, olvídalo y confírmaselo.")
    if p.get("offered"):
        # V2-655: no es una acción irreversible, es algo que TÚ te ofreciste a hacer. Decirle «irreversible» a
        # una oferta corriente asusta sin motivo y le hace contestar otra cosa.
        return (f"TE OFRECISTE A HACER ESTO y él AÚN NO ha contestado: «{p['request'][:120]}». No has empezado "
                f"nada, así que no digas que está en marcha. Si dice que SÍ, arranca; si dice que NO, olvídalo.")
    return (f"CONFIRMACIÓN PENDIENTE de una acción IRREVERSIBLE: «{p['request'][:120]}».{money} Le preguntaste al "
            f"operador y AÚN NO ha contestado, así que la tarea está PARADA y no ha empezado nada — no digas "
            f"que está en marcha. Si dice que SÍ, arranca; si dice que NO, olvídalo y confírmaselo. Si vuelve a "
            f"pedir LO MISMO con otras palabras, es ESTA tarea: no la escales otra vez, repítele la pregunta en "
            f"una frase.")


def resolve_confirm(ok: bool, task_id: str = "") -> dict | None:
    """Answer the pending confirmation (`task_id`'s when given, else the most recent). `True` re-dispatches the SAME
    request with `confirmed` set (the gate lets it through this time); `False` drops it. Returns what was resolved,
    or None if nothing was pending."""
    p = pending_confirm(task_id)
    if not p:
        return None
    _PENDING_CONFIRM.pop(p["task_id"], None)
    if not ok:
        _DECLINED_CONFIRM[str(p["task_id"])] = {**p, "declined_at": time.time()}
        return {**p, "ok": False}
    # Se re-lanza by the MISMA puerta that any escalada (`escalate.requested` → `run_listener`), no by a
    # atajo: so preserves the trace, the dedup and the record of tasks. Lo only distinto es `confirmed`, that es
    # it that the gate mira for dejarla pasar this vez.
    if p.get("ask_id"):
        from nucleo.request import inline_ask
        if not inline_ask.take(str(p["ask_id"])):
            return {**p, "ok": True}            # the durable ask's own answer already relaunched it
    return {**_relaunch(p), "ok": True}


def _relaunch(p: dict) -> dict:
    """His yes to a parked errand: the SAME request through the same door, `confirmed`, on its OWN row (V2-857 P0-1:
    the row was kept and waited on his answer, so «how is it going?» and a restart both find it)."""
    ctx = {**p["context"], "confirmed": True, "kind": p["kind"]}
    if p.get("uid"):
        ctx["task_uid"] = str(p["uid"])
        try:
            from nucleo.circuit import ledger
            ledger.resumed(str(p["uid"]))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"relaunch: the row's wait not ended ({e!r})")
    request = str(p["request"])
    if p.get("refinements"):
        # What he added while the question waited goes WITH the errand — see `absorb_refinement`.
        request = request + "\n\nWhile waiting for the OK the operator added: " + " · ".join(p["refinements"])
    # La HOJA of the errand viaja with the «si». `_sheet_open` already sabe heredarla (compara contra the that le tocaria
    # a ESTE task_id: if the that trae no deriva of el, es of su predecesor and no is estrena). Sin this linea the
    # confirmado opens caja new al lado of the that the operator already has delante.
    if p.get("sheet"):
        ctx["sheet"] = str(p["sheet"])
    try:
        from nucleo.acts import errand as _esc
        _esc.escalate_to_slowbrain(request, context=ctx)
    except Exception:
        logger.warning("resolve_confirm: the confirmed errand could not be relaunched")
    return p


def make_durable(task_id: str, rec) -> str:
    """The parked errand's question on its OWN row, through the one asker (V2-857 P0-1). The gates used to forget the
    row (`ledger.withdrawn`) and keep the question only in this process: a restart lost it, his «yes» went nowhere,
    and «how is it going?» found no task. Now the row WAITS on the question (`circuit.asker`), keeps what the yes
    relaunches, and the in-memory entry is only this process's index (dedup, refinements, the brain's line). The
    turn already said the question (`_deliver_confirm`), so the pulse never relays it again. Returns the `ask_id`."""
    import json
    p = _PENDING_CONFIRM.get(str(task_id))
    uid = str(getattr(rec, "uid", "") or "")
    if not p or not uid:
        return ""
    try:
        from nucleo.circuit import asker
        from observability import identity
        ask_id = f"{uid}-start"
        keep = json.loads(json.dumps({k: p.get(k) for k in ("request", "kind", "trusted", "context", "sheet",
                                                             "refinements")}, default=str))
        entry = {"ask_id": ask_id, "corr_id": ask_id, "uid": uid, "task_id": str(task_id), "inline": True,
                 "consent": "ask_consent", "question": str(p.get("question") or ""), "answer": "", "result": None,
                 "session": identity.session_id(), "said": True, "retained": {"kind": "start", "pending": keep}}
        from nucleo.request.consent_ask import yes_no
        entry["candidates"] = entry["options"] = yes_no()   # the two DECLARED answers the brief picks (`#0` is yes)
        asker.ask(uid, entry, bus_id=str(task_id))
        p.update(uid=uid, ask_id=ask_id)
        return ask_id
    except Exception as e:  # noqa: BLE001 — the in-memory gate still holds it; the row is the part that failed
        logger.warning(f"make_durable: the parked errand's question is not on its row ({e!r})")
        return ""


def rerun_start(uid: str, entry: dict, text: str, choice: int | None = None):
    """The durable ask's answer for a parked errand (`inline_ask.rerun`): yes relaunches it on its row, anything else
    ends the row as not confirmed. One act per answer (`inline_ask.take`), whichever reader got the answer first.
    The brief's pick among the declared answers (`choice`, `#0` yes) decides; his words are read only with no pick."""
    from nucleo.request import inline_ask
    if not inline_ask.take(str(entry.get("ask_id") or "")):
        return None
    retained = entry.get("retained") or {}
    task_id = str(entry.get("task_id") or "")
    p = _PENDING_CONFIRM.pop(task_id, None) or dict(retained.get("pending") or {})
    p.setdefault("context", {})
    p.update(uid=uid)
    if choice is not None:
        yes = int(choice) == 0
    else:
        from nucleo.cli.worker_api_answer import _says_yes
        yes = _says_yes(str(entry.get("question") or ""), text)
    if not yes:
        _DECLINED_CONFIRM[task_id] = {**p, "declined_at": time.time()}
        from nucleo import circuit
        circuit.settle(row=uid, state="cancelled", outcome="he did not confirm it")
        return {"ok": False, "row": uid}
    _relaunch(p)
    return {"ok": True, "row": uid}


#: Was the gate's question actually SPOKEN to him (`proactive.notify`'s own answer)? By task id; read once by
#: `remember_*`, which park the errand right after the delivery.
_SPOKEN: dict[str, bool] = {}


async def _deliver_confirm(rec: "SessionRecord") -> None:
    try:
        # V2-796 — an errand waiting on his yes is a notice that must reach him: his phone when he is away.
        from nucleo.pulse import notices as _notices
        _res = await _notices.notify("zaelar", rec.result_summary, kind="approval", key=f"approval:{rec.task_id}",
                                     task_id=str(rec.task_id), speak=True, detail={"task": rec.task_id})
        _SPOKEN[str(rec.task_id)] = "voice" in str(_res.get("channel") or "")
    except Exception:
        pass


def owed_question(spoken: str) -> str:
    """The question of an errand parked on him that nobody has SAID yet, or "" — given once, for a reply that does
    not already name that errand (three-tasks-at-once EN, 2026-10-15). With no live speaker the gate's question
    falls back to a note, and the reply that should carry it said only the car's refinement: the game sat parked
    on «build you a new card?» that he never heard, and «make that one jump higher» went to the car report."""
    _sweep_confirm()
    from nucleo.turn import named_errand as _ne
    for p in sorted(_PENDING_CONFIRM.values(), key=lambda v: v["ts"]):
        if p.get("asked") or not p.get("question"):
            continue
        p["asked"] = True                 # said now — by this reply's own words, or by the line returned
        return "" if _ne.named(spoken or "", [{"request": p.get("request") or ""}]) else str(p["question"])
    return ""


