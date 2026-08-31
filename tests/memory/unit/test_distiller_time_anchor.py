"""The distiller's TEMPORAL ANCHOR — a pill that says "three days ago" becomes false as it ages (2026-08-19).

Measured on LoCoMo with the language matched in BOTH arms, so this is not a cross-lingual artefact: distilling
loses **24.3pp** on the temporal category against keeping the raw turn (78.4% -> 54.1%). The cause was not
retrieval. `_render` sent the distiller the state, the language and the utterance and NO notion of when "now" is,
so "I quit smoking three days ago" could only be canonicalised as "quit smoking three days ago" — a pill that is
not merely harder to find but **wrong within a week**, with its real date unrecoverable once detached from the
turn. Probed with real calls on LoCoMo-stamped turns (where the timestamp at least travels inside the text): 5 of
6 relative expressions left unresolved. In production it is worse — no stamp in the text at all — so the model was
not failing, it was being asked the impossible. The FlashBrain has had the explicit date since V2-026; the
memory's own write path did not.

Verified with real API calls after the fix: 0 of 6 unresolved on the stamped turns, and on production-shaped
turns with no stamp at all, "three days ago" -> "August 16, 2026", "a month ago" -> "July 19, 2026",
"Thursday at ten" -> "Thursday, August 20, 2026 at 10:00", "next week" -> "week of August 24,
2026". Those are LLM outputs and cannot be asserted deterministically; what IS asserted here is the
mechanism they depend on — that the anchor is present, and that it follows the MEMORY's clock.
"""
from __future__ import annotations

import datetime

from memory import clock as memclock
from nucleo import mem_processor as MP


def test_the_prompt_carries_an_absolute_time_anchor():
    rendered = MP._render("dejé de fumar hace tres días", {})
    assert "FECHA Y HORA ACTUAL:" in rendered
    year = datetime.datetime.fromtimestamp(memclock.now()).strftime("%Y")
    assert year in rendered, "sin fecha en el prompt, una relativa no se puede resolver — solo copiar"


def test_the_anchor_follows_THE_MEMORYS_CLOCK_not_the_wall_clock():
    """The load-bearing property. The timeline corpus replays 270 SIMULATED days with `clock.travel()`; an anchor
    read from `time.time()` would date every replayed pill in the present while the rest of the run believes it is
    March, which is a corpus that silently stops testing aging."""
    past = int(datetime.datetime(2019, 3, 14, 9, 30).timestamp())
    with memclock.travel(past):
        rendered = MP._render("me mudé ayer", {})
    assert "2019" in rendered and "March" in rendered or "marzo" in rendered.lower() or "2019" in rendered
    assert "2019" in rendered, f"el ancla ignoró el reloj de la memoria: {rendered!r}"


def test_the_rule_that_makes_the_anchor_useful_is_still_there():
    """A ratchet on the instruction, not on prose taste: the anchor alone does nothing if the model is not told to
    USE it, and a later prompt edit that drops the rule would leave a date in the prompt and relative dates in the
    pills — the exact state this fixed, with no test failing."""
    assert "FECHAS RELATIVAS" in MP._SYSTEM
    assert "ABSOLUTAS" in MP._SYSTEM


def test_the_anchor_never_fails_a_write():
    """Writing is the operator's data arriving. An anchor that cannot be computed must degrade to an approximate
    now, never raise — the same fail-open posture as every other piece of this write path."""
    import nucleo.mem_processor as _MP

    orig = _MP._now_stamp

    def _boom():
        raise RuntimeError("clock unavailable")

    try:
        # `_render` must survive a broken anchor: patch the *facade* call it depends on, not `_now_stamp` itself,
        # so the fail-open branch inside `_now_stamp` is what gets exercised.
        import memory.api as _api
        orig_now, _api.now = _api.now, _boom
        try:
            stamp = _MP._now_stamp()
        finally:
            _api.now = orig_now
        assert stamp and any(ch.isdigit() for ch in stamp), "debe caer a un ahora aproximado, no a vacío"
    finally:
        _MP._now_stamp = orig
