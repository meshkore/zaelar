"""The Anthropic Messages SSE stream as a pure state machine (V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/fast_client.py` (901 lines, over the 900 a new file may reach): the parser has no
transport and no dependency on the client, which is why it was testable on its own (`tests/infrastructure/unit/
test_zai_sse.py`). `fast_client` imports it back under its old name.
"""
from __future__ import annotations

import json


class _AnthropicSSE:
    """PURE state machine for the Anthropic Messages SSE stream (the protocol spoken by direct Z.AI). Deliberately
    separate from HTTP transport → testable with synthetic `data:` objects (see tests). `feed(obj)` receives ONE
    JSON object from a `data:` line and returns a list of events: `("text", str)` for each `text_delta`, and
    `("tool", name, input_dict)` when a `tool_use` block closes (accumulating `input_json_delta.partial_json`)."""

    def __init__(self) -> None:
        self._blocks: dict[int, dict] = {}   # index → {"type","name","json"}

    def feed(self, obj: dict) -> list[tuple]:
        out: list[tuple] = []
        t = obj.get("type")
        if t == "content_block_start":
            cb = obj.get("content_block") or {}
            self._blocks[obj.get("index")] = {"type": cb.get("type"), "name": cb.get("name", ""), "json": ""}
        elif t == "content_block_delta":
            d = obj.get("delta") or {}
            dt = d.get("type")
            if dt == "text_delta" and d.get("text"):
                out.append(("text", d["text"]))
            elif dt == "input_json_delta":
                b = self._blocks.get(obj.get("index"))
                if b is not None:
                    b["json"] += d.get("partial_json", "") or ""
        elif t == "content_block_stop":
            b = self._blocks.get(obj.get("index"))
            if b and b.get("type") == "tool_use" and b.get("name"):
                try:
                    inp = json.loads(b["json"] or "{}")
                except Exception:
                    inp = {}
                out.append(("tool", b["name"], inp))
        return out
