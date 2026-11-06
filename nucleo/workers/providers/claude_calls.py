"""One row per MODEL CALL of a Brain Worker (capture gaps, 2026-11-06), around the Claude stream mapper (`claude_map._map`).
Part of providers.claude, which binds `_map_with_calls` as the session's `_map`."""
from __future__ import annotations

from loguru import logger

from nucleo.workers.providers import claude_map as _cm   # by module: claude_map may still be loading

# ── one row per MODEL CALL (capture gaps, 2026-11-06) ───────────────────────────────────────────────────────────
# A Brain Worker's model calls had no row of their own: the usage rode on the turn's first step or narration, and
# what the model was HANDED and what it ANSWERED had to be rebuilt from the rows around it. A call is opened by the
# first block of an assistant message and closed by the next answer (`user`), the next message or the `result`; the
# close yields ONE `model_call` event with the turn's usage, what went in (the tool results it was handed) and what
# came out (its text and the tools it asked for), both summarised and bounded. A worker killed mid-call leaves its
# partial usage (`usage` events) but no `model_call`: there is no answer to record.
#: Bounds of the two summaries (characters). The evidence of each tool result is already its own `step_result` row.
CALL_IN_MAX = 600
CALL_OUT_MAX = 600


def _map_with_calls(self, obj: dict):
    """`_map`, with the model call around it: an assistant message opens (or continues) a call and feeds it its text,
    tools and usage; the next answer (`user`), message or `result` closes it first, so its `model_call` comes before
    what follows it. The stream's own events are untouched."""
    t = obj.get("type")
    msg = obj.get("message") or {}
    if t in ("user", "result"):
        closed = _call_close(self)
    elif t == "assistant":
        closed = _call_open(self, msg)              # a new message with no answer between: the previous call is over
    else:
        closed = None
    if closed is not None:
        yield closed
    for ev in _cm._map(self, obj):
        if t == "assistant":
            if ev.type == "usage":
                _call_usage(self, (ev.data or {}).get("usage") or {}, {"turn": (ev.data or {})["turn"]}
                            if (ev.data or {}).get("turn") else {})
            elif ev.type == "note":
                _call_out(self, str((ev.data or {}).get("text") or ""))
            elif ev.type == "step":
                _call_out(self, "", tool=str((ev.data or {}).get("tool") or ""),
                          target=str((ev.data or {}).get("target") or ""))
        elif t == "user" and ev.type == "step_result":
            _call_in(self, str((ev.data or {}).get("tool") or ""), str((ev.data or {}).get("text") or ""))
        yield ev


def _call_open(self, msg: dict):
    """The first block of a new assistant message opens a call; returns the previous one's event when it was still
    open (two messages with no answer between). A repeated block of the same message keeps the call open."""
    if str(msg.get("model") or "") == "<synthetic>":
        return None                                  # a message the CLI made itself is not a model call
    mid = str(msg.get("id") or "")
    cur = getattr(self, "_call", None)
    if cur is not None and (not mid or cur.get("mid") == mid):
        return None
    closed = _call_close(self) if cur is not None else None
    self._call = {"mid": mid, "in": list(getattr(self, "_call_input", None) or []), "out": [], "tools": [],
                  "usage": None, "facts": {}}
    self._call_input = []
    return closed


def _call_usage(self, usage: dict, facts: dict) -> None:
    cur = getattr(self, "_call", None)
    if cur is not None and facts:                    # once per message: the CLI repeats a message's usage per block
        cur["usage"], cur["facts"] = dict(usage or {}), dict(facts)


def _call_out(self, text: str, tool: str = "", target: str = "") -> None:
    cur = getattr(self, "_call", None)
    if cur is None:
        return
    if text:
        cur["out"].append(text)
    if tool:
        cur["tools"].append(tool)
        cur["out"].append(f"→ {tool}" + (f" {target}" if target else ""))


def _call_in(self, tool: str, body: str) -> None:
    """What a tool answered: the input of the NEXT model call."""
    lst = getattr(self, "_call_input", None)
    if lst is None:
        lst = self._call_input = []
    lst.append(f"{tool or 'tool'}: {body}" if body else str(tool or "tool"))


def _clip(parts, n: int) -> str:
    try:
        from observability import evidence as _evd
        return _evd.clip(" · ".join(p for p in parts if p), n)
    except Exception:  # noqa: BLE001
        return " · ".join(p for p in parts if p)[:n]


def _call_close(self):
    """The open call as ONE `model_call` event, or None. Never raises: a record never stops the stream."""
    cur = getattr(self, "_call", None)
    self._call = None
    if cur is None:
        return None
    try:
        self._n_calls = int(getattr(self, "_n_calls", 0) or 0) + 1
        return self._ev("model_call", n=self._n_calls, model=getattr(self, "_model", "") or "",
                        real_model=getattr(self, "_real_model", "") or "",
                        usage=cur.get("usage") or {}, ctx_tokens=int(getattr(self, "_ctx_tokens", 0) or 0),
                        input=_clip(cur.get("in") or [], CALL_IN_MAX),
                        output=_clip(cur.get("out") or [], CALL_OUT_MAX),
                        tools=list(cur.get("tools") or [])[:12], **(cur.get("facts") or {}))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"worker: model call not recorded ({e!r})")
        return None
