"""Unit — Anthropic Messages SSE parser for direct Z.AI streaming (V2-077, `_stream_zai`).

The HTTP transport is tested end-to-end against a live GLM-4.5-Air (pending funding); HERE we test the
PURE and deterministic component: `_AnthropicSSE.feed()` reconstructs the text and tool calls from the
stream's `data:` objects, including the realistic case of a `tool_use` `input_json` FRAGMENTED across multiple deltas.
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
    # message_start/message_delta/message_stop and unknown blocks produce no events and do not break.
    assert _drive([{"type": "message_start"}, {"type": "message_delta"}, {"type": "message_stop"}]) == []
