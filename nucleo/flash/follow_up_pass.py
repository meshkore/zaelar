"""First words vs the tool round (V2-831 T-19 R5b, R16; V2-851 F5).

Under a sure ANSWER verdict the first words wait for the model's call (`Hold`): words that narrated a call the verdict
replaced are never said, and the op's answer is the first words. Every round is measured apart (`turn_perf.note_pass`).

A confirm-or-correct pass used to run DETACHED after the turn and speak a correction as a late follow-up (`detach`,
`deliver` — a second mouth, «🗣 the turn's follow-up»). V2-851 F5 removed it: a tool round is said inside its turn,
through the turn's own mouth, or not at all; nothing speaks for a turn after its reply.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger


def _messages(sys2: str, user_text: str) -> list[dict]:
    return [{"role": "system", "content": sys2}, {"role": "user", "content": user_text}]


def _note(what: str, t0: float, m: dict, n_chars: int, detached: bool) -> dict:
    from nucleo.flash import turn_perf
    from nucleo.llm.fast_client import est_tokens
    return turn_perf.note_pass(what, int((time.monotonic() - t0) * 1000), detached=detached, ttft_ms=m.get("ttft_ms"),
                               prompt_tokens=int(m.get("prompt_tokens") or est_tokens(n_chars)))


async def measured(client, sys2: str, user_text: str, spec, max_tokens: int, what: str):
    """The inline pass's stream, unchanged, noted for the turn's verdict."""
    m, t0 = {}, time.monotonic()
    try:
        async for delta in client.stream(_messages(sys2, user_text), spec=spec, max_tokens=max_tokens, metrics=m):
            yield delta
    finally:
        _note(what, t0, m, len(sys2) + len(user_text), False)


def _unrun_model_card(model_calls, ran_ops) -> str:
    """The card of the last `widget_data` call the MODEL made this turn that did not run (a guard's discard does not
    make its card unknown) — "" when none. Moved in from `turn/promise_repair.py` when it went (V2-851 F2)."""
    ran = {(_card(w), str(a or "")) for w, a in (ran_ops or ()) if w}
    for c in reversed(list(model_calls or ())):
        if not isinstance(c, dict) or c.get("name") != "widget_data":
            continue
        args = c.get("args") if isinstance(c.get("args"), dict) else {}
        wid, act = _card(args.get("widget_id")), str(args.get("action") or "")
        if wid and (wid, act) not in ran:
            return wid
    return ""


class Hold:
    """The streamed words, held under a SURE `screen_action` that ANSWERS (`output.answer`) — the model's first words are
    speculative there. Decided at the FIRST word: the brief often lands after the stream opens (pass 5, C2)."""

    def __init__(self, brief, send, wait_s: float = 0.0, route_wait_s: float = 0.0):
        self.brief, self.card, self.send, self.held, self.deferred = brief, None, send, [], ""
        # V2-851 F5 — the third holder: a SURE «escalate» verdict routes the request to its task, and the model's
        # words of that turn are never said (`nucleo/turn/route_by_verdict`). None until known; `route_wait_s` = 0
        # (a caller that hands no wait) decides at once from what is ready.
        self.routed, self.route_pending, self.route_wait_s = None, [], float(route_wait_s or 0.0)
        # V2-833 F8 — the second holder: a sentence the brief read as UNREADABLE. Undecided (None) until the first
        # word finds the verdict, or `wait_s` passes — the lead-in filler's own deadline, handed in by the channel
        # (the time the engine already treats as «he is fine without words»); `unread` is what the turn answers with.
        self.unclear, self.pending, self.unread, self.t0, self.wait_s = None, [], "", time.monotonic(), float(wait_s or 0.0)
        # V2-852 T04 — the fourth holder: a stop verdict IN PLAY (`stop.in_play`). Words that may narrate a stop wait
        # for its door; the turn says them, or the rows' state, after its acts (`stop.say_the_row`).
        self.stop_held, self.stop_pending, self.stop_words = None, [], ""

    def say(self, piece: str) -> None:
        if piece and self.routed is None:
            from nucleo.turn import route_by_verdict as _route
            self.routed = _route.decided(self.brief, self.t0, self.route_wait_s)
        if piece and (self.routed is None or self.routed):
            self.route_pending.append(piece)          # in flight: wait for the verdict · routed: never said
            return
        if self.route_pending:
            pend, self.route_pending = self.route_pending, []
            for p in pend:
                self._say(p)
        self._say(piece)

    def _say(self, piece: str) -> None:
        if piece and self.unclear is None:
            self.unclear = _unclear_at_first_word(self.brief, self.t0, self.wait_s)
            if self.unclear is None:
                self.pending.append(piece)            # the brief is still in flight: the words wait for it
                return
            self._settle_pending()
        if piece and self.unclear:
            self.pending.append(piece)                # unreadable: nothing is said until we know the pass ACTED
            return
        self._route(piece)

    def _route(self, piece: str) -> None:
        if piece and self.stop_held is None:
            from nucleo.request import stop_row as _stop_row
            self.stop_held = _stop_row.in_play(self.brief)
        if piece and self.stop_held:
            self.stop_pending.append(piece)
            return
        self.card = holds(self.brief) if piece and self.card is None else self.card
        (self.held.append if piece and self.card else self.send)(piece)

    def _settle_pending(self) -> None:
        if not self.unclear:
            pend, self.pending = self.pending, []
            for p in pend:
                self._route(p)

    async def _release_unclear(self, model_calls, emit) -> None:
        """The stream ended on an unreadable sentence: a pass that made an ACT read it after all — its words are said;
        one that called nothing (or only read: memory, a card) is dropped unsaid and the turn answers with
        `unclear_turn` instead. A stream that ended before the brief landed WAITS for it, up to the deadline: a check
        per chunk is not a wait, and a short reply has no later chunk to check on."""
        from nucleo.flash import unclear_turn
        if self.unclear is None:
            left = self.wait_s - (time.monotonic() - self.t0)
            if left > 0 and self.brief and not _ready(self.brief):
                try:
                    await asyncio.to_thread(self.brief["event"].wait, left)
                except Exception as e:  # noqa: BLE001 — an unawaitable brief reads as in flight
                    logger.debug(f"follow_up_pass: the brief was not awaited — {e!r}")
            self.unclear = unclear_turn.verdict(self.brief)
            self._settle_pending()
        if not self.unclear:
            return
        words, self.pending = "".join(self.pending), []
        if any((n := str((c or {}).get("name") or "")) and n not in unclear_turn.READS for c in model_calls or ()):
            self._route(words)
            return
        self.unread = self.unclear
        emit("brain", "🤐 unreadable turn — the reflex words are not said", role="system", text=words[:160],
             extra={"cat": "flash", "readable": self.unclear})

    async def release(self, model_calls, ran_ops, emit, op_tasks=()) -> None:
        """The stream ended: the held words are said — unless the model's call on that card did not run as made, or an
        answer op there RETURNED data (words written before it are a guess, pass 7 C2): its answer is the first words.
        Under a sure «escalate» verdict nothing the model wrote is said (V2-851 F5)."""
        if await self._release_routed(emit):
            return
        await self._release_unclear(model_calls, emit)
        self.stop_words, self.stop_pending = self.stop_words + "".join(self.stop_pending), []
        text, self.held[:] = "".join(self.held), []
        if text and not any(_card(w) == self.card for w, _a in ran_ops or ()):
            # no op of the stream touched the held card: its answer comes later (the verdict's completion), so these
            # words were written before any data — they wait for the turn's end (`flush`), pass 9 C2
            self.deferred = text
            emit("brain", "⏳ held words wait — the card's answer has not run yet", role="system", text=text[:160],
                 extra={"cat": "flash", "card": self.card})
        elif text and (_unrun_model_card(model_calls, ran_ops) == self.card
                     or await self._answered(ran_ops, op_tasks)):
            emit("brain", "🤐 the words were written before the data (or narrated another call) — not said",
                 role="system", text=text[:160], extra={"cat": "flash", "card": self.card})
        elif text:
            self.send(text)

    async def _release_routed(self, emit) -> bool:
        """The stream ended: decide the route if the first word did not (waiting what is left of the wait). True when
        the turn is routed to its task — its held words are dropped, unsaid."""
        from nucleo.turn import route_by_verdict as _route
        if self.routed is None:
            left = self.route_wait_s - (time.monotonic() - self.t0)
            if left > 0 and self.brief and not _route.ready(self.brief):
                try:
                    await asyncio.to_thread(self.brief["event"].wait, left)
                except Exception as e:  # noqa: BLE001 — an unawaitable brief reads as in flight
                    logger.debug(f"follow_up_pass: the brief was not awaited — {e!r}")
            self.routed = _route.sure_escalate(self.brief)
        if self.routed:
            words, self.route_pending = "".join(self.route_pending), []
            if words.strip():
                emit("brain", "🤐 routed to its task — the inline words are not said", role="system", text=words[:160],
                     extra={"cat": "flash", "routed": True})
            return True
        pend, self.route_pending = self.route_pending, []
        for p in pend:
            self._say(p)
        return False

    async def _answered(self, ran_ops, op_tasks, timeout: float = 6.0) -> bool:
        """An answer op ran on the held card and its dispatch RETURNED data (waited for as the op's answer pass would)."""
        from nucleo.flash import data_ops
        from widgets import effects
        if not any(_card(w) == self.card and effects.carries(self.card, a, effects.OUTPUT_ANSWER) for w, a in ran_ops or ()):
            return False
        mine = [t for w, t in op_tasks or () if _card(w) == self.card]
        if (pend := [t for t in mine if not t.done()]):
            await asyncio.wait(pend, timeout=timeout)
        return any(t.done() and not t.cancelled() and not t.exception() and data_ops.answer_of(t.result()) for t in mine)


def flush(hold: "Hold | None", spoken, emit, spoken_text: str = "") -> str:
    """The turn's chain has run: deferred words are said only if nothing else was — the card's answer, said later, is
    the turn's ONE answer (never a guess, a correction and a third line). The turn's words after it."""
    text = getattr(hold, "deferred", "")
    if not text:
        return spoken_text
    hold.deferred = ""
    if "".join(spoken or ()).strip():
        emit("brain", "🤐 the words were written before the data (or narrated another call) — not said",
             role="system", text=text[:160], extra={"cat": "flash", "card": hold.card, "deferred": True})
        return spoken_text
    hold.send(text)
    return text


def _ready(brief) -> bool:
    from nucleo import jev
    return jev._is_ready(brief)


def _unclear_at_first_word(brief, t0: float, wait_s: float):
    """The `readable` verdict at the first word: `garbled`/`noise`, "" (read, or nothing to wait for), or None while the
    brief is in flight and the channel's deadline (`wait_s`, the lead-in filler's) has not passed."""
    from nucleo.flash import unclear_turn
    if brief and not _ready(brief) and time.monotonic() - t0 < wait_s:
        return None
    return unclear_turn.verdict(brief)


def _card(wid) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def holds(brief) -> str:
    """The card a sure ANSWER verdict names, or "" (nothing held: today's path)."""
    try:
        from nucleo.acts import card
        from nucleo.turn import brief as tb
        from widgets import effects
        target, info = tb.read(brief, tb.TARGET_KEY, "", min_confidence=card.VETO_SURE)
        wid, _, act = str(target or "").partition(":")
        return wid if (info or {}).get("used") and effects.carries(wid, act, effects.OUTPUT_ANSWER) else ""
    except Exception as e:  # noqa: BLE001 — an unreadable verdict holds nothing
        logger.debug(f"follow_up_pass: hold unreadable: {e!r}")
        return ""
