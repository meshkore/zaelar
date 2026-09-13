"""The assistant answers to the name it calls itself (V2-682 T-1).

Measured on the operator's engine, 2026-09-12. Every kickoff of that day introduced the agent as «Johnny» —
the name lived in a MEMORY PILL («desea que su asistente se llame Johnny»), which recall feeds to the model
and the model obeys — while `state.assistant_name` was still «Zaelar», so `attention.wakewords()` answered
only to «zaelar». The result, in his own words to a machine that had just told him what to call it:

    «Hey, Johnny.»                     → 🙉 ambient
    «Hello. Johnny. How are you?»      → 🙉 ambient
    «Hey, Johnny. Show me my agenda.»  → 🙉 ambient

Thirty-five turns of one day. Nothing was broken: the rename had simply never gone through the structured
door, because the model had no reason to call a tool about a name it already believed it had.

The whole mechanism existed — detector, process-level apply, durable write (`identity_actions`, V2-... the
9th) — behind ONE door the model chooses to open. This gives the operator's own sentence a deterministic
lane, the V2-539/V2-674 shape, in both channels. It is language-neutral by construction: the regex was
already bilingual, and a rename's failure mode (a deaf agent) is the same in every language.
"""
import asyncio
from pathlib import Path

import pytest

from nucleo.flash import identity_actions as ident

ROOT = Path(__file__).resolve().parents[4]


# ── 1 · what is a rename order and what is not ───────────────────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("llámate Johnny", "Johnny"),
    ("Llámate Colmena.", "Colmena"),
    ("te llamas Johnny", "Johnny"),
    ("cámbiate el nombre a Colmena", "Colmena"),
    ("cambia tu nombre a Nova", "Nova"),
    ("el asistente debe llamarse Johnny", "Johnny"),
    ("call yourself Johnny", "Johnny"),
    ("your name is Nova", "Nova"),
    ("the assistant should be called Johnny", "Johnny"),
])
def test_his_own_sentence_renames(text, expected):
    assert ident.spoken_identity_order(text) == ("rename", expected)


@pytest.mark.parametrize("text", [
    "¿cómo te llamas?",                  # a QUESTION about the name is not an order to change it
    "¿te llamas Johnny?",                # …and this one WOULD have renamed it: the verb form is identical
    "what's your name?",
    "how do you call yourself",
    "call yourself the best assistant in the world",   # a clause is not a name
    "llámate el asistente más rápido del mundo",
    "llámate como quieras",              # not a name — this would have renamed it «como quieras»
    "call yourself whatever you want",
    "Hey Johnny, how are you?",          # being ADDRESSED by a name is not a rename
    "show me the agenda",
    "",
])
def test_what_never_renames(text):
    assert ident.spoken_identity_order(text) is None


# ── 2 · the property that matters: the gate then answers to it ───────────────────────────────────────
def test_after_a_rename_the_gate_answers_to_the_new_name(monkeypatch):
    """The incident's exact shape, reproduced end to end over the real attention gate."""
    from voice import attention
    monkeypatch.setattr(attention, "_state", dict(attention._state), raising=False)
    assert not attention.has_wakeword("Hey, Johnny.")          # the deaf state of 2026-09-12
    order = ident.spoken_identity_order("call yourself Johnny")
    assert order is not None
    ident.apply_rename_now(order[1])
    try:
        assert attention.has_wakeword("Hey, Johnny.")
        assert attention.has_wakeword("Hey, Johnny. Show me my agenda.")
        assert "johnny" in [w.lower() for w in attention.wakewords()]
        assert "zaelar" in [w.lower() for w in attention.wakewords()], \
            "the shipped name keeps working — a rename adds a name, it does not orphan the default"
    finally:
        attention.set_assistant_name("")


def test_the_rename_is_written_where_the_gate_reads_it(monkeypatch):
    """`state.assistant_name` is the structured fact `memory_cache` pushes into the gate. A pill is not."""
    wrote = {}
    import memory.api as mem
    monkeypatch.setattr(mem, "set_state", lambda fields: wrote.update(fields))
    asyncio.run(ident.persist_rename("Johnny"))
    assert wrote == {"assistant_name": "Johnny"}


# ── 3 · the probe channel does the same thing (V2-252: a lane in one channel only is a lane that rots) ─
class _Sess:
    window: list = []


def test_the_probe_mirror_renames_and_writes(monkeypatch):
    from nucleo.flash import probe_actionmap as pa
    seen = {}
    import memory.api as mem
    monkeypatch.setattr(mem, "set_state", lambda fields: seen.update(fields))
    from voice import attention
    monkeypatch.setattr(attention, "_state", dict(attention._state), raising=False)
    try:
        got = pa.try_rename("llámate Colmena", _Sess(), trace_id="T1", spec=type("S", (), {"data_ack": "Hecho."})(),
                            execute=True)
        assert got and got["action"] == "rename_assistant"
        assert seen == {"assistant_name": "Colmena"}
        assert attention.has_wakeword("Colmena, abre la agenda")
    finally:
        attention.set_assistant_name("")


def test_a_dry_run_changes_nothing(monkeypatch):
    from nucleo.flash import probe_actionmap as pa
    seen = {}
    import memory.api as mem
    monkeypatch.setattr(mem, "set_state", lambda fields: seen.update(fields))
    got = pa.try_rename("llámate Colmena", _Sess(), trace_id="T1",
                        spec=type("S", (), {"data_ack": "Hecho."})(), execute=False)
    assert got and got["action"] == "rename_assistant"
    assert seen == {}, "a dry run reports the decision and writes nothing"


def test_an_ordinary_turn_falls_through_to_the_model():
    from nucleo.flash import probe_actionmap as pa
    assert pa.try_rename("show me the agenda", _Sess(), trace_id="T1",
                         spec=type("S", (), {"data_ack": "Hecho."})(), execute=True) is None


# ── 4 · the wiring, read in BOTH channels (V2-555: a guard on one file goes green when the other rots) ─
def _stripped(p: Path) -> str:
    return "\n".join(line.split("#", 1)[0] for line in p.read_text(encoding="utf-8").splitlines())


def test_the_voice_channel_runs_the_lane():
    src = _stripped(ROOT / "voice" / "engine" / "llm" / "providers" / "nucleo.py")
    assert "_fast_lane.rename(brain, text, emit" in src


def test_the_probe_channel_runs_the_lane():
    src = _stripped(ROOT / "nucleo" / "flash" / "probe_actionmap.py")
    assert "try_rename(text, sess" in src
