"""nucleo/canvas_focus.py — which card «it» / «that» means: the one the operator's LAST TURN acted on.

The canvas's own stack could not say it (demo pass 2026-09-28). z named the agenda over a worker's sheet that had
opened underneath it (A2); «last to arrive» then named a monitor sheet that popped up in the background while he
was watching a video (V3: «Make it fullscreen» filled the screen with the sheet). What «it» points at is the
conversation's subject, and the engine sees that directly: the cards the previous turn touched.

Fed from the event funnel (`voice.observer.emit`): an operator turn (`transcript`, role user) closes the window of
the turn before it; `widget` events inside a window are that turn's touches. What HE ordered — the fast lane, the
model, the probe (`actionmap` / `flash` / `probe` / `jev`) — wins over a worker's show inside the same window,
which only counts when nothing else was touched (A1: the errand he just commissioned opens its sheet). The
operator's own tab echoing the canvas back (`src: user`) and system housekeeping never count.
"""
from __future__ import annotations

import threading

_ACTS = ("show", "fullscreen", "maximize", "minimize", "action", "select")
_OPERATOR = ("actionmap", "flash", "probe", "jev")
_lock = threading.Lock()
_state = {"current": [], "previous": [], "fs": ""}


def _src_rank(src: str) -> int:
    s = str(src or "")
    if s.split(":", 1)[0] in _OPERATOR:
        return 2
    if s.startswith("worker"):
        return 1
    return 0


def note(kind: str, label: str, role: str = "", extra: dict | None = None) -> None:
    """One event from the funnel. Cheap and never raises: this runs on every event the engine emits."""
    try:
        if kind == "transcript" and role == "user":
            with _lock:
                if _state["current"]:
                    _state["previous"] = _state["current"]
                _state["current"] = []
            return
        if kind != "widget":
            return
        e = extra or {}
        cid = str(e.get("id") or "").strip()
        rank = _src_rank(e.get("src"))
        lab = str(label or "")
        # The full screen HE ordered, until something undoes it — a second witness for «exit fullscreen» when
        # the canvas report says nothing (two tabs report, and the last one to speak may not be maximised:
        # demo pass 2026-09-28, V4 answered «Done, back to normal» and left the video at full screen).
        if cid and rank == 2 and lab == "fullscreen":
            with _lock:
                _state["fs"] = cid
        elif cid and lab in ("minimize", "close") and cid.split("::", 1)[0] == _state["fs"].split("::", 1)[0]:
            with _lock:
                _state["fs"] = ""
        if not cid or not rank or not (lab in _ACTS or lab.startswith("data:")):
            return
        with _lock:
            _state["current"].append((rank, cid))
    except Exception:  # noqa: BLE001
        pass


def last_turn_card(open_ids: list[str]) -> str:
    """The card the previous turn acted on, among the cards open NOW — or "" when none of them is one."""
    with _lock:
        touched = list(_state["previous"])
    if not touched:
        return ""
    ids = [str(i) for i in open_ids if str(i)]
    best = max(r for r, _ in touched)
    for _, cid in reversed([t for t in touched if t[0] == best]):
        if cid in ids:
            return cid
        same_base = [i for i in ids if i.split("::", 1)[0] == cid.split("::", 1)[0]]
        if len(same_base) == 1:
            return same_base[0]
    return ""


def ordered_fullscreen() -> str:
    """The card his own order put at full screen and nothing has taken out since, or ""."""
    with _lock:
        return _state["fs"]


def _reset() -> None:                                   # tests
    with _lock:
        _state["current"], _state["previous"], _state["fs"] = [], [], ""
