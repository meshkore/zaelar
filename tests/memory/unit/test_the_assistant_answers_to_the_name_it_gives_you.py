"""V2-716 — the assistant's own name is a SLOT, so the wake word cannot disagree with the greeting.

Measured in session 928c8761 (2026-09-17). The engine introduced itself as «Johnny» — the name lived as PROSE
in memory («Quiere que el asistente cambie su nombre a Johnny»), which recall feeds the model and the model
obeys — while `state.assistant_name` still said «Zaelar», so `attention.wakewords()` answered only to
«zaelar». For four minutes the operator called «Johnny?», «Zilar?», «Zaylor?» into a live microphone and every
single one was ruled 🙉 AMBIENT (`reason: "ambient"`, `window_open: false`). He ended up typing «hello, arent
you listening ?» into the chat to be heard at all.

One prompt carried two contradictory identities: the model read the pill, the wake word read the state field.
The cause was structural and small — **the assistant's name was the one identity fact with no slot**, so a
rename could only ever be remembered as prose, and prose reaches the model but never `voice.attention`.

These tests hold the chain that now carries it: catalogue → canonical key → state field → wake word.
"""
from __future__ import annotations

import pytest

from memory import slots
from voice import attention


def test_the_assistants_name_is_a_registered_identity_slot():
    assert "assistant.name" in slots.SLOTS
    assert "assistant.name" in slots.identity_slots(), "a rename is a singular fact, not an accumulating one"
    assert slots.state_field("assistant.name") == "assistant_name"
    assert slots.slot_for_state_field("assistant_name") == "assistant.name"


def test_the_processor_is_offered_the_slot_it_has_to_route_a_rename_into():
    """The catalogue the model sees and the one the host validates are the same object by construction — so
    a slot missing from this string is a slot the processor can never emit."""
    assert "assistant.name" in slots.prompt_catalog()


@pytest.mark.parametrize("emitted", [
    "assistant_name", "assistant.name", "agent_name", "agent.name",
    "bot_name", "nombre_asistente", "ASSISTANT_NAME", " assistant.name ",
])
def test_every_spelling_a_model_reaches_for_collapses_to_one_lineage(emitted):
    """Parallel lineages of one fact is the failure this whole registry exists to prevent (audit 2026-07-14:
    four live location pills at once). A rename is the worst case for it — two lineages means the wake word
    and the greeting can pick different ones, which is precisely what was measured."""
    assert slots.canonical(emitted) == "assistant.name"


def test_a_rename_does_not_get_quarantined_as_a_contradiction():
    """`garble_guard=False`, like `operator.treatment`. A rename CONTRADICTS the previous value by design;
    with the P0b anti-garble gate on, every legitimate rename would be held and the old name would survive
    in state — the measured failure of that flag on `operator.treatment` (4 rows / 0 live, audit
    2026-07-19)."""
    assert "assistant.name" not in slots.garble_guard_slots()


def test_the_operators_name_and_the_assistants_are_different_slots():
    """Session 928c8761 also left «The operator's name is Johnny.» in the store — the two identities had
    already bled into each other once. Separate keys, separate state fields, no shared alias."""
    assert slots.canonical("operator.name") != slots.canonical("assistant.name")
    assert slots.state_field("operator.name") == "operator_name"
    shared = set(slots.SLOTS["operator.name"].aliases) & set(slots.SLOTS["assistant.name"].aliases)
    assert not shared, f"an alias resolving to both identities: {shared}"


def test_the_name_in_state_is_what_the_microphone_answers_to():
    """The last link, and the one that was broken in vivo: whatever `state.assistant_name` holds is a wake
    word. `memory_cache` pushes it here on every refresh; this test holds the contract that push relies on."""
    try:
        attention.set_assistant_name("Johnny")
        assert attention.has_wakeword("Johnny?"), "the name it gave the operator must wake it"
        assert attention.has_wakeword("Tony? Johnny?"), "the real accumulated utterance, at 694.4 s"
        assert attention.has_wakeword("zaelar, ¿sigues ahí?"), "the default never stops working (habit)"
    finally:
        attention.set_assistant_name("")
