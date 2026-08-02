"""Observabilidad EN VIVO de un Brain Worker: que se vea qué hace desde el primer segundo.

Medido en la sesión del 2026-08-02: 21 s desde que nacía el worker hasta su primera fila visible, y un hueco de
2m21s sin una sola línea en mitad de una tarea de 5 min. El worker SÍ estaba hablando todo ese rato (dice qué va a
hacer, qué encuentra, por qué cambia de plan) pero `_map` solo traducía los bloques `tool_use` y tiraba el texto.
"""
from nucleo.workers.claude_session import ClaudeCodeSession


def _map(obj):
    s = object.__new__(ClaudeCodeSession)
    s._task_id = "7"
    s._native_sid = ""
    s._model = "claude-sonnet-4"
    s._done = False
    return list(s._map(obj))


def _assistant(*blocks):
    return {"type": "assistant", "message": {"content": list(blocks)}}


def test_assistant_text_becomes_a_visible_note():
    evs = _map(_assistant({"type": "text", "text": "Voy a buscar parques acuáticos abiertos hoy."}))
    notes = [e for e in evs if e.type == "note"]
    assert len(notes) == 1
    assert notes[0].data["text"] == "Voy a buscar parques acuáticos abiertos hoy."
    assert notes[0].task_id == "7"          # sellado con el ID de la sesión


def test_narration_is_never_spoken():
    """Sigue siendo observabilidad, no voz: `say` es SIEMPRE explícito por los puentes (§v2·E)."""
    evs = _map(_assistant({"type": "text", "text": "creo que empezaré por Aquopolis"}))
    assert not [e for e in evs if e.type == "say"]


def test_text_and_tools_coexist_in_order():
    evs = _map(_assistant(
        {"type": "text", "text": "Primero miro los horarios."},
        {"type": "tool_use", "name": "WebSearch", "input": {"query": "aquopolis horario"}},
    ))
    kinds = [e.type for e in evs]
    assert "note" in kinds and "step" in kinds
    assert kinds.index("note") < kinds.index("step")     # la narración llega ANTES que la herramienta


def test_whitespace_is_collapsed_and_empties_dropped():
    evs = _map(_assistant({"type": "text", "text": "  hola\n\n   mundo  "}))
    assert [e.data["text"] for e in evs if e.type == "note"] == ["hola mundo"]
    assert not [e for e in _map(_assistant({"type": "text", "text": "   "})) if e.type == "note"]


def test_unknown_block_types_are_still_ignored():
    evs = _map(_assistant({"type": "thinking", "thinking": "..."}, {"type": "image"}))
    assert evs == []


def test_result_and_init_are_untouched():
    assert [e.type for e in _map({"type": "system", "subtype": "init", "session_id": "abc"})] == ["spawned"]
    assert [e.type for e in _map({"type": "result", "subtype": "success", "result": "listo"})] == ["result", "done"]
