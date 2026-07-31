"""Unit — parser SSE de Anthropic Messages para el streaming de Z.AI directo (V2-077, `_stream_zai`).

El transporte HTTP se prueba end-to-end contra un GLM-4.5-Air vivo (pendiente de fondos); AQUÍ se prueba la
pieza PURA y determinista: `_AnthropicSSE.feed()` reconstruye el texto y las tool-calls a partir de los objetos
`data:` del stream, incluido el caso realista de un `input_json` de tool_use FRAGMENTADO en varios deltas.
"""
from nucleo.flash.fast_client import _AnthropicSSE


def _drive(objs):
    p = _AnthropicSSE()
    out = []
    for o in objs:
        out += p.feed(o)
    return out


def test_text_deltas_accumulate():
    evs = _drive([
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hola"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " mundo"}},
        {"type": "content_block_stop", "index": 0},
    ])
    assert "".join(e[1] for e in evs if e[0] == "text") == "Hola mundo"
    assert not [e for e in evs if e[0] == "tool"]


def test_tool_use_json_reassembled_from_fragments():
    evs = _drive([
        {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "name": "web_search"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"query":'}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": ' "clima"}'}},
        {"type": "content_block_stop", "index": 0},
    ])
    tools = [(e[1], e[2]) for e in evs if e[0] == "tool"]
    assert tools == [("web_search", {"query": "clima"})]


def test_malformed_tool_json_yields_empty_input_not_crash():
    evs = _drive([
        {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "name": "t"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "{not json"}},
        {"type": "content_block_stop", "index": 0},
    ])
    assert [(e[1], e[2]) for e in evs if e[0] == "tool"] == [("t", {})]


def test_ignores_envelope_events():
    # message_start/message_delta/message_stop y bloques desconocidos no producen eventos ni rompen.
    assert _drive([{"type": "message_start"}, {"type": "message_delta"}, {"type": "message_stop"}]) == []
