"""nucleo/memory_agent/rename_decision.py — does this turn actually RENAME the assistant?

THE INCIDENT (live session fce3eff3, 2026-09-22, at +154.9 s). The operator was correcting a video
search. He said:

    «He dicho, Apollo once.»

The memory processor distilled that into an atom with `slot: assistant.name`, `value: "Apollo 11"`,
`state_patch: {"assistant_name": "Apollo 11"}` — and it was written. Row 16 of his real `memories`
table. From that turn on the prompt told the model «Tú te llamas Apollo 11», and `voice.attention`
answered to «Apollo 11» as a wake word.

Nothing stopped it, and the reason is ours: V2-747 gave this slot `garble_guard=False` and
`about_operator=False` — both correct in isolation, for reasons written in `memory/slots.py` — and
between them they left `assistant.name` as **an identity slot writable on the small model's own
signature alone**. That is what [[feedback_un_slot_de_identidad_que_no_habla_del_operador]] warned
about from the other side: a guard applied to the set that merely *looks* like the class. V2-747 was
that mistake in the refusing direction; this was the same mistake in the granting one.

## WHY NOT A REGEX

`_talks_about_the_operator` — the guard this slot was excused from — is a regex over first-person
marks. Writing `_talks_about_the_assistant` beside it would be a verb table deciding a route, which
CLAUDE.md forbids on three measured incidents, and it would be Latin-script only, so a Japanese or
Hindi rename would be silently unwritable (the exact shape V2-750 measured on
`looks_like_create_widget`: 6/9 in zh, ja and hi).

So the declared options are enumerated and the decision model chooses, like every other route in this
engine since V2-750. It costs nothing in latency: the memory processor runs OFF the turn, after the
reply has already been spoken.

## THE DIRECTION OF FAILURE, AND WHY IT IS THIS ONE

Absent, disabled, unsure → REFUSE the write. That is the opposite of this module's neighbours, and it
is deliberate:

  · refusing wrongly costs a rename that needs saying once more, and the EXPLICIT path is untouched —
    `nucleo/flash/identity_actions` persists a rename the moment the model calls the tool, which is what
    worked correctly in this very session (`🏷️ zaelar se renombra Johnny`, +76.1 s).
  · granting wrongly costs what it cost here: his assistant renamed to a search term, the prompt
    telling the model an identity he never gave it, and the wake word moved out from under him — in
    silence, and persisted across sessions.

The two are not close, so the gate closes rather than opens.
"""
from __future__ import annotations

RENAME_KEY = "renames_the_assistant"

RENAME_INSTRUCTIONS = (
    "The operator is talking to a voice assistant. Does this utterance GIVE THE ASSISTANT A NEW NAME — "
    "is he telling it what he wants to call it from now on? Answer 'renames' only when the utterance is "
    "about what the assistant should be called. Answer 'no' for anything else, including when it merely "
    "contains a name or a proper noun for some other reason — a search, a person, a place, a title.")

RENAME_CHOICE = {
    "renames": "he is telling the assistant what he wants it to be called",
    "no": "the utterance is not about the assistant's name",
}


def renames_the_assistant(text: str) -> bool:
    """True only on a confident verdict that this utterance names the assistant. Never raises."""
    text = (text or "").strip()
    if not text:
        return False
    try:
        from nucleo import jev
        if not jev.enabled():
            return False
        out = jev.choose_many_sync(
            text, {RENAME_KEY: {"instructions": RENAME_INSTRUCTIONS, "criteria": dict(RENAME_CHOICE)}},
            question_id="rename")
        if not out:
            return False
        v = out.get(RENAME_KEY) or {}
        return (str(v.get("choice") or "") == "renames"
                and float(v.get("confidence") or 0.0) >= jev.MIN_CONFIDENCE)
    except Exception:  # noqa: BLE001
        return False
