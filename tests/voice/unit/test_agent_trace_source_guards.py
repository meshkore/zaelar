"""Guardas de FUENTE sobre voice/engine/pipeline/agent.py — quién puede etiquetar con voice.trace.active()
(2026-08-16). Igual que test_lead_in.py's `test_el_relleno_consulta_la_sonda_y_muere_con_su_turno`: montar la
sesión real exige media pila de LiveKit, así que se protege la DECISIÓN leyendo el código fuente.

Origen: una auditoría en vivo de una sesión real mostró que la MAYORÍA de eventos de `agent.py` (transcript,
bot_speech, tts, state, metric, vad) llegaban SIN corr_id — nacen en tareas HERMANAS de la que fija el trace del
turno (`NucleoLLMStream._run_inner`), así que el ContextVar nunca los ve, sea cual sea el orden temporal real
(confirmado contra el código fuente de livekit-agents 1.6.6). `voice/trace.py::active()` es el puntero explícito
que arregla esto — pero SOLO para los eventos que describen algo sobre un trace que YA EXISTE (TTS que suena
porque el turno ya generó texto, un barge-in que interrumpe una locución en marcha, el item del asistente
añadido tras la cadena LLM+TTS). Los que PRECEDEN a su propio trace (el transcript del operador, "voz
detectada", "fin de voz", las métricas de STT) se dejan SIN forzar a propósito: colgarles active() les pegaría
el trace de la conversación ANTERIOR más a menudo que el correcto — ESE caso lo resuelve
`cloud/backoffice/src/flowAttribution.js::attributeOrphans` en lectura, que sí conoce ambos lados de la ventana
temporal.

Estos tests fijan esa línea para que no se difumine sin querer en un cambio futuro."""
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
    """El transcript FINAL del operador (y su interim) nacen ANTES de que exista el trace del turno que van a
    disparar — forzar active() aquí les pegaría el de la conversación anterior. Debe seguir resolviéndose en
    lectura (attributeOrphans), no aquí."""
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
