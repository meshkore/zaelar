"""The turn a canvas act belongs to, read off the observer stream: his words (25 s), their credit, our last reply and
the brief's verdict by trace — what the arbiter judges with. `shadow_tap` keeps it and still judges, unenforced, what
does not cross the door; `_emit_verdict` writes the `arbiter` event (refactor2710-04)."""
from __future__ import annotations

import contextlib
import time

from nucleo.acts import canvas_arbiter as _tree
from nucleo.acts.canvas_arbiter import Verdict, _note

@contextlib.contextmanager
def judged():
    """While the door emits what it already judged, the tap must not judge it a second time."""
    global _in_tap
    prev, _in_tap = _in_tap, True
    try:
        yield
    finally:
        _in_tap = prev


_TURN_TTL_S = 25.0
_last_turn: dict = {"text": "", "ts": 0.0, "credit": True, "reply": ""}
_in_tap = False                     # re-entrancy guard: our own verdict emit must not re-enter the tap
#: trace → {key: (choice, confidence)}: the brief's answers, read off its `jev read <key>` events.
_reads: dict[str, dict] = {}
_READS_KEPT = 64


def _trace_of(ex: dict) -> str:
    """The event's trace: the caller's own, else the stimulus in flight (the observer stamps the same one)."""
    if ex.get("trace"):
        return str(ex["trace"])
    try:
        from voice import trace as _trace
        return str(_trace.current() or "")
    except Exception as e:  # noqa: BLE001
        _note(f"no trace in flight: {e!r}")
        return ""


def request_for(extra: dict | None = None) -> dict:
    """The turn a canvas act belongs to, as `decide` reads it: his words (25 s), their credit, our last reply and
    the brief's verdict on that trace — what the door passes when its caller did not bring its own."""
    text, credit = _turn_text()
    return {"text": text, "turn_credit": credit, "last_reply": str(_last_turn.get("reply") or ""),
            "verdict": dict(_reads.get(_trace_of(extra or {}), {}))}


def request_of(brief=None, text: str | None = None, *, credit: bool | None = None) -> dict:
    """The same request, from a door that holds the turn's brief handle: its verdict read with the turn's own
    reader (`turn_brief.read`, at any confidence — the tree applies its own lines); his words and their credit
    from the call, else from the stream."""
    req = request_for()
    if text is not None:
        req["text"] = str(text)
    if credit is not None:
        req["turn_credit"] = credit
    if brief is None:
        return req
    from nucleo.flash import turn_brief as _tb
    verdict = {}
    for key in (_tb.CANVAS_KEY, _tb.TARGET_KEY, _tb.CATALOG_KEY):
        choice, info = _tb.read(brief, key, "", min_confidence=0.0)
        if choice:
            info = info or {}
            sure = 1.0 if info.get("used") else 0.0          # a read the turn USED already passed jev's own line
            verdict[key] = (str(choice), float(info.get("confidence") or sure))
    req["verdict"] = verdict or req["verdict"]
    return req


def _note_read(ex: dict) -> None:
    from nucleo.flash import turn_brief as _tb
    trace, key = _trace_of(ex), str(ex.get("question") or "")
    if not trace or key not in (_tb.CANVAS_KEY, _tb.TARGET_KEY, _tb.CATALOG_KEY):
        return
    _reads.setdefault(trace, {})[key] = (str(ex.get("choice") or ""), float(ex.get("confidence") or 0))
    while len(_reads) > _READS_KEPT:
        _reads.pop(next(iter(_reads)))

#: op labels as they travel on the observer's `widget` events today.
_SHOW_LABELS = ("show",)
_CLOSE_LABELS = ("close",)


def _turn_text() -> tuple[str, bool]:
    if time.time() - _last_turn["ts"] <= _TURN_TTL_S:
        return _last_turn["text"], bool(_last_turn["credit"])
    return "", True


def shadow_tap(kind: str, label: str, text: str, role: str, extra: dict | None) -> None:
    """Called by `voice/observer.emit` for every recorded event: keeps the turn the door reads and judges, as
    shadow, what did not cross the door. Never raises, never mutates the event it observes."""
    global _in_tap
    if _in_tap:
        return
    try:
        _in_tap = True
        ex = extra or {}
        if kind == "transcript" and role == "user":
            _last_turn.update(text=str(text or ""), ts=time.time(), credit=True)
            return
        if kind == "transcript" and role == "assistant":
            # a bare «yes» licenses only as the answer to what WE asked (V2-723): our side is kept too
            _last_turn["reply"] = str(text or "")
            return
        if kind == "brain" and str(label or "").startswith("jev read "):
            _note_read(ex)
            return
        if kind == "ambient":
            # the gate's own verdict for the turn: 🙉 removes credit, 👂 restores it
            if "🙉" in (label or ""):
                _last_turn["credit"] = False
            elif "dirigido" in (label or "") or "👂" in (label or ""):
                _last_turn["credit"] = True
            return
        if kind != "widget":
            return
        op, action = "", ""
        if label in _SHOW_LABELS:
            op, action = "show", str(ex.get("action") or "")   # V2-721: a mount names the action that produces
        elif label in _CLOSE_LABELS:
            op = "close"
        elif isinstance(label, str) and label.startswith("data:"):
            op, action = "data", label.split(":", 1)[1]
        elif label == "action":
            # the order event both data funnels emit; a flash one was already judged at its `data:*` log
            op, action = "data", str(ex.get("action") or "")
        if not op:
            return
        wid = str(ex.get("id") or "").strip().lower()
        src = str(ex.get("src") or "") or _prov_src(wid)
        if label == "action" and src.split(":", 1)[0] == "flash":
            return
        if src == "client:engine":      # `voice.canvas_src.of(BY_ENGINE)`
            return          # the canvas echoing an engine command: that command was judged when it was issued
        # a data:* log carries its own phrase and payload; show/close borrow the assembled last turn
        turn, credit = (str(text or ""), True) if op == "data" and text else _turn_text()
        payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
        brief = dict(_reads.get(_trace_of(ex), {}))
        verdict = _tree.decide(op, wid, src, action=action, payload=payload, text=turn, turn_credit=credit,
                         last_reply=str(_last_turn.get("reply") or ""), verdict=brief)
        _emit_verdict(op, wid, src, action, verdict, shadow=True, brief=brief)
    except Exception:  # noqa: BLE001
        pass
    finally:
        _in_tap = False


def _prov_src(wid: str) -> str:
    try:
        from widgets import provenance
        return provenance.who(wid)
    except Exception:  # noqa: BLE001
        return "system"


def _emit_verdict(op: str, wid: str, src: str, action: str, verdict: Verdict, *, shadow: bool,
                  brief: dict | None = None) -> None:
    try:
        from voice.observer import emit
        face = ("✅ permitiría" if verdict.allow else "⛔ vetaría") if shadow else \
               ("✅ permitida" if verdict.allow else "⛔ vetada")
        emit("arbiter", f"{face} · {verdict.rule}",
             text=f"{op} {wid}" + (f":{action}" if action else ""),
             role="system",
             extra={"op": op, "id": wid, "action": action, "src": src, "allow": verdict.allow,
                    "rule": verdict.rule, "shadow": shadow, "source": src,
                    "verdict": {k: {"choice": c, "confidence": round(f, 2)} for k, (c, f) in (brief or {}).items()},
                    **({"ev": verdict.evidence} if verdict.evidence else {})})
    except Exception:  # noqa: BLE001
        pass
