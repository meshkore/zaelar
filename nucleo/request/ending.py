"""nucleo/request/ending.py — «acted» is the request's `done_when` met: a view never ends a request about a send (V2-851 F2e).

Measured after F2d: «send Rachel a message…» — the model first called `mensajeria:show_view` (a lens), the data-op door
settled the turn's row `done` with an `undeclared` verdict, and then the reply asked «which Rachel?». The row had
ended, so the question could not wait on it (an ended row is never re-opened), and the turn counted as acted, so
`ask_outside_door` never measured it. A request about an act that LEAVES ends on that act's echo, never on a view, a
draft or a show of the same card.

The rule, at the one door every inline data-op crosses (`nucleo/flash/data_ops.dispatch_and_report`), for an act that
does NOT leave the machine on a card that DECLARES acts that do (`widgets.effects.leaves`), and that only shows or
prepares (a lens — no `data.write` — or an act that mounts the card, a draft; never one that answers):

  · the turn's verdict identifies one of that card's leaving acts (`screen_action` names it, or the `end_state`
    verdict names the echo a leaving act's template attests) → the act writes NO ending: the row's end is the
    leaving act's echo (`hold` → `VERDICT`);
  · otherwise, inside a live turn, its ending is written when the turn closes (`close_turn`) — unless the same turn
    ran one of the card's leaving acts on that row (that act writes the end), or the turn ended
    on our own question about that card's leaving act, which makes the row WAIT instead (`own_question.held`)
    (`hold` → `TURN`). An op that lands after its turn closed writes its ending at once, unless the row now waits;
    a turn whose end never comes writes what it held after `STALE_S`.

`only_held()` tells the turn's end that every data-op it ran was one of these, so the question about the leaving act
is measured and made durable as if nothing had acted. Reads declared effects and verdicts only — never his words.
"""
from __future__ import annotations

import time

from nucleo.request import base, note

VERDICT, TURN = "verdict", "turn"
#: A turn whose end never came (a path that did not reach `close_turn`) writes what it held after this long.
STALE_S = 30.0
_OPEN: list = []


def leaving_acts(wid: str) -> list[str]:
    """The card's declared acts that leave the machine."""
    try:
        from widgets import effects
        card = base(wid)
        return sorted(a for a in (effects._manifest(card).get("actions") or {}) if effects.leaves(card, a))
    except Exception as e:  # noqa: BLE001
        note(e)
        return []


def verdict_names_leaving(brief, wid: str) -> bool:
    """Does the turn's verdict identify one of `wid`'s leaving acts — by the act, or by the end state it attests?"""
    if not brief:
        return False
    acts = leaving_acts(wid)
    if not acts:
        return False
    try:
        from nucleo.flash import direct_action as _da
        owner, name = _da.from_brief(brief)
        if base(owner) == base(wid) and name in acts:
            return True
        from nucleo.circuit import spec
        want = spec.end_state_verdict(brief)
        return bool(want) and any(spec.target_of(spec.template_of(base(wid), a) or {}) == want for a in acts)
    except Exception as e:  # noqa: BLE001
        note(e)
        return False


def shows_or_prepares(wid: str, action: str) -> bool:
    """The act only shows the card or prepares on it (a lens, a draft it mounts) — never a write of its own, a send or
    an answer. Read off the declared effects."""
    from widgets import effects
    fx = effects.of(base(wid), action)
    if effects.EXTERNAL_SEND in fx or effects.OUTPUT_ANSWER in fx:
        return False
    return effects.PRESENT_MOUNT in fx or (effects.DATA_READ in fx and effects.DATA_WRITE not in fx)


def _turn() -> dict | None:
    try:
        from nucleo.request import model
        return model.current()
    except Exception as e:  # noqa: BLE001
        note(e)
        return None


def hold(wid: str, action: str, row: str, brief=None) -> str:
    """How this op's ending is written: "" as always, `VERDICT` never, `TURN` when its turn closes. Counts the op."""
    turn = _turn()
    how = ""
    try:
        from widgets import effects
        if row and not effects.leaves(base(wid), action) and shows_or_prepares(wid, action) and leaving_acts(wid):
            if brief is None:
                from nucleo.turn import brief as _tb
                brief = _tb.of_this_turn()
            if verdict_names_leaving(brief, wid):
                how = VERDICT
            elif turn is not None and not turn.get("closed"):
                how = TURN
    except Exception as e:  # noqa: BLE001 — unreadable: the op writes its ending as always
        note(e)
        how = ""
    if turn is not None:
        if row and not how and _leaves(wid, action):
            turn.setdefault("left", set()).add(str(row))     # the row's end is this act's: a held view never writes it
        turn["ops"] = int(turn.get("ops") or 0) + 1
        if how:
            turn["held_ops"] = int(turn.get("held_ops") or 0) + 1
    return how


def _leaves(wid: str, action: str) -> bool:
    try:
        from widgets import effects
        return effects.leaves(base(wid), action)
    except Exception as e:  # noqa: BLE001
        note(e)
        return False


def _waits(row: str) -> bool:
    try:
        from nucleo.circuit import ledger
        return str((ledger.get(row) or {}).get("state") or "") == "waiting"
    except Exception as e:  # noqa: BLE001
        note(e)
        return False


def defer(row: str, write) -> None:
    """Write an op's ending (`write()`) when its turn closes; at once when the turn already closed — never over a
    row that now waits on our question."""
    turn = _turn()
    _close_stale(turn)
    if turn is not None and not turn.get("closed"):
        turn.setdefault("endings", []).append((str(row or ""), write))
        if not any(t is turn for t in _OPEN):
            turn["held_at"] = time.time()
            _OPEN.append(turn)
            import threading
            t = threading.Timer(STALE_S, close_turn, args=(turn,))
            t.daemon = True
            t.start()
        return
    if not _waits(row) and str(row or "") not in ((turn or {}).get("left") or ()):
        write()


def only_held() -> bool:
    """Every data-op this turn ran was a non-leaving act whose ending is held: nothing reached the request's end."""
    turn = _turn() or {}
    ops = int(turn.get("ops") or 0)
    return ops > 0 and int(turn.get("held_ops") or 0) == ops


def _close_stale(current: dict | None) -> None:
    now = time.time()
    for t in [t for t in _OPEN if t is not current and now - float(t.get("held_at") or now) > STALE_S]:
        close_turn(t)


def close_turn(turn: dict | None = None) -> int:
    """The turn is over: write the endings it held, except over a row that now waits. How many were written."""
    turn = turn if turn is not None else _turn()
    if turn is None:
        return 0
    turn["closed"] = True
    _OPEN[:] = [t for t in _OPEN if t is not turn]
    n = 0
    left = turn.get("left") or set()
    for row, write in turn.pop("endings", []) or []:
        if _waits(row) or row in left:
            continue                             # the row waits on our question, or a leaving act writes its end
        try:
            write()
            n += 1
        except Exception as e:  # noqa: BLE001
            note(e)
    return n
