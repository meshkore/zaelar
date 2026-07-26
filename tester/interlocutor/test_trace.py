#
# Regression test for the double-counting bug found in the 2026-07-26 audit: a filler phrase ("Mmm…") spoken
# before the real reply made `zaelar_texts()` join the `transcript` event (filler+reply, audio ground truth) AND
# the `brain` reply event (reply only) as if they were two DIFFERENT utterances — the judge then saw every
# filler-preceded turn as "reply … filler … reply", a duplication that never actually happened in production.
from .trace import zaelar_texts


def test_filler_then_transcript_prefers_transcript_no_duplication():
    events = [
        {"kind": "brain", "role": "assistant", "label": "filler", "text": "Mmm…"},
        {"kind": "brain", "role": "assistant", "label": "…reply", "text": "Hola, todo bien. ¿Qué necesitas?"},
        {"kind": "transcript", "role": "assistant", "text": "Mmm… Hola, todo bien. ¿Qué necesitas?"},
    ]
    assert zaelar_texts(events) == ["Mmm… Hola, todo bien. ¿Qué necesitas?"]


def test_no_transcript_falls_back_to_brain_reply():
    events = [
        {"kind": "brain", "role": "assistant", "label": "…reply", "text": "Son las 14:32."},
    ]
    assert zaelar_texts(events) == ["Son las 14:32."]


def test_consecutive_identical_transcripts_dedup():
    events = [
        {"kind": "transcript", "role": "assistant", "text": "Vale."},
        {"kind": "transcript", "role": "assistant", "text": "Vale."},
    ]
    assert zaelar_texts(events) == ["Vale."]


def test_ignores_non_assistant_and_empty_text():
    events = [
        {"kind": "transcript", "role": "user", "text": "hola"},
        {"kind": "brain", "role": "assistant", "label": "…reply", "text": ""},
    ]
    assert zaelar_texts(events) == []
