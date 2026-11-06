"""nucleo/workers/exit_gate.py — a worker act that LEAVES the machine crosses the message door (V2-851 F2, §4a/§15c).

Measured in F0: a worker's `widget_data` reached `server_api.brain_action` through the SAME consent rule as Flash but
skipped everything `nucleo/acts/message` does around a send — the recipient put back in his word, the held row, the
someone-else's-text check — and `card.licence`; and no worker exit read the taint. This is that door, reused, never
rebuilt; `worker_api.worker_act` asks it before executing, after the consent policy and `on_his_behalf`:

  · `card.licence` at LEAVES and FAST — a vetoed call is refused to the worker with its reason (e.g. the identical
    retry of a refused op);
  · ONE question per DECLARED slot of the act (`exit_slots`, V2-857 phase 5): the card's manifest declares each
    slot (`recipient`, `channel`, `text`, a held `draft`) and the rule its value must come from — his words (a
    swapped recipient goes back to HIS word), the commissioning turn's READING (`rec.reading`: the channel he
    named), his sure order over the row he saw (the yes, CRIT-C9), the card, or the worker's own; each slot's source
    is recorded on the exit's event;
  · `asked_if_leaving` — the leave rule, the SAME one Flash's send gate asks; the stranger's-text half reads THIS
    session's taint, not Flash's window;
  · **taint (§4a)** — `taint_question`: while the session has consumed a stranger's text since its last confirmed
    act, an exit is ASK_CONSENT unless the session runs under an explicit mandate that covers it
    (`nucleo/errands/mandate.py`). Freedom of reasoning, zero freedom of consequence (`party.py`): the worker may
    read anything; what leaves after reading it waits for his yes.

Every exit the worker reaches calls `taint_question`: a leaving `widget_data` (here), `mesh_serve` (the errand text
to a third-party agent) and the browser's submit (`widgets/navegador/click_gate.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger


@dataclass(frozen=True)
class Exit:
    payload: dict           # the call as it may run (his word put back in place of a swapped recipient)
    question: str = ""      # non-empty: ask him first (the worker's ordinary CONFIRM)
    refused: str = ""       # non-empty: vetoed, said to the worker
    released: bool = False  # his order over a held row he has seen is the yes (CRIT-C9): no consent question
    event: str = ""         # the EVENT TYPE this exit is (`messaging.send_new@whatsapp`, `errand.mesh_serve@mesh`)
    subject: str = ""       # the contact id the act reaches, when it reaches exactly one person (V2-857 phase 2)
    slots: dict = field(default_factory=dict)   # {declared slot: its source} (`exit_slots`, V2-857 phase 5)

    @property
    def verdict(self) -> str:
        return "refused" if self.refused else "ask" if self.question else "released" if self.released else "pass"


@dataclass(frozen=True)
class ExitSpec:
    """One bridge act that LEAVES the machine, declared once (V2-857 phase 5): the door it crosses (`body`) and how its
    event is read — a fixed type with its channel (`mesh_serve`), or the card's own class (`widget_data`, read off the
    manifest and its `consent_scope` hook, so a messaging act is `messaging.send_new@<channel>`)."""
    action: str
    body: str               # the name of this module's door, `(rec, payload) -> Exit`, read at call time
    event: str = ""         # fixed event type, or "" when the card's declared class is the type
    channel: str = ""       # fixed channel for a fixed event


def leave(rec, action: str, payload: dict | None) -> Exit | None:
    """THE exit door of a worker's act (V2-857 phase 5): None when the act does not leave the machine (undeclared
    here), else the Exit of its declared door, with the act's EVENT TYPE and SUBJECT read from the call and ONE
    `task` event recording the verdict. The bridge asks this and nothing by action name; the retained act his yes
    runs crosses it again (`worker_api_answer.answer`)."""
    spec = next((s for s in EXITS if s.action == str(action or "")), None)
    if spec is None:
        return None
    p = dict(payload or {})
    ex = globals()[spec.body](rec, p)
    event, subject, who, channel = _event_of(spec, ex.payload if ex.payload else p)
    ex = Exit(ex.payload, ex.question, ex.refused, ex.released, event=event, subject=subject, slots=ex.slots)
    _emit(f"🚪 exit door: {ex.verdict}", f"{event or action} → {', '.join(who) or channel or '?'}"[:200],
          {"id": str(getattr(rec, "task_id", "")), "exit": action, "event": event, "channel": channel,
           "subject": subject, "who": who[:3], "verdict": ex.verdict, "slots": dict(ex.slots),
           "why": (ex.refused or ex.question or ("his order over the row" if ex.released else ""))[:160]})
    return ex


def _event_of(spec: "ExitSpec", payload: dict) -> tuple[str, str, list[str], str]:
    """`(event type with its channel, subject, who, channel)` of this exit, from declared data only: the card's class
    (its manifest, refined by its `consent_scope` hook) or the spec's fixed type; the recipient the call names and
    the one person it means (`directory.subject_id`). Unreadable parts are empty, never guessed."""
    from nucleo import consent
    try:
        if spec.event:
            return consent.act_key(spec.event, spec.channel), "", [], spec.channel
        from nucleo import on_his_behalf as _ob
        from nucleo.flash import frontend as _fe
        from widgets import directory, runtime
        wid, act, inner = _ob._resolve(payload or {})
        man = runtime.get(wid) or {}
        sp = (man.get("actions") or {}).get(act)
        from rules import split_key
        cls, ch = split_key(_fe._policy_key(wid, act, sp if isinstance(sp, dict) else {}, inner) if wid and act else "")
        channel = ch or str(inner.get("platform") or inner.get("channel") or "")
        who = _ob.who_of(wid, act, inner) if wid and act else []
        subject = directory.subject_id(who[0], channel) if len(who) == 1 else ""
        return consent.act_key(cls, channel) if cls else "", subject, who, channel
    except Exception as e:  # noqa: BLE001 — the record names what it could read; the door's verdict stands
        logger.debug(f"exit_gate: the exit's event could not be read ({e!r})")
        return (spec.event, "", [], spec.channel)


def _emit(label: str, text: str, extra: dict) -> None:
    try:
        from voice.observer import emit
        emit("task", label, text=text, role="system", extra=extra)
    except Exception as e:  # noqa: BLE001 — the trace never stops the gate
        logger.debug(f"exit_gate: event not emitted ({e!r})")


def leaves(wid: str, act: str) -> bool:
    """Does this declared action leave the machine (`external.send`)? Unreadable → it leaves (it asks)."""
    try:
        from widgets import effects as _fx
        return bool(_fx.carries(wid, act, _fx.EXTERNAL_SEND))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"exit_gate: effects unread for {wid}:{act} ({e!r})")
        return True


def under_mandate(rec, kind: str, channel: str = "") -> bool:
    """Does the session's mandate cover this exit? `message` reads the errand rule itself (`mandate.covers`); any
    other kind must be named in `may`. No mandate → no."""
    m = getattr(rec, "mandate", None)
    if not isinstance(m, dict) or not m:
        return False
    from nucleo.errands.mandate import acts, covers
    if kind == "message":
        return covers({"mandate": m}, channel)
    return kind in acts(m.get("may")) or kind in [str(x) for x in (m.get("may") or [])]


def taint_question(rec, kind: str, action: str, target: str, channel: str = "") -> str:
    """'' when this exit may go; else the question for him — the session read a stranger's text since his last yes."""
    from nucleo.workers import taint
    if not taint.tainted(rec) or under_mandate(rec, kind, channel):
        return ""
    _emit("🛑 sale fuera tras leer texto de terceros — se le pregunta", f"{action} → {target}",
          {"id": str(getattr(rec, "task_id", "")), "exit": kind, "action": action, "target": target[:120]})
    try:
        from i18n import langs as _lg
        return _lg.current_language().worker_confirm_tainted.format(action=action, target=target or "?")
    except Exception:  # noqa: BLE001
        return f"{action} → {target}?"


