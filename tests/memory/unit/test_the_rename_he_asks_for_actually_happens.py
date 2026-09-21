"""V2-747 — «cámbiate el nombre a Johnny» is a thing the agent can do, and it does it.

## The session

`981dd54c` (2026-09-21). Four turns, one rename, nothing changed:

    +55.7 s   «Además quiero que te cambies el nombre a Johnny, ahora mismo.»
    +61.6 s   🧠 `slot assistant.name: self-declared change IGNORED — the turn is not about the operator`
    +64.8 s   «No puedo cambiarme el nombre a Johnny, mi palabra de activación es y seguirá siendo "Zaelar".»
    +76.2 s   «Entendido, te cambio el nombre a Johnny ahora mismo.» · ⚠️ promesa sin acción (no tool fired)
    +85.2 s   «Me equivoqué: el nombre sí se puede cambiar y no debí negarme.»
    +105 s    …and a background worker was spawned to «averiguar cómo se cambia el nombre del asistente».

He then asked, reasonably: *«¿Por qué te has negado en primera?»*

## Three separate things were broken, and each one alone was enough

1. **The memory gate sealed the slot.** `ingest` only honours a self-declared `change` on an IDENTITY slot
   when the turn TALKS ABOUT THE OPERATOR — a guard written for `operator.location`, where a third party's
   city must never overwrite where HE lives. `assistant.name` is the one identity slot that is NOT about
   him, so that test could never pass and the write was refused every single time.
2. **The catalog never said the capability existed.** `identity_actions` has carried the rename since
   V2-716, riding `set_style_directive`, and that tool's description covered it only «in spirit». A
   capability nobody declares is not routable — so the model answered from its own idea of itself.
3. **The pattern did not match how he says it.** `c[aá]mbia(?:te)?` is the imperative; he said «quiero que
   TE CAMBIES el nombre a Johnny», clitic first, subjunctive.

The wake-word complaint of the same session rides on this: he spent the whole session calling it «Johnny»,
and the attention gate correctly refused a name that had never been registered. There is nothing to fix in
the gate — `attention.wakewords()` extends itself the moment the rename lands.
"""
from __future__ import annotations

import json

import pytest

from memory import slots
from nucleo.flash import identity_actions as ia


# ── 1 · the slot the guard could never let through ────────────────────────────────────────────────────

def test_the_assistants_name_is_an_identity_fact_that_is_not_about_the_operator():
    spec = slots.SLOTS["assistant.name"]
    assert spec.identity is True, "it is a singular identity fact and the rest of the registry treats it so"
    assert spec.about_operator is False, (
        "a sentence renaming the assistant never talks about the operator — declaring otherwise is what "
        "made the self-declaration guard refuse every rename")


def test_the_self_declaration_guard_only_covers_the_slots_it_can_judge():
    judged = slots.slots_about_the_operator()
    assert "assistant.name" not in judged
    assert judged < slots.identity_slots(), "it must be a strict subset, or nothing changed"
    for k in ("operator.name", "operator.location", "operator.job", "goal.current"):
        assert k in judged, f"{k} is about him and MUST keep its guard — that is the incident it came from"


def test_the_guard_reads_that_set_and_not_the_wider_one():
    """Where the two sets get confused again. The wider one is still right for the INJECTION guard three
    lines above it — an injection preamble may not overwrite any identity fact, the assistant's included."""
    import inspect

    from nucleo.memory_agent import ingest
    src = inspect.getsource(ingest)
    assert "_OPERATOR_IDENTITY_SLOTS and not _talks_about_the_operator" in src
    assert "_IDENTITY_SLOTS and _looks_like_injection" in src, (
        "the injection guard covers EVERY identity slot and must not have been narrowed with it")


# ── 2 · the capability is declared where the model reads ──────────────────────────────────────────────

def test_the_tool_that_carries_the_rename_says_so():
    from nucleo.flash import router_catalog as rc
    spec = next(t["function"] for t in rc.TOOLS if t["function"]["name"] == "set_style_directive")
    desc = spec["description"].lower()
    assert "nombre" in desc, (
        "«no puedo cambiarme el nombre» over a capability it has had since V2-716: the tool that carries "
        "the rename never mentioned it")
    assert "puedes" in desc, "…and it has to say it CAN, because what it did was refuse"


def test_declaring_it_did_not_cost_the_turn_anything():
    """The catalog travels in EVERY voice turn, so a new sentence is paid for by a shorter one elsewhere —
    the ceiling is not raised to fit a fix."""
    from nucleo.flash import router_catalog as rc
    size = sum(len(json.dumps(t, ensure_ascii=False)) for t in rc.TOOLS)
    assert size <= 23_600, f"the catalog grew to {size}: compact a description instead of raising the ceiling"


# ── 3 · the words he actually used ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said", [
    "quiero que te cambies el nombre a Johnny",          # ← verbatim, session 981dd54c
    "cámbiate el nombre a Johnny",
    "cambia tu nombre a Johnny",
    "El asistente debe llamarse Johnny",
    "llámate Johnny",
    "your name is Johnny",
    "call yourself Johnny",
])
def test_every_way_he_has_asked_for_it_resolves_to_a_rename(said):
    assert ia.resolve(said) == ("rename", "Johnny"), said


@pytest.mark.parametrize("said", [
    "no me cambies el tono",
    "cambia el nombre de la lista a la compra",           # a LIST, not the assistant
    "ponme música",
])
def test_and_nothing_else_does(said):
    got = ia.resolve(said)
    assert got is None or got[0] != "rename", (said, got)


# ── the end of the chain: the name it answers to ──────────────────────────────────────────────────────

def test_the_new_name_becomes_a_wake_word():
    """Why the rename is not cosmetic, and why the gate needed no change: `attention` extends its own wake
    words from the name, additively — «zaelar» keeps working, which is what makes a rename safe."""
    from voice import attention
    prev = attention.assistant_name()
    try:
        attention.set_assistant_name("Johnny")
        assert attention.has_wakeword("Hola, Johnny, ¿estás ahí?"), (
            "he said exactly this, three times, to a gate that ruled it ambient")
        assert attention.has_wakeword("oye zaelar"), "the original name is never dropped"
    finally:
        attention.set_assistant_name(prev)
