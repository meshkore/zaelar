"""tests/widget_data_rig.py — one `widget_data` call through the REAL data-op gate, and what it ended in.

A test hands the card, the action, the payload, his words and the turn's brief; this runs
`tool_executor_widget_calls._apply_widget_data` with every gate it has (held row, two readers on an act that leaves,
the ordered send, the stranger's-text gate) and stops at the two places an act leaves the gate:

  · `ran`    — the ops that STARTED (`data_ops.start_op`), as `(card, action, payload)`; nothing is dispatched;
  · `asked`  — the ops held for his yes (`_request_data_confirm`), same shape;
  · `events` — every `(kind, label)` the gate emitted.

The brief is a plain dict, or `brief(...)` builds one the way `turn_brief.read` reads it. Shared by the message door
(refactor2710-06) and the card door (refactor2710-05).
"""
from __future__ import annotations

from types import SimpleNamespace


def brief(screen_action: str = "", confidence: float = 0.95, *, kind: str = "order", open_ids=("mensajeria",)) -> dict:
    """A settled turn brief whose `screen_action` reads `card:action` at `confidence` and whose request is `kind`."""
    import threading
    ev = threading.Event()
    ev.set()
    result = {"request_type": {"choice": kind, "confidence": 1.0}}
    if screen_action:
        result["screen_action"] = {"choice": screen_action, "confidence": confidence}
    return {"event": ev, "turn_id": "t-rig", "open_ids": list(open_ids), "result": result}


def run(card: str, action: str, payload: dict | None = None, *, said: str = "", turn_brief=None,
        monkeypatch=None) -> SimpleNamespace:
    """Drive one data-op through the gate. `monkeypatch` (pytest's) keeps the dispatch stub to this test."""
    from nucleo.flash import frontend, tool_executor_widget as txw, tool_executor_widget_calls as calls
    out = SimpleNamespace(ran=[], asked=[], events=[])

    def start_op(wid, act, pay, **_kw):
        out.ran.append((wid, act, dict(pay or {})))
        return None

    if monkeypatch is not None:
        monkeypatch.setattr(txw._data_ops, "start_op", start_op)
    else:
        txw._data_ops.start_op = start_op
    state = {"acted": {"widget": False}, "data_done": {"v": False}, "deduped": {"v": False}, "escalate": {"v": None}}
    brain = SimpleNamespace(_window=[], _last_dataop=None, _last_spoken="", _last_action="")

    def apply(wid, act, pay, ref=""):
        calls._apply_widget_data(
            wid, act, pay, ref, _apply_widget_data=apply, _brief=turn_brief, _frontend=frontend,
            _request_data_confirm=lambda w, a, p: out.asked.append((w, a, dict(p or {}))),
            _spawn=lambda *a, **k: None, _tag_emit=lambda *a, **k: None, _turn_op_tasks=[],
            acted=state["acted"], brain=brain, data_done=state["data_done"], deduped=state["deduped"],
            emit=lambda kind, label, **k: out.events.append((kind, label)), escalate_req=state["escalate"],
            text=said)
    apply(card, action, dict(payload or {}))
    return out