def gate(rec, payload: dict) -> Exit:
    """The message door for one `widget_data` call of a worker. A call that does not leave passes untouched."""
    from nucleo import on_his_behalf as _ob
    wid, act, inner = _ob._resolve(payload or {})
    if not wid or not act or not leaves(wid, act):
        return Exit(payload)
    from nucleo.workers.prompts import playbook as _pbk
    if (first := _pbk.checkpoint_one(rec)):          # the harness: checkpoint 1 closes before anything leaves (T19b)
        _emit("🧭 checkpoint 1 abierto — el acto que sale espera", first, {"id": str(getattr(rec, "task_id", "")),
                                                                         "exit": f"{wid}:{act}"})
        return Exit(payload, refused=first)
    from widgets import contract as _contract     # an act that would refuse this call is said so before any question
    if (no := _contract.would_refuse(wid, act, inner)):
        why = str(no.get("message") or no.get("error") or "refused")
        _emit("🚫 the act would refuse this call — nothing is asked", f"{wid}:{act} · {why}"[:200],
              {"id": str(getattr(rec, "task_id", "")), "exit": f"{wid}:{act}", "error": str(no.get("error") or "")})
        return Exit(payload, refused=f"{wid}:{act} would be refused ({no.get('error') or 'refused'}): {why}")
    said = " ".join(_ob.errand_words(rec))
    from nucleo.turn import brief as _tb
    turn = _tb.revived(getattr(rec, "reading", None))   # the commissioning turn's reading (V2-852), or None
    from nucleo.acts import card, message
    for at in (card.LEAVES, card.FAST):
        lic = card.licence({"text": said, "brief": None}, wid, act, inner, at=at)
        if lic.verdict == card.DROP:
            _emit(lic.label or "🛑 vetoed", lic.text, {**(lic.extra or {}), "id": str(getattr(rec, "task_id", ""))})
            return Exit(payload, refused=f"{wid}:{act} not run ({lic.clause}): {lic.text}")
    out = dict(payload or {})
    # ONE question per declared slot (V2-857 phase 5, second slice): his word, the turn's reading, his order over the
    # held row, or a stranger's — the manifest's `slots` name the rule, `exit_slots` holds the mechanism
    from nucleo.workers import exit_slots
    got = exit_slots.read(rec, wid, act, inner, said=said, turn=turn,
                          call=out, emit=_emit)
    if got.inner != inner:
        out["payload"], inner = got.inner, got.inner
    from nucleo.workers import taint
    from widgets import actions as _wa
    who = ", ".join(_ob.who_of(wid, act, inner)) or wid
    channel = str(inner.get("platform") or inner.get("channel") or "")
    # The taint asks about WHAT leaves: a slot whose value the worker wrote after reading a stranger's text
    # (`stranger`). A send whose every declared slot is his, the turn's reading, the card's or the held row's carries
    # nothing a stranger could have steered — the taint is no question there (measured 2026-11-06: a text he dictated
    # himself was asked about because the worker had read the inbox to find the person).
    stranger = taint.tainted(rec) and not under_mandate(rec, "message", channel) and (
        not got.sources or "stranger" in got.sources.values())
    mode = message.asked_if_leaving(_wa.FAST, None, wid, act, payload=inner, said=said, stranger=stranger)
    q = taint_question(rec, "message", act, who, channel) if stranger else ""
    if not q and mode == _wa.CONFIRM:
        # the leave rule's question: a recipient his words do not name (with the taint: one only a stranger named)
        try:
            from i18n import langs as _lg
            q = _lg.current_language().worker_confirm_on_behalf.format(action=act, who=who)
        except Exception:  # noqa: BLE001
            q = f"{act} · {who}?"
    return Exit(out, question=q, released=got.released, slots=dict(got.sources))


