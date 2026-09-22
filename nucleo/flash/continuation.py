"""nucleo/flash/continuation.py — does this fragment CONTINUE the one being held, or start something else?

THE DEFECT THIS EXISTS FOR (live session fce3eff3, 2026-09-22, at +241.4 s). The operator said:

    «quita este vídeo y vamos otra vez al [inicio]»

Deepgram never delivered «inicio». The fragment dangles on «al», so the accumulator held it — correctly.
Then, a beat later, he said something that was NOT the rest of it:

    «No me estás oyendo.»

The accumulator glued them by TIME ADJACENCY ALONE and handed the turn this sentence:

    «quita este vídeo y vamos otra vez al No me estás oyendo.»

Jev read that and answered `canvas=close`, `screen_action=youtube:close` at **0.93**. The video card was
closed. He had never asked for it to be closed, and spent the next ninety seconds saying so — «Yo no te he
dicho en ningún momento que cerraras el widget de vídeo» — while a verb table closed it twice more.

## WHY THE EXISTING LAYERS COULD NOT CATCH IT

`Accumulator.offer` asks two questions about the MERGED text and neither of them is this one:

  · layer 1 (`segmenter.looks_incomplete`) — does the sentence DANGLE? The merged text ends in a full
    stop, so it answered «complete» and delivered. It was right about what it was asked.
  · layer 2 (`segmenter.judge`) — the same question, to a model, and it never even ran: layer 1 is
    consulted first and only an «incomplete» verdict reaches the judge.

Both judge the merge AFTER it has happened, so by the time anything looks at the text, the damage is in
it. Nothing in the chain ever asked whether these two fragments belong to one sentence. «No» cannot
continue «…vamos otra vez al»: the article demands a noun. That is not a rule about Spanish worth
writing down — it is the shape of the question, and the answer belongs to a model that can read any
script (CLAUDE.md, «UNA TABLA DE VERBOS NO ES UN ENRUTADOR»).

## THE PRICE, SAID OUT LOUD

This is a PRE-MODEL classifier and it costs what one costs. The operator authorised that on 2026-09-22
(«Jev es un modelo que tiene una latencia mínima… allí donde consideres que eso puede aportarnos claridad
y eficiencia, puedes considerar ponerlo»), and the standing criterion is to pay it only where the decision
cannot be read afterwards. It cannot be read afterwards here: the merge is what the whole turn is built
from — prompt, brief, memory, the chat wall — so by the time any post-model reader exists it is reading
the glued sentence.

What contains the price is that it is asked **only at a seam**: there is a fragment on hold AND a new one
has arrived. Measured over that session, 10 turns of 28 (36 %) reached that state; the other 18 pay
nothing at all. One round trip, p50 ~760 ms on the five-language corpus of node 2.68.

## FAIL-OPEN, AND WHICH DIRECTION IS CHEAP

Disabled, unreachable, timed out, or unsure → `True` (it continues), which is today's behaviour bit for
bit. Splitting wrongly costs a held fragment answered as its own turn; gluing wrongly costs what it cost
above. But an ABSENT verdict must never silently change behaviour, so absence keeps the old path and the
separation only ever happens on a confident NO.
"""
from __future__ import annotations

CONTINUES_KEY = "continues_previous"

CONTINUES_INSTRUCTIONS = (
    "A person was interrupted mid-sentence. The first line below is what they had said so far — it is "
    "unfinished. The second line is what they said next, after a pause. Do these two lines form ONE "
    "sentence, with the second finishing the first? Answer 'continues' when the second line is the rest "
    "of the same thought and reading them joined makes sense. Answer 'separate' when the second line "
    "starts something else — a new order, a complaint, an aside, an answer to something else — so that "
    "joining them would produce nonsense. Judge the words themselves, in whatever language they are in.")

CONTINUES_CHOICE = {
    "continues": "the second line finishes the first: together they are one sentence",
    "separate": "the second line begins something else; joining them would produce nonsense",
}

#: Below this the verdict is a shrug and the caller keeps today's behaviour (glue). Deliberately the same
#: gate every other reader of a verdict uses — a separate number here would be a second policy for one
#: question, which is the shape this repo keeps paying for.
MIN_CONFIDENCE = 0.5


def question() -> dict:
    """The question, in the shape `jev.choose_many_sync` takes."""
    return {"instructions": CONTINUES_INSTRUCTIONS, "criteria": dict(CONTINUES_CHOICE)}


def _state(held: str, incoming: str) -> str:
    return f"UNFINISHED: {held}\nWHAT CAME NEXT: {incoming}"


def continues(held: str, incoming: str) -> tuple[bool, str]:
    """`(glue them, why)`. True — the caller's existing behaviour — unless a confident verdict says no.

    `why` is for the timeline: it carries the verdict and its confidence when there was one, and "" when
    nothing was asked or nothing came back. Never raises: a classifier may not break a turn.
    """
    held, incoming = (held or "").strip(), (incoming or "").strip()
    if not held or not incoming:
        return True, ""
    try:
        from nucleo import jev
        if not jev.enabled():
            return True, ""
        out = jev.choose_many_sync(_state(held, incoming), {CONTINUES_KEY: question()},
                                   question_id="continuation")
        if not out:
            return True, ""
        v = out.get(CONTINUES_KEY) or {}
        choice, conf = str(v.get("choice") or ""), float(v.get("confidence") or 0.0)
        if choice == "separate" and conf >= MIN_CONFIDENCE:
            return False, f"{CONTINUES_KEY}=separate ({conf:.2f})"
        return True, (f"{CONTINUES_KEY}={choice} ({conf:.2f})" if choice else "")
    except Exception:  # noqa: BLE001 — no caller may ever break on a classifier
        return True, ""
