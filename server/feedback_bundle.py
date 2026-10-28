"""What a report may carry, inside its budget — the pictures, the session bundle and the last turn read back
out of it (from `server/feedback_api.py`, refactor2710-13 T-03). `feedback_api` imports them back."""
#: The picture budget, and it is enforced HERE as well as in the browser: a client is not a guard, and
#: this endpoint is reachable by anything that can speak HTTP to the loopback.
_MAX_SHOTS = 3
_MAX_SHOT_BYTES = 180_000
_MAX_SHOTS_BYTES = 600_000
_SHOT_MIMES = ("image/webp", "image/jpeg", "image/png", "image/gif")
_MAX_EVIDENCE_EVENTS = 200
# The ingestion endpoint rejects a bundle over 40_000 bytes with a flat 400. 200 events can serialise to
# ~212_000 bytes, so without a byte cap every submission that ticked "include this session" would be
# refused and the user's message lost with it. The engine caps itself by BYTES here, and the count stays as
# the cheap first cut.
_MAX_EVIDENCE_BYTES = 30_000


def _fit_shots(shots) -> list[dict]:
    """The pictures that may travel, in the order they were attached, inside the budget (V2-695).

    Silent about what it drops ON PURPOSE at this layer: the browser already refused what did not fit and
    SAID so, with the same numbers. What reaches here past that is either a client that lied or one that
    is not ours, and neither earns an explanation — it earns a ceiling.
    """
    if not isinstance(shots, (list, tuple)):
        return []
    out: list[dict] = []
    total = 0
    for s in shots:
        if len(out) >= _MAX_SHOTS:
            break
        if not isinstance(s, dict):
            continue
        data = s.get("data")
        if not isinstance(data, str) or not data:
            continue
        mime = str(s.get("mime") or "")
        if mime not in _SHOT_MIMES:
            continue
        # The BYTES the picture really weighs, not the number it claims to: base64 is 4 chars per 3 bytes.
        size = (len(data) * 3) // 4
        if size > _MAX_SHOT_BYTES or total + size > _MAX_SHOTS_BYTES:
            continue
        total += size
        out.append({"name": str(s.get("name") or "captura")[:120], "mime": mime,
                    "bytes": size, "data": data})
    return out


def _fit_evidence(summary: dict, events: list) -> dict | None:
    """Trim the bundle until it fits `_MAX_EVIDENCE_BYTES`, keeping the MOST RECENT events — what the
    operator is reporting just happened, and the oldest events are the ones they are least likely to mean.
    Returns `None` when even the summary alone does not fit (nothing sensible left to attach).

    Halving instead of dropping one at a time: a session can carry thousands of events and this runs on the
    request path. `truncated` travels in the bundle so the reader never mistakes a trimmed session for a
    short one — the receiving end must not have to guess whether it is seeing everything."""
    import json as _json

    def _size(obj) -> int:
        return len(_json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    base = {"summary": summary, "events": []}
    if _size(base) > _MAX_EVIDENCE_BYTES:
        return None
    kept = list(events)
    while kept and _size({"summary": summary, "events": kept}) > _MAX_EVIDENCE_BYTES:
        kept = kept[-(len(kept) // 2):] if len(kept) > 1 else []
    out: dict = {"summary": summary, "events": kept}
    if len(kept) < len(events):
        out["truncated"] = {"kept": len(kept), "of": len(events), "reason": "size"}
    return out


def _last_turn(events: list) -> tuple[str, str, str]:
    """(what he asked last, what the agent said after it, that turn's trace) — from the bundle's own events,
    newest first. Empty strings when the session holds no conversation yet."""
    import json as _json
    asked = answered = trace = ""
    for e in reversed(events or []):
        if (e or {}).get("kind") != "transcript":
            continue
        try:
            pl = _json.loads(e.get("payload") or "{}")
        except Exception:  # noqa: BLE001
            pl = {}
        text = str(pl.get("text") or "").strip()
        if not text:
            continue
        who = str(e.get("label") or pl.get("label") or "")
        if who == "zaelar" and not answered and not asked:
            answered = text
        elif who != "zaelar" and not asked:
            asked = text
            trace = str(pl.get("trace") or e.get("corr_id") or "")
            break
    return asked, answered, trace
