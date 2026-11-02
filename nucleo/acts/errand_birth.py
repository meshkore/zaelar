"""An errand is born IN its turn (V2-844 F1a): its id, its durable row and his WHOLE request, before anything of it runs.

The turn that decides an errand is the one that names it. Until this, an errand existed only when the dispatcher picked
its escalation up, so whatever the turn opened for it before that belonged to nobody, under a counter id of its own,
and its request was whatever words the door had in hand — the tail of a cut sentence included. `born` gives the id and
the uid (which is also the sheet's id) at once and hands the row to ONE ordered writer, so the turn never waits on the
store and the row's birth always lands before its end; `whole_request` is the request every door names an errand by.
"""
from __future__ import annotations

from loguru import logger

from nucleo.runtime_ids import next_seq as _next_seq

def whole_request(text: str) -> str:
    """The request an errand of THIS turn is about (V2-844 F1a): what the turn's verdict judged — a cut, unanswered
    sentence joined with its tail (`accumulator.whole_turn`) — when `text` is only a fragment of it (its content words a
    strict part of the whole: «Okay.», «Sorry.», «the price, thirty to fifty»). Anything else, a model's own wording
    included, stays as it is. The house content measure, no word list of ours."""
    text = str(text or "").strip()
    try:
        from nucleo import matching
        from nucleo.acts.errand import strip_system_notes
        from nucleo.turn import brief as _tb
        whole = strip_system_notes(_tb.judged_text(_tb.of_this_turn(), "")).strip()
        if whole and whole != text and matching.content_words(text) < matching.content_words(whole):
            return whole
    except Exception as e:  # noqa: BLE001 — no verdict to read: the words as given
        logger.debug(f"escalate: no whole request for the turn ({e!r})")
    return text


_ROWS = None   # ONE writer for the rows a turn's errand writes: in order (birth before its end), off the turn's path


def row_write(fn, *args) -> None:
    """Hand a durable-row write of a turn's errand to the one ordered writer: the turn never waits on the store."""
    global _ROWS
    if _ROWS is None:
        from concurrent.futures import ThreadPoolExecutor
        _ROWS = ThreadPoolExecutor(max_workers=1, thread_name_prefix="errand-rows")
    _ROWS.submit(fn, *args)


def rows_settled(timeout: float = 5.0) -> None:
    """Wait until every row handed to the writer is written (a reader that must see them, a test)."""
    if _ROWS is not None:
        _ROWS.submit(lambda: None).result(timeout=timeout)


def born(request: str, ctx: dict | None = None) -> tuple[int, str]:
    """An errand born IN the turn, before anything of it runs (V2-844 F1a): its id and its durable row's uid, which is
    also its sheet's id. The ids are known at once; the row is written by the ordered writer, before anything else of
    it. The dispatcher adopts the row when a worker is needed; the turn's own fast pass closes it when it delivers."""
    from nucleo.circuit import ledger as _ledger
    tid = _next_seq("escalate.task")
    row_write(_ledger.born, tid, whole_request(request), dict(ctx or {}))
    return tid, _ledger.task_uid(tid)


