"""The second trip's reply goes through the tag seam — never `send()` raw model text (2026-08-31).

Measured live in the operator's own session (`acc5e85e`, master link he pasted): «Vale, quiero saber si
tengo mensajes de WhatsApp» → the messaging family had been trimmed (V2-096 F2), the model asked for it
with `need_capability`, and the SECOND TRIP's reply — which contained `[[show:mensajeria]]` — was sent
verbatim: the TTS *spoke the tag out loud* and no widget opened. The action reached the operator's ears
instead of the dispatcher. The primary stream never had this bug because every chunk flows through
`buf`/`take()` → `strip_tags(_tag_emit)`; the retry path collected raw pieces and bypassed all of it.

Why these are SOURCE guards and not a behavioral test: the retry block lives inside `_run_inner`'s
closure and mounting it for real requires half the LiveKit stack (same verdict as
`test_agent_trace_source_guards.py` and `test_lead_in.py`'s neighbours). The guards are written in both
directions and were verified RED against the shipped bug (the exact pre-fix code makes all three fail).
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[4] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"


def _second_trip_block() -> str:
    """The retry block, from its `_need_family` read to its except handler — anchored on markers that a
    refactor cannot silently drop: if the anchors go, this raises and the guard gets repointed, never
    left watching nothing (the V2-201 lesson: a guard aimed at the void stays green)."""
    text = SRC.read_text(encoding="utf-8")
    m = re.search(r"_need = getattr\(self, \"_need_family\".*?except Exception as e:", text, re.S)
    assert m, "the second-trip block moved — repoint this guard at wherever V2-096 F2's retry lives now"
    return m.group(0)


def test_the_second_trip_reply_goes_through_take():
    """`take(True)` is what runs strip_tags with `_tag_emit`: it executes `[[show:…]]` and removes it
    from speech. The shipped bug was exactly its absence here."""
    block = _second_trip_block()
    assert "take(True)" in block, (
        "the second trip no longer routes its reply through take() — inline tags will be SPOKEN "
        "instead of executed (the acc5e85e incident)")


def test_the_second_trip_never_sends_raw_text():
    """The other half: even with take() present somewhere, a raw `send(_txt2)` without sanitize would
    still leak whatever take didn't consume. The final send must be the same shape as the primary
    stream's: `send(speech.sanitize(...))`."""
    block = _second_trip_block()
    assert "send(speech.sanitize(_txt2" in block
    assert re.search(r"send\(_txt2\)", block) is None, (
        "a bare send(_txt2) is back in the second trip — that is the exact line that spoke "
        "[[show:mensajeria]] out loud")


def test_the_second_trip_discards_first_pass_tag_leftovers():
    """`buf` may hold a half-open tag from the first pass; reusing it would splice the retry's text into
    it. The other second-pass sites in this file all reset it first — this one must too."""
    block = _second_trip_block()
    assert re.search(r"buf = \"\"", block), "the second trip must reset buf before feeding take()"