def mesh(rec, payload: dict) -> Exit:
    """`mesh_serve`: the errand's request leaves to an agent that SERVES it — a query to a provider, like a web search,
    never a message to a person (V2-852 T14, re-cut on the C13 replay). It passes the leave door: the outbound scan
    first (`scan_outbound`, the cluster's detector: a hard secret sends nothing, identity terms are redacted, so what
    leaves is the request, not his data); then the one consent rule for the class with his standing rules
    (`errand.mesh_serve`: «never» refuses, «ask» asks, «allow» runs it); then the
    taint, read on WHAT leaves (asked after untrusted reads when the request carries his data — the scan redacted —
    unless a mandate names `mesh`) (the session read untrusted content since its last confirmed act → he is asked). No recipient rule: the
    agent is a provider the worker chose for the task, as it chooses a site. Every outcome is a `consequence` event on
    door `mesh.serve`, so a send is never invisible. The text that may leave is handed back to the bridge.

    Measured (V2-852, the first live session): the worker sent the errand to two third-party agents found by the
    oracle; the class rule alone (`standard` below `ask_at`) ran it with no question and no event before it."""
    p = dict(payload or {})
    text = str(p.get("prompt") or p.get("errand") or "")
    agent = str(p.get("agent") or "").strip()
    tid = str(getattr(rec, "task_id", ""))
    from nucleo.workers.prompts import playbook as _pbk
    if (first := _pbk.checkpoint_one(rec)):
        return _mesh_outcome(p, agent, tid, "refused", refused=first)
    try:
        from connectors.meshkore import security
        safe, block = security.scan_outbound(text)
        # what leaves carries HIS data when the scan had to redact (identity terms) — or could not look at all
        carries_his = (not security.enabled()) or safe != text
    except Exception as e:  # noqa: BLE001 — a scan that could not run is not a licence to send
        return _mesh_outcome(p, agent, tid, "refused", refused=f"the outbound scan could not run "
                                                              f"({type(e).__name__}): nothing was sent")
    if block:
        _emit("🛑 texto de encargo con un secreto — no sale a la red", block, {"id": tid, "exit": "mesh"})
        return _mesh_outcome(p, agent, tid, "refused", refused=f"the errand text carries a {block}: nothing was sent "
                                                              f"to a third-party agent — write the request without it")
    p["prompt"] = safe
    from nucleo import consent
    allowed = consent.class_policy(consent.act_key("errand.mesh_serve", "mesh")) == "allow" \
        or under_mandate(rec, "mesh")
    v = consent.decide_act("errand.mesh_serve", channel="mesh", licensed=True, his_yes=allowed)
    if v.get("verdict") == consent.REFUSE:
        return _mesh_outcome(p, agent, tid, "refused",
                             refused=f"his rule forbids it: {v.get('why') or 'mesh'} — nothing was sent")
    target = agent or str(p.get("errand") or "")[:60]
    # the taint reads WHAT leaves: a request the scan found nothing of his in carries nothing a stranger's text could
    # have steered out of him — a search reads the web by its nature, and asking each query would stop every search
    q = taint_question(rec, "mesh", "mesh serve", target) if carries_his else ""
    if not q and consent.asks(v):
        try:
            from i18n import langs as _lg
            q = _lg.current_language().worker_confirm_on_behalf.format(action="mesh serve", who=target or "?")
        except Exception:  # noqa: BLE001
            q = f"mesh serve → {target}?"
    return _mesh_outcome(p, agent, tid, "ask" if q else "pass", question=q,
                         why="" if q else ("his rule or mandate allows it" if allowed else "a service request: scanned, untainted"))


def _mesh_outcome(p: dict, agent: str, tid: str, verdict: str, *, question: str = "", refused: str = "",
                  why: str = "") -> Exit:
    """The exit's one record: a `consequence` event (door `mesh.serve`) with its verdict, then the Exit itself."""
    try:
        from nucleo import consequence
        if not consequence.passes("mesh.serve", task_id=tid, agent=agent or "?", gate=verdict,
                                  why=(refused or why)[:160]) and not refused:
            refused = "this turn reaches no door (a dry run): nothing was sent"
    except Exception as e:  # noqa: BLE001 — the record never decides the exit
        logger.debug(f"exit_gate: mesh consequence not recorded ({e!r})")
    return Exit(p, question=question, refused=refused)


#: The bridge acts that LEAVE, declared once: the door each crosses and how its event type is read. An act not declared
#: here does not leave (`leave` returns None); a new leaving act declares itself here, never as a branch by its name.
EXITS: tuple[ExitSpec, ...] = (ExitSpec("widget_data", "gate"),
                              ExitSpec("mesh_serve", "mesh", event="errand.mesh_serve", channel="mesh"))
