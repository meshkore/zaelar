"""nucleo/turn/acts_asked.py — two acts asked, one done: the mouth says the rest is not done (V2-854 F4, I4).

Measured on his engine (2026-11-05, «Marca a Rakel Karó como contacto favorito y añádele los alias «Raquel» y «Raquel
Salvador».»): the model made ONE call (`contactos:set_favorite`), the act landed, and the reply was «Done.» — the
aliases were never added and nothing said so. A turn's acts are counted from what its doors ran; how many acts his
words ASKED for is one question of the turn's brief (`acts_asked`, any language, never a word list). When the brief is
sure he asked for several and the turn's doors ran exactly one, the mouth says, after whatever the model said, that
only part was done and where — the verdict is `unmet`, always said. A turn that handed the rest to an errand never
reaches here (the reply's verdicts are read only on a turn that did not escalate); a turn whose doors ran nothing is
the «claimed» / «nothing served» doors' (`nucleo/request/ask_outside_door`).

A close ENDS what it closes (demo V7 in a sandbox, 2026-11-05: «ok stop the video and close youtube» → the model's one
call closed the player, which is both things, and the mouth said «I've only done part of it, on YouTube»). The verdict
counts verbs, so the question says it: a stop or pause followed by a close of the same thing is one act. Measured on the
real decision model (3 of 3 each): «stop the video and close youtube» several 1.00 → one; «pause it and close the player»
→ one 0.94; the operator's own «mark her as favourite and add the aliases» stays several 0.96 — the bench
`tests/voice/bench/test_the_acts_asked_question_against_the_real_api.py` holds those numbers.
"""
from __future__ import annotations

from loguru import logger

KEY = "acts_asked"
ONE, SEVERAL = "one", "several"

INSTRUCTIONS = ("How many DIFFERENT things does the operator ask to be done in this message, in any wording or "
                "language? Each change, send, open, close or play of something is one act; doing the same thing to "
                "several items at once is still one act. Stopping, pausing or leaving full screen something and then "
                "closing it is ONE act: the close already ends it.")
CRITERIA = {
    ONE: "one act, or nothing to do at all (a question, a chat, an answer); also a stop or pause followed by a close "
         "of the same thing",
    SEVERAL: "two or more different acts in the same message",
}


def question(_ctx=None) -> dict:
    return {"instructions": INSTRUCTIONS, "criteria": dict(CRITERIA)}


def several(brief) -> bool:
    """The brief is SURE (veto confidence: this reading makes the mouth say something was not done) he asked for more
    than one act."""
    try:
        from nucleo.turn import verdicts
        choice, info = verdicts.read(brief, KEY, None, min_confidence=verdicts.VETO)
        return bool(info) and choice == SEVERAL
    except Exception as e:  # noqa: BLE001 — unread is «not sure»: nothing is said
        logger.debug(f"acts_asked: verdict unread — {e!r}")
        return False


def ran(tasks=()) -> list[tuple[str, str]]:
    """The distinct `(card, action)` the turn's doors ran: its data-ops (`(card::action, task)`) and its card acts
    (`canvas_focus.this_turn_acts`: shows, closes, controls)."""
    out: list[tuple[str, str]] = []
    for w, _t in tasks or ():
        card, _sep, action = str(w).partition("::")
        out.append((card.split("::", 1)[0], action))
    try:
        from nucleo import canvas_focus
        out += [(str(c), str(a)) for c, _k, a in canvas_focus.this_turn_acts()]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"acts_asked: card acts unread — {e!r}")
    seen: list[tuple[str, str]] = []
    for pair in out:
        if pair[0] and pair not in seen:
            seen.append(pair)
    return seen


def left_undone(tasks=(), *, brief=None) -> list:
    """The `unmet` outcome owed when he asked for several acts and the turn's doors ran exactly one; [] otherwise."""
    try:
        if brief is None:
            from nucleo.turn import brief_turn
            brief = brief_turn.of_this_turn()
        done = ran(tasks)
        if len(done) != 1 or not several(brief):
            return []
        from i18n import langs
        from nucleo.circuit import verdict as V
        from nucleo.flash import card_receipt
        from nucleo.turn.reply import Outcome
        card, action = done[0]
        tpl = str(getattr(langs.current_language(), "reply_part_only", "") or "")
        if not tpl:
            return []
        line = tpl.format(cards=card_receipt.card_name(card))
        # `reason` carries it too: an unmet line with no reason beside a landed op of its card reads as a card's own
        # unspoken refusal (`reply_news.silent`) — this one is the turn's, never silent.
        return [Outcome(V.UNMET.name, card, action, reason=line, said=line)]
    except Exception as e:  # noqa: BLE001 — never takes the reply down
        logger.debug(f"acts_asked: not read — {e!r}")
        return []
