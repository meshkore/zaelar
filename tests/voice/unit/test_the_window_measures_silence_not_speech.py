"""V2-661 — the window measures the operator's SILENCE, and his silence has not started while he is talking.

Session 1cdcb08e (2026-09-11, 00:46): with the window open he spoke for 47 seconds without a pause longer than
1.1 s — eleven VAD rising edges, the STT holding the sentence as «frase a medias» the whole time. V2-660 had made
the window measure from speech ONSET, but every rising edge re-stamped that onset, so the final sentence was
measured from its LAST breath (33 s after the anchor) and thrown away as room noise; the ring on his orb had gone
dark five seconds in, because the client's timer only knew the last verdict and no verdict arrives mid-sentence.
His rule, verbatim: «cuando pasan tres o cuatro segundos [de silencio] cortas el micrófono». Not before.
"""
import os
import re

import pytest

from voice import attention

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture(autouse=True)
def _smart(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    attention.reset()
    yield
    attention.reset()


def _src(rel: str) -> str:
    return open(os.path.join(ENG, rel), encoding="utf-8").read()


# ── the measured incident, replayed second by second ───────────────────────────────────────────────────────
def test_the_47_second_utterance_of_session_1cdcb08e_is_directed():
    """Timestamps relative to 00:46:00. Fragment verdicts landed at :08.8 / :11.0 / :17.1 while he kept
    talking; VAD flickered eleven times with gaps under 1.1 s; the whole sentence was judged at :52.3."""
    W = attention.window_s()
    assert W <= 5.0
    attention.note_directed(now=0.9)                      # «…Johnny» — the wake-word verdict
    attention.note_speech_onset(now=4.5); attention.note_speech_end(now=5.21)
    attention.note_speech_onset(now=5.81)
    assert attention.evaluate("y detectamos que no es una ruta de", now=8.81).directed
    attention.note_directed(now=8.81)
    assert attention.evaluate("de un disco duro local,", now=11.0).directed
    attention.note_directed(now=11.0)
    attention.note_speech_end(now=11.66); attention.note_speech_onset(now=12.66)
    assert attention.evaluate("porque el sistema de archivos en la versión de la nube tiene", now=17.08).directed
    attention.note_directed(now=17.08)                    # judged mid-sentence: the turn got barge-in-cancelled
    for end, rise in ((20.11, 20.46), (28.76, 29.26), (32.41, 33.02), (45.81, 45.91), (50.01, 50.06)):
        attention.note_speech_end(now=end); attention.note_speech_onset(now=rise)
    attention.note_speech_end(now=51.66)
    v = attention.evaluate("…y en local, cuando detectemos que la ruta es de un archivo local, del mismo ordenador",
                           now=52.29)
    assert v.directed and v.reason == "active_window", "the sentence he never stopped saying was room noise"


def test_a_pause_longer_than_the_window_breaks_the_utterance():
    """The rule cuts both ways: silence for a whole window IS the end — the next words start a new clock."""
    attention.note_directed(now=100.0)
    attention.note_speech_onset(now=102.0); attention.note_speech_end(now=104.0)
    attention.note_speech_onset(now=110.0)                # 6 s of silence: past the 5 s window
    attention.note_speech_end(now=111.0)
    assert not attention.evaluate("y otra cosa más", now=112.0).directed


def test_a_pause_shorter_than_the_window_continues_the_utterance():
    attention.note_directed(now=100.0)
    attention.note_speech_onset(now=102.0); attention.note_speech_end(now=104.0)
    attention.note_speech_onset(now=108.0)                # 4 s of silence: still the same breath
    attention.note_speech_end(now=111.0)
    assert attention.evaluate("y otra cosa más", now=112.0).directed


def test_a_fragment_verdict_mid_sentence_keeps_the_clock_at_zero():
    """The STT finalizes a fragment while he is still talking; its verdict re-anchors the window. The rest of
    the sentence must not be measured against an onset OLDER than that anchor."""
    attention.note_directed(now=1000.0)
    attention.note_speech_onset(now=1002.0)               # no falling edge yet — one long breath
    attention.note_directed(now=1006.0)                   # the fragment's verdict, mid-sentence
    assert attention.evaluate("…y sigo hablando", now=1014.0).directed


def test_a_missed_falling_edge_cannot_hold_the_window_past_the_cap():
    attention.note_directed(now=1000.0)
    attention.note_speech_onset(now=1001.0)               # the VAD never reports the end
    assert attention.evaluate("algo", now=1001.0 + attention._UTTERANCE_CAP_S - 1.0).directed, "inside the cap it holds"
    assert attention.evaluate("algo", now=1001.0 + attention._UTTERANCE_CAP_S + 1.0).reason == "ambient"


def test_window_open_follows_the_utterance_and_closes_after_real_silence():
    attention.note_directed(now=1000.0)
    attention.note_speech_onset(now=1002.0); attention.note_speech_end(now=1003.0); attention.note_speech_onset(now=1004.0)
    assert attention.window_open(now=1009.0), "mid-utterance the window is open, whatever the timer says"
    attention.note_speech_end(now=1009.0)
    assert not attention.window_open(now=1015.0), "six seconds of real silence closes it"


def test_reset_forgets_the_edges():
    attention.note_speech_onset(now=1.0); attention.note_speech_end(now=2.0)
    attention.reset()
    assert attention._state["speech_onset"] == 0.0 and attention._state["speech_end"] == 0.0
    assert attention._state["speech_rise"] == 0.0


# ── the seams ───────────────────────────────────────────────────────────────────────────────────────────────
def _strip_comments(js: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", js, flags=re.S)


def test_the_vad_falling_edge_reaches_the_gate_and_both_edges_are_named_for_the_client():
    body = _src("voice/engine/pipeline/agent.py")
    i = body.index('@session.on("user_state_changed")')
    block = body[i:body.index("@session.on(", i + 10)]
    assert "note_speech_end()" in block, "the falling edge no longer starts the silence clock"
    assert '"edge": "on"' in block and '"edge": "off"' in block, "the client cannot tell the edges apart"


def test_the_ring_holds_while_his_voice_is_active_and_never_lights_from_off():
    js = _strip_comments(_src("frontend/app/services/sse.js"))
    m = re.search(r'd\.kind === "vad"[^{]*\{(.*?)\n    \}', js, flags=re.S)
    assert m, "sse.js has no `vad` branch — the ring dies on its timer mid-sentence again"
    branch = m.group(1)
    assert "store.attentionHit()" in branch and "pulseAttentionHit" in branch
    assert 'd.edge === "on"' in branch
