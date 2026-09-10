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

from nucleo import harness
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
    return open(os.path.join(ENG, rel), encoding="utf-8").read()


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
    attention.note_directed(now=t)
    assert not attention.evaluate("y otra cosa", now=t + 6).directed


def test_the_vad_rising_edge_stamps_the_onset():
    body = _src("voice/engine/pipeline/agent.py")
    i = body.index('@session.on("user_state_changed")')
    block = body[i:body.index("@session.on(", i + 10)]
    assert "note_speech_onset()" in block, "the VAD handler no longer stamps the onset — the fix is dead"


# ── the claim grammar ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("txt", [
    "Claro, aquí tienes el texto completo de la Declaración de Independencia.",
    "Ya la tienes en pantalla.",
    "Te lo he puesto en el documento.",
    "Ya está cargado, Ricardo.",
    "Here it is — the full text.",
])
def test_a_completion_claim_is_recognized(txt):
    assert harness.claims_done(txt)


@pytest.mark.parametrize("txt", [
    "Todavía no lo tienes en pantalla, dame un momento.",     # negated — honest
    "Te lo busco y te lo pongo en el documento.",             # a PROMISE, not a claim (promise_backstop's job)
    "¿Te refieres a la Declaración de Independencia de los Estados Unidos?",
    "",
])
def test_promises_and_negations_are_not_claims(txt):
    assert not harness.claims_done(txt)


# ── the ledger and the verifier ─────────────────────────────────────────────────────────────────────────
def _fake_view(monkeypatch, views: dict, opened: set | None = None):
    async def _view(wid):
        return views.get(wid)
    monkeypatch.setattr(harness, "_widget_view", _view)
    monkeypatch.setattr(harness, "_card_is_open", lambda wid: (wid in opened) if opened is not None else None)


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


def test_the_false_claim_is_the_measured_incident(monkeypatch):
    harness.note_goal(harness.KIND_WIDGET_CONTENT, "documento", "muéstrame la declaración de independencia")
    _fake_view(monkeypatch, {"documento": {"empty": True}}, opened={"documento"})
    g = asyncio.run(harness.false_claim("Claro, aquí tienes el texto completo de la Declaración.", data_done=False))
    assert g and g["target"] == "documento"
    req = harness.rescue_request(g)
    assert "declaración de independencia" in req and "documento" in req and "VACÍA" in req


def test_a_data_op_this_turn_is_trusted_over_the_stale_store(monkeypatch):
    """Fire-and-forget (V2-603): the store may not have caught up — the harness must never contradict a
    data-op the same turn just fired."""
    harness.note_goal(harness.KIND_WIDGET_CONTENT, "documento", "la declaración")
    _fake_view(monkeypatch, {"documento": {"empty": True}}, opened={"documento"})
    assert asyncio.run(harness.false_claim("Aquí la tienes.", data_done=True)) is None


def test_a_met_goal_closes_on_the_sweep_and_leaves_the_prompt(monkeypatch):
    harness.note_goal(harness.KIND_WIDGET_CONTENT, "documento", "la declaración")
    assert harness.prompt_lines() and "VACÍA" in harness.prompt_lines()[0]
    _fake_view(monkeypatch, {"documento": {"empty": False}}, opened={"documento"})
    closed = asyncio.run(harness.sweep())
    assert len(closed) == 1 and closed[0]["status"] == "met"
    assert harness.open_goals() == [] and harness.prompt_lines() == []


# ── the four seams are wired ────────────────────────────────────────────────────────────────────────────
def test_the_voice_channel_wires_the_harness_before_the_rescue_and_the_holding_line():
    prov = _src("voice/engine/llm/providers/nucleo.py")
    i = prov.index("_harness.false_claim(spoken_text, data_done=bool(data_done")
    assert i < prov.index("oversized_widget_write as _oversized"), "harness runs before the V2-658 rescue"
    assert i < prov.index('if escalate_req["v"] is not None and not spoken_text:')
    assert "_harness.note_goal(_harness.KIND_WIDGET_CONTENT, _gid, _h_words" in prov, "shown cards become goals"
    assert "_shown_ids.add(_pw)" in prov, "the promise-backstop show must register its card as a goal too"


def test_the_probe_mirrors_goal_birth_and_the_false_claim():
    probe = _src("nucleo/flash/probe.py")
    assert "_harness_p.note_goal(" in probe and "_harness_p.false_claim(spoken" in probe


def test_the_prompt_and_the_heartbeat_read_the_ledger():
    assert "_harness.prompt_lines()" in _src("nucleo/flash/prompt.py")
    loop = _src("nucleo/loop.py")
    assert "await self._supervise_harness(now)" in loop and "harness.sweep(now)" in loop
