"""SOURCE guards for voice/engine/pipeline/agent.py — who may label with voice.trace.active()
(2026-08-16). Like test_lead_in.py's `test_el_relleno_consulta_la_sonda_y_muere_con_su_turno`: mounting the
real session requires half a LiveKit stack, so the DECISION is protected by reading the source code.

Origin: a live audit of a real session showed that the MAJORITY of `agent.py` events (transcript, bot_speech, tts,
state, metric, vad) arrived WITHOUT corr_id — they are created in SIBLING tasks to the one that sets the turn's
trace (`NucleoLLMStream._run_inner`), so the ContextVar never sees them, regardless of the actual temporal order
(confirmed against the livekit-agents 1.6.6 source code). `voice/trace.py::active()` is the explicit pointer
that fixes this — but ONLY for events that describe something about a trace that ALREADY EXISTS (TTS that sounds
because the turn has already generated text, a barge-in that interrupts an ongoing utterance, the assistant item
added after the LLM+TTS chain). Those that PRECEDE their own trace (the operator transcript, "voice detected",
"end of voice", STT metrics) are deliberately left WITHOUT forcing: attaching active() to them would attach
the PREVIOUS conversation's trace more often than the correct one — THAT case is resolved by
`cloud/backoffice/src/flowAttribution.js::attributeOrphans` at read time, which does know both sides of the
temporal window.

These tests establish that boundary so it does not inadvertently blur in a future change."""
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "voice/engine/pipeline/agent.py"


def _body():
    return SRC.read_text(encoding="utf-8")


def test_state_trace_safe_set_excludes_states_that_can_precede_their_own_trace():
    body = _body()
    i = body.index("_STATE_TRACE_SAFE = {")
    line = body[i:body.index("}", i) + 1]
    assert '"speaking"' in line and '"listening"' in line and '"interrupted"' in line
    assert '"thinking"' not in line, "'thinking' can fire before the turn's own trace exists — must stay unsafe"
    assert '"idle"' not in line, "'idle' can fire before the turn's own trace exists — must stay unsafe"


def test_on_state_change_only_reads_active_when_the_state_is_safe():
    body = _body()
    i = body.index("def on_state_change(state: State) -> None:")
    block = body[i:body.index("def ", i + 10)]
    assert "if state.value in _STATE_TRACE_SAFE:" in block
    assert "trace.active()" in block


def test_operator_transcript_and_interim_never_read_active():
    """The operator's FINAL transcript (and its interim) are created BEFORE the trace of the turn they will
    trigger exists — forcing active() here would attach the previous conversation's trace. It must continue to be
    resolved at read time (attributeOrphans), not here."""
    body = _body()
    i = body.index('@session.on("user_input_transcribed")')
    block = body[i:body.index("@session.on(", i + 10)]
    assert "trace.active()" not in block


def test_stt_metrics_never_read_active_but_tts_metrics_do():
    body = _body()
    i = body.index('@session.on("metrics_collected")')
    block = body[i:body.index("@session.on(", i + 10)] if "@session.on(" in body[i + 10:] else body[i:]
    tts_block = block[block.index('kind == "TTSMetrics"'):block.index('kind == "STTMetrics"')]
    stt_block = block[block.index('kind == "STTMetrics"'):]
    assert "trace.active()" in tts_block, "TTS metrics describe audio for text the turn already generated"
    assert "trace.active()" not in stt_block, "STT metrics describe recognition that precedes the turn's trace"


def test_vad_speaking_onset_and_end_of_speech_never_read_active_but_barge_in_does():
    body = _body()
    i = body.index('@session.on("user_state_changed")')
    block = body[i:body.index("@session.on(", i + 10)]
    barge_in = block[block.index("if was_bot_speaking:"):block.index("🎤 voz detectada")]
    rest = block[block.index("🎤 voz detectada"):]
    assert "trace.active()" in barge_in, "a barge-in interrupts an ALREADY-open trace's speech"
    assert "trace.active()" not in rest, "onset/end-of-speech precede the trace of the turn they're about to trigger"


def test_conversation_item_added_reads_active_only_for_the_assistant_branch():
    body = _body()
    i = body.index('@session.on("conversation_item_added")')
    block = body[i:body.index("@session.on(", i + 10)]
    assert 'role == "assistant"' in block
    assert "trace.active()" in block
