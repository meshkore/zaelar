"""V2-468 · a span for ONE event does not last zero, and reading it that way contradicts the fact that it does measure it.

`audit.spans` is carried in full in the JSON received by the judge, with `first_ms` and `last_ms`. For a span of ONE
single event, the two coincide, and from that one reads “duration 0 ms.” A rail that announces the start once and
falls silent while it works has EXACTLY that shape — which is the shape of the music player.

MEASURED in `play-music-and-build-playlist` (2026-08-28 21:38, ES studio). The report contained
`rail:music.playing` with `n: 1, first_ms: 7859, last_ms: 7859`, and `widgets_producing: ["musica"]` — the fact
that truly answers “was anything playing?”, stated in words two lines above with “regardless of what the
rest says.” The judge wrote: “the span 'rail:music.playing' shows a duration of 0ms (instantaneous) … it is
considered that the audio was only prepared without playing,” and scored the result 1.

The test was not invented: it read a REAL field whose shape invites that interpretation. That is why the fix is NOT
to forbid it from looking at spans or tell it the opposite conclusion — it is to name the shape and tell it where the
meaningful measurement is.
"""
from tests.use_cases.e2e.agent import judge


def _line(mech):
    for l in judge.mechanism_facts(mech).splitlines():
        if "UN SOLO evento" in l:
            return l
    return ""


AUDIT_REAL = {"n_events": 277, "n_evidence": 0, "errors": [], "tools_run": {},
              "spans": {"rail:music.playing": {"n": 1, "first_ms": 7859, "last_ms": 7859, "errors": 0}}}


def test_the_single_event_span_is_named_with_what_it_does_not_mean():
    l = _line({"audit": AUDIT_REAL})
    assert "rail:music.playing" in l
    assert "NO porque durara cero" in l
    assert "SONANDO/REPRODUCIENDO" in l, "hay que decirle dónde está la medida que sí contesta"


def test_a_span_with_several_events_says_nothing():
    """The part that keeps this from being noise: a span with a REAL duration is read as usual."""
    au = {"n_events": 10, "n_evidence": 1, "errors": [], "tools_run": {},
          "spans": {"web:t1": {"n": 12, "first_ms": 100, "last_ms": 9000, "errors": 0}}}
    assert _line({"audit": au}) == ""


def test_it_does_not_claim_the_opposite_either():
    """It does not say “then it was playing”: `widgets_producing` measures that, and asserting it here would fabricate
    a pass from the harness — the symmetrical and worse failure."""
    l = _line({"audit": AUDIT_REAL})
    assert "sonaba" not in l.lower() and "sí ocurrió" not in l


def test_without_an_audit_there_is_no_line():
    assert _line({}) == ""
