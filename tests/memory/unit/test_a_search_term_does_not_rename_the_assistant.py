"""V2-752 — the assistant's name is not written on the small model's signature alone.

THE INCIDENT (live session fce3eff3, 2026-09-22, +154.9 s). The operator was correcting a video search
that the STT had mangled. He said:

    «He dicho, Apollo once.»

The memory processor distilled that into an atom with `slot: assistant.name`, `value: "Apollo 11"`,
`state_patch: {"assistant_name": "Apollo 11"}`, and it was WRITTEN — row 16 of his real `memories`
table, found while auditing this repair. From that turn on the prompt told the model «Tú te llamas
Apollo 11» and `voice.attention` answered to «Apollo 11» as a wake word. Across sessions.

The hole is ours and it is one day old. V2-747 excused this slot from two guards:

  · `about_operator=False` — right: a sentence renaming the assistant never talks about the operator,
    so the guard that asks that question sealed the slot instead of protecting it.
  · `garble_guard=False` — right: a rename contradicts the established value by design, which is
    exactly what the anti-garble gate quarantines.

Both correct in isolation, and between them `assistant.name` became an identity slot writable on the
distiller's own `change` signature with nothing checking the premise. V2-747 was a guard applied to a
set that merely looked like the class, in the REFUSING direction; this is the same mistake in the
GRANTING one.

The question nobody asked is «does this utterance give the assistant a name?», and it is asked by the
decision model rather than by a regex — a sibling of `_talks_about_the_operator` would be a verb table
deciding a route (forbidden on three measured incidents) and would be Latin-script only.

Run: .venv/bin/pytest tests/memory/unit/test_a_search_term_does_not_rename_the_assistant.py
"""
from __future__ import annotations

import pytest

from memory import slots
from nucleo.memory_agent import rename_decision


class _Asked:
    def __init__(self):
        self.asked: list[str] = []


@pytest.fixture
def jev(monkeypatch):
    """Answers for the decision model, patched ON the real module rather than swapped INTO `sys.modules`.

    The first version of this fixture did the swap, and it leaked: a module that resolves `nucleo.jev`
    lazily inside a function picked up the double for the rest of the folder run, and a neighbouring
    recall test that has its own jev double went red only when run together. A test that changes the
    module table is [[feedback_el_aislamiento_vive_en_la_suite]] with the blast radius pointed inward.
    """
    import nucleo.jev as real
    spy = _Asked()

    def _install(answer, confidence=0.93, on=True):
        monkeypatch.setattr(real, "enabled", lambda: on)

        def _choose(state, questions, **kw):
            spy.asked.append(state)
            if answer is None:
                return None
            return {rename_decision.RENAME_KEY:
                    {"choice": answer, "confidence": confidence, "probs": {}}}

        monkeypatch.setattr(real, "choose_many_sync", _choose)
        return spy
    return _install


# ── 1 · THE INCIDENT ──────────────────────────────────────────────────────────────────────────────────
def test_a_corrected_search_term_is_not_a_new_name(jev):
    """«He dicho, Apollo once.» renamed his assistant to «Apollo 11» and moved the wake word with it."""
    jev("no", 0.97)
    assert not rename_decision.renames_the_assistant("He dicho, Apollo once.")


def test_a_real_rename_still_lands(jev):
    """The half that must not move. His own words from the same session, +73.4 s."""
    jev("renames", 0.95)
    assert rename_decision.renames_the_assistant("Y ahora tú te vas a llamar Johnny.")


# ── 2 · THE DIRECTION OF FAILURE IS THE CLOSED ONE ────────────────────────────────────────────────────
# Opposite to every other verdict reader in this engine, and deliberately: refusing wrongly costs a
# rename said once more (and the EXPLICIT tool path is untouched — it worked correctly in that very
# session); granting wrongly costs an identity he never gave, silently, across sessions.
@pytest.mark.parametrize("answer,conf,on,why", [
    (None, 0.0, True, "the model was unreachable"),
    ("renames", 0.2, True, "the verdict was a shrug"),
    ("renames", 0.95, False, "the model is disabled on this build"),
])
def test_without_a_confident_yes_nothing_is_renamed(jev, answer, conf, on, why):
    jev(answer, conf, on)
    assert not rename_decision.renames_the_assistant("He dicho, Apollo once."), why


def test_the_utterance_itself_is_what_is_judged(jev):
    """No surrounding context, no previous reply: the question is about these words. Anything else would
    make a rename depend on what we happened to have said before it."""
    fake = jev("no")
    rename_decision.renames_the_assistant("He dicho, Apollo once.")
    assert fake.asked == ["He dicho, Apollo once."]


# ── 3 · THE SLOT IS STILL THE ONE V2-747 UNSEALED ─────────────────────────────────────────────────────
def test_the_slot_keeps_both_V2_747_exemptions():
    """This repair must not be «put the old guards back». Those two exemptions are correct and they are
    why a rename can be written at all; what was missing was a question of this slot's own.

    Re-arming `about_operator` here would seal the slot again (V2-747's measured failure: the write was
    refused 100 % of the times the function was used), and re-arming the anti-garble gate would
    quarantine every legitimate rename, since a rename contradicts the established value by design.
    """
    spec = slots.SLOTS["assistant.name"]
    assert spec.about_operator is False, "a rename never talks about the operator — V2-747"
    assert spec.garble_guard is False, "a rename contradicts the old value on purpose — V2-747"
    assert spec.state_field == "assistant_name"


def test_the_write_path_asks_before_it_persists():
    """The seam. The verdict is useless in a module the write never calls, which is how `catalog_widget`
    spent a week being paid for and read by nobody (V2-750)."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[3] / "nucleo/memory_agent/ingest.py"
    body = src.read_text(encoding="utf-8")
    i = body.index('if a.get("slot") == "assistant.name"')
    guard = body[i:i + 300]
    assert "renames_the_assistant" in guard, "the atom path must consult the verdict"
    assert "continue" in guard, "…and a «no» must DROP the atom, not merely soften its change signal"
