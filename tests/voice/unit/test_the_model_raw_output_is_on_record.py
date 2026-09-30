"""Demo pass 2026-09-28, C2: the model returned 127 completion tokens, 0 characters and no tool call that reached the
turn — and nothing on record could say what those tokens were (hidden reasoning? a tool call that failed to parse?
text a sanitizer ate?). The stream keeps the raw text, the raw tool calls and the hidden-reasoning size in the
turn's metrics, and the reply event carries them."""
from tests import voice_turn_source as _vts
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_the_stream_keeps_what_the_model_returned():
    src = (ROOT / "nucleo/flash/fast_client.py").read_text("utf-8")
    loop = src[src.index("async for chunk in stream:"):]
    loop = loop[:loop.index("def describe(")]
    assert 'm["raw_text"]' in loop and 'm["reasoning_chars"]' in loop and 'm["raw_tool_calls"]' in loop


def test_the_reply_event_carries_it():
    prov = _vts.read(ROOT / "voice/engine/llm/providers/nucleo.py")
    body = prov[prov.index("        _reply_extra = {"):]
    body = body[:body.index("\n        }")]
    for k in ("raw_text", "raw_tool_calls", "reasoning_chars", "finish_reason", "dropped_tool_calls"):
        assert f'"{k}": llm_metrics.get("{k}")' in body, k
