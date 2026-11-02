"""Which act outcomes are NOT news after the turn's words — the mouth's three silences (V2-834 T08/T12/T24).

`reply.owed` decides which verdict lines a turn still owes after the model's words. It always said `unmet`, `cannot`
and `asked`, and said `met` when the words had not named its object. Three measured cases showed a line that was true
and still wrong to say, each because the line repeated something already said — never because of a word table:

  · a card's OWN sentence (a message, a notice read back) already spoke for its object, and a second act on the same
    object would add «Hecho: «Dune…»» beside it — pause said it twice next to «He pausado…»
    (`watch-a-video-not-listen-to-it`, T08);
  · OUR PREVIOUS reply named the object and the model has words this turn: after every volume or pause turn
    «Hecho: «Dune…»» was glued on again (T08). The previous reply is read from the conversation window, never from a
    module global — a global let one conversation (or a test) silence a receipt in another (T12);
  · a refusal with only an internal `error` and no speakable reason is the mouth's to say (`told=False`, T24) — but not
    when another op on the SAME card landed this turn: «ponla a las cinco» refused `set_reminder` while
    `update_meeting` moved it, and «not done» there would contradict the move that happened.
"""
from __future__ import annotations

from nucleo.circuit import verdict as V


def _value(verdict) -> str:
    v = V.of(getattr(verdict, "name", verdict))
    return v.name if v else ""


def named_in(obj: str, said: str) -> bool:
    """The words named the object: every title the object quotes is in what was said."""
    names = [t.split("»")[0].strip().lower() for t in str(obj or "").split("«")[1:]]
    low = (said or "").lower()
    return bool(names) and all(n in low for n in names)


def silent(o, outcomes, said: str, prior: str = "") -> bool:
    """Is this outcome's line not news? `o.told` (its door said it) or one of the three silences above."""
    if o.told:
        return True
    value = _value(o.verdict)
    if value == V.UNMET.name and not o.reason:
        return any(x.card == o.card and _value(x.verdict) == V.MET.name for x in outcomes)
    if value == V.MET.name and not o.said:
        voiced = any(x.said and x.object and (x.card, x.object) == (o.card, o.object) for x in outcomes)
        return voiced or bool(said.strip() and named_in(o.object, prior))
    return False
