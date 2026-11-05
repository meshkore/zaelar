from tests import voice_turn_source as _vts
"""V2-660 — the errand HARNESS closes the circle, and the window measures silence from speech ONSET.

Session 0141a72a (2026-09-11), two defects in one minute:
  1. «Johnny.» opened a 5 s window; he began «Enséñame la declaración de independencia» 2 s later and the
     STT finalized it 6 s later — judged at the END it fell outside the window and became room noise.
  2. After his «Adelante» the model said «Claro, aquí tienes el texto completo…» having run ONE web_search;
     the `documento` card was open and EMPTY, and nothing compared the claim with the screen.
"""
import asyncio
import os

import pytest

from nucleo.circuit import harness
from voice import attention

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    attention.reset()
    harness.reset()
    yield
    attention.reset()
    harness.reset()


def _src(rel: str) -> str:
    return _vts.read(os.path.join(ENG, rel))


# ── the window measures SILENCE, and silence ends at speech onset ───────────────────────────────────────
def test_a_sentence_begun_inside_the_window_is_directed_even_if_it_ends_after_it(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    t = 1000.0
    attention.note_directed(now=t)              # «Johnny.»
    attention.note_speech_onset(now=t + 2)      # he starts the sentence
    v = attention.evaluate("enséñame la declaración de independencia", now=t + 6)   # STT final, 6 s later
    assert v.directed and v.reason == "active_window"


def test_without_an_onset_the_end_of_speech_still_rules(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    t = 1000.0
    attention.note_directed(now=t)
    assert not attention.evaluate("enséñame la declaración", now=t + 6).directed


def test_a_stale_onset_from_before_the_anchor_grants_nothing(monkeypatch):
    """An onset OLDER than the anchor belongs to earlier speech — it must not stretch the window."""
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    t = 1000.0
    attention.note_speech_onset(now=t - 30)
    attention.note_speech_end(now=t - 28)       # V2-661: that earlier speech ENDED — it is not the anchor's utterance
    attention.note_directed(now=t)
    assert not attention.evaluate("y otra cosa", now=t + 6).directed


def test_the_vad_rising_edge_stamps_the_onset():
    body = _src("voice/engine/pipeline/agent.py")
    i = body.index('@session.on("user_state_changed")')
    block = body[i:body.index("@session.on(", i + 10)]
    assert "note_speech_onset()" in block, "the VAD handler no longer stamps the onset — the fix is dead"


# ── the ledger and the verifier ─────────────────────────────────────────────────────────────────────────
def _fake_view(monkeypatch, views: dict, opened: set | None = None):
    from nucleo.circuit import verify
    monkeypatch.setattr(verify, "card_view", lambda wid: views.get(wid))
    monkeypatch.setattr(verify, "card_on_screen", lambda wid: (wid in opened) if opened is not None else None)


def test_a_goal_is_born_once_per_target_and_expires():
    g1 = harness.note_goal(harness.KIND_WIDGET_CONTENT, "documento", "muéstrame la declaración", now=100.0)
    g2 = harness.note_goal(harness.KIND_WIDGET_CONTENT, "Documento", "en castellano", now=101.0)
    assert g1 is g2 and g2["text"] == "en castellano"
    assert len(harness.open_goals(now=102.0)) == 1
    assert harness.open_goals(now=102.0 + harness.TTL_S + 1) == []


def test_an_empty_card_is_unmet_a_filled_open_card_is_met(monkeypatch):
    g = harness.note_goal(harness.KIND_WIDGET_CONTENT, "documento", "la declaración")
    _fake_view(monkeypatch, {"documento": {"empty": True, "body": ""}}, opened={"documento"})
    assert asyncio.run(harness.verify(g)) is False
    _fake_view(monkeypatch, {"documento": {"empty": False, "body": "Cuando en el curso…"}}, opened={"documento"})
    assert asyncio.run(harness.verify(g)) is True


def test_a_widget_that_cannot_be_read_is_unverifiable_never_unmet(monkeypatch):
    """The harness stays silent when it cannot see: a wrong «you did not deliver» over a delivered card is
    worse than none."""
    g = harness.note_goal(harness.KIND_WIDGET_CONTENT, "musica", "pon la lista")
    _fake_view(monkeypatch, {"musica": {"tracks": []}})          # no `empty` key declared
    assert asyncio.run(harness.verify(g)) is None
    _fake_view(monkeypatch, {})                                   # unreadable
    assert asyncio.run(harness.verify(g)) is None


def test_a_met_goal_closes_on_the_sweep_and_leaves_the_prompt(monkeypatch):
    g = harness.note_goal(harness.KIND_WIDGET_CONTENT, "documento", "la declaración")
    # V2-755 — a goal nobody has VERIFIED yet says nothing. This line used to assert the prompt spoke
    # the moment the goal was born, and that is the defect: over a widget that cannot declare emptiness
    # the sentence «la hoja sigue VACÍA» was never true and never went away (three minutes of it over a
    # full video card, session 665e666a). So the goal is verified UNMET first, and what this pins — a
    # met goal closes on the sweep and leaves the prompt — is unchanged.
    _fake_view(monkeypatch, {"documento": {"empty": True}}, opened={"documento"})
    assert asyncio.run(harness.verify(g)) is False
    assert harness.prompt_lines() and "VACÍA" in harness.prompt_lines()[0]
    _fake_view(monkeypatch, {"documento": {"empty": False}}, opened={"documento"})
    closed = asyncio.run(harness.sweep())
    assert len(closed) == 1 and closed[0]["status"] == "met"
    assert harness.open_goals() == [] and harness.prompt_lines() == []


# ── the four seams are wired ────────────────────────────────────────────────────────────────────────────
def test_the_turn_records_its_shown_cards_and_reads_no_claim_from_its_reply():
    """V2-851 F5: the turn end no longer reads the reply for a CLAIM of delivery nor says a follow-up after it —
    shown cards stay goals the prompt carries; the claim grammar and `false_claim` are gone (disarm: either back → red)."""
    seam = _src("nucleo/flash/harness_turn.py")
    assert "harness.note_goal(harness.KIND_WIDGET_CONTENT" in seam, "shown cards become goals"
    assert not hasattr(harness, "claims_done") and not hasattr(harness, "false_claim")
    prov = _src("voice/engine/llm/providers/nucleo.py")
    assert "_ht.note_shown(_shown_ids" in prov, "the turn's shown cards must reach the ledger"
    assert "_ht.rescue(" not in prov and "follow_up_line" not in prov


def test_the_prompt_and_the_heartbeat_read_the_ledger(monkeypatch):
    # V2-661: the harness lines joined their two neighbours in `live_blocks`; read on the built live state.
    from nucleo.turn.prompt import live_record
    from nucleo.turn.prompt import live_state
    monkeypatch.setattr(live_record, "harness_lines", lambda: ["HARNESS-MARK"])
    assert "HARNESS-MARK" in live_state.live_state()
    assert "harness.prompt_lines()" in _src("nucleo/turn/prompt/live_record.py")
    loop = _src("nucleo/pulse/loop.py") + _src("nucleo/pulse/flows.py")
    assert "await self._supervise_harness(now)" in loop and "harness.sweep(now)" in loop
