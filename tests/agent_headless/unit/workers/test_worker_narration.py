"""LIVE observability for a Brain Worker: make it possible to see what it does from the first second.

Measured in the 2026-08-02 session: 21 s from the worker being spawned to its first visible row, and a gap of
2m21s with not a single line in the middle of a 5 min task. The worker WAS talking the whole time (it says what it is
going to do, what it finds, and why it changes plans), but `_map` only translated the `tool_use` blocks and discarded the text.
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
    assert notes[0].task_id == "7"          # sealed with the session ID


def test_narration_is_never_spoken():
    """It remains observability, not voice: `say` is ALWAYS explicit through the bridges (§v2·E)."""
    evs = _map(_assistant({"type": "text", "text": "creo que empezaré por Aquopolis"}))
    assert not [e for e in evs if e.type == "say"]


def test_text_and_tools_coexist_in_order():
    evs = _map(_assistant(
        {"type": "text", "text": "Primero miro los horarios."},
        {"type": "tool_use", "name": "WebSearch", "input": {"query": "aquopolis horario"}},
    ))
    kinds = [e.type for e in evs]
    assert "note" in kinds and "step" in kinds
    assert kinds.index("note") < kinds.index("step")     # the narration arrives BEFORE the tool


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
