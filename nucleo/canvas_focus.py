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
import time

_ACTS = ("show", "fullscreen", "maximize", "minimize", "action", "select")
_OPERATOR = ("actionmap", "flash", "probe", "jev")
_lock = threading.Lock()
_state = {"current": [], "previous": [], "fs": "", "acts": [], "failed": [], "t_cur": 0.0, "t_prev": 0.0}
#: How long after his order an unprompted report still counts as crossing that exchange (`crossed_by`).
CROSSING_S = 30.0


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
                _state["t_prev"], _state["t_cur"] = _state["t_cur"], time.monotonic()
                _state["acts"] = []
                _state["failed"] = []
            return
        if kind != "widget":
            return
        e = extra or {}
        cid = str(e.get("id") or "").strip()
        if label == "action_failed" and cid:
            # The `data:<act>` event is the ORDER, emitted before dispatch; a control the card refused did not
            # happen, and the receipt must not name it (`flash.transport_receipt`, 2026-10-11).
            with _lock:
                _state["failed"].append((cid.split("::", 1)[0], str(e.get("action") or "")))
            return
        rank = _src_rank(e.get("src"))
        lab = str(label or "")
        if e.get("already_open"):
            # A show of a card that is already up is still the turn aiming at it (demo pass 2026-09-28, U3: «no,
            # put like a prayer» played on the open music card; «pause it a sec» then paused the VIDEO card).
            lab = "show"
        # The full screen HE ordered, until something undoes it — a second witness for «exit fullscreen» when
        # the canvas report says nothing (two tabs report, and the last one to speak may not be maximised:
        # demo pass 2026-09-28, V4 answered «Done, back to normal» and left the video at full screen).
        if cid and rank == 2 and lab == "fullscreen":
            with _lock:
                _state["fs"] = cid
        elif cid and lab in ("minimize", "close") and cid.split("::", 1)[0] == _state["fs"].split("::", 1)[0]:
            with _lock:
                _state["fs"] = ""
        if cid and rank == 2 and (lab in ("show", "close") or lab.startswith("data:")):
            with _lock:   # what HIS turn did to each card, for the receipt (`flash.card_receipt.voice_ack`)
                _state["acts"].append((cid, lab))
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


def crossed_by(at: float, about: str) -> bool:
    """A report said at `at` about card `about` crossed his last exchange: said within `CROSSING_S` of that order,
    while the card his order acted on is ANOTHER one. Unknown card or no order of his to cross: False."""
    base = str(about or "").split("::", 1)[0]
    with _lock:
        touched, t_prev = list(_state["previous"]), _state["t_prev"]
    mine = [cid for r, cid in touched if r == 2]
    if not base or not mine or not t_prev or not (0.0 <= at - t_prev <= CROSSING_S):
        return False
    return all(cid.split("::", 1)[0] != base for cid in mine)


def this_turn_acts() -> list[tuple[str, str, str]]:
    """`[(card, kind, action)]` — what the CURRENT turn's own orders did to each card (kind close / show / control),
    one entry per card, a close over a show over a control. The voice channel's receipt (`flash.card_receipt`)."""
    with _lock:
        acts = list(_state["acts"])
        failed = set(_state["failed"])
    best: dict[str, tuple[str, str, str]] = {}
    rank = {"close": 0, "show": 1, "control": 2}
    for cid, lab in acts:
        kind, action = (("control", lab[5:]) if lab.startswith("data:") else (lab, lab))
        if action == "close":
            kind = "close"
        base = cid.split("::", 1)[0]
        if kind == "control" and (base, action) in failed:
            continue
        if base not in best or rank[kind] < rank[best[base][1]]:
            best[base] = (base, kind, action)
    return list(best.values())


def this_turn_cards() -> list[str]:
    """The cards the CURRENT turn has acted on so far — his orders first — for a later pass of the same turn that
    cannot see the calls (the web-search answer said «I can't display a chart» over the chart this turn opened)."""
    with _lock:
        cur = list(_state["current"])
    out: list[str] = []
    for _, cid in sorted(cur, key=lambda t: -t[0]):
        base = cid.split("::", 1)[0]
        if base not in out:
            out.append(base)
    return out


def ordered_fullscreen() -> str:
    """The card his own order put at full screen and nothing has taken out since, or ""."""
    with _lock:
        return _state["fs"]


def _reset() -> None:                                   # tests
    with _lock:
        _state["current"], _state["previous"], _state["fs"] = [], [], ""
        _state["acts"], _state["failed"] = [], []
        _state["t_cur"], _state["t_prev"] = 0.0, 0.0
