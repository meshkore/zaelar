"""observability/usage.py — ONE shape for every model call (V2-837 G4/G5).

The flash reply already said what it cost and how it went (model, tokens, prompt size, time to first token, finish
reason); a decision read (Jev) and a Brain Worker turn said none of it, so «the context is almost full» or «the
classifier is slow today» could not be seen from the record. Every model call that reaches the timeline carries
these keys in its `extra`, with the SAME names, so one reader (the local viewer, the operator console, `bus/log.py`'s
`tokens_in`/`tokens_out` columns) reads them all:

    model · provider · prompt_tokens · completion_tokens · cached_tokens · prompt_chars · reply_chars ·
    ms · ttft_ms · finish_reason · outcome

`prompt_tokens`/`completion_tokens` are the names the durable log already projects to its token columns. Absent
values are dropped, never written as null: the stamp rides on events that are stored forever.
"""
from __future__ import annotations

#: `outcome` says how the call ended: `ok` answered; `error` failed; `timeout` gave up on the clock; `truncated` answered
#: but was cut by its own limit (the 200 that looks like success); `pending` was read before it answered.


def shape(*, model=None, provider=None, prompt_tokens=None, completion_tokens=None, cached_tokens=None,
          prompt_chars=None, reply_chars=None, ms=None, ttft_ms=None, finish_reason=None, outcome=None) -> dict:
    """The usage block for one model call. The keyword list IS the shape — a new name is a TypeError, never a second
    shape; empty values are left out."""
    out = {}
    for k, v in (("model", model), ("provider", provider), ("prompt_tokens", prompt_tokens),
                 ("completion_tokens", completion_tokens), ("cached_tokens", cached_tokens),
                 ("prompt_chars", prompt_chars), ("reply_chars", reply_chars), ("ms", ms), ("ttft_ms", ttft_ms),
                 ("finish_reason", finish_reason), ("outcome", outcome)):
        if v is None or v == "":
            continue
        try:
            v = (int(v) if k.endswith(("_tokens", "_chars")) else round(float(v)) if k.endswith("ms")
                 else str(v)[:80])
        except (TypeError, ValueError):
            continue
        out[k] = v
    return out


#: The shape's field names, read off its signature (one source).
FIELDS = tuple(__import__("inspect").signature(shape).parameters)
