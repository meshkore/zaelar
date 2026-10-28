"""Turn-specific semantic RECALL (`memory.query`), composed on demand and outside the event loop (T115/T116).

The STATE block (name, address, location, topics) is not here: it comes from the session cache (`memory_cache`, T114).
"""
from __future__ import annotations


def _observability_on() -> bool:
    """Is the memory observability layer (live viewer highlighting) active? UI-managed
    (`config/settings.py::memory_observability`), ON by default; env fallback `ZAELAR_MEM_OBSERVABILITY`."""
    try:
        from config import settings as _s
        v = _s.get("memory_observability")
        if v is not None:
            return bool(v)
    except Exception:
        pass
    import os as _os
    return (_os.getenv("ZAELAR_MEM_OBSERVABILITY", "1").strip().lower() not in ("0", "false", "no", "off"))


def compose_recall(recall_query: str = "", timings: dict | None = None,
                   lexical_only: bool = False) -> tuple[str, list[int]]:
    """Turn-specific SEMANTIC recall (`memory.query`). Returns (recall_block, used_ids). The STATE block
    (name/form of address/location/topics) does NOT go here: it comes from the session cache (`memory_cache`, T114). Best-effort.

    ⚠️ Performs blocking I/O (HTTP embeddings to Ollama): the caller runs it OUTSIDE the event loop
    (`asyncio.to_thread`, T115) and ONLY when the turn needs it (T116). `timings` fills `mem_query_ms` (T113)."""
    if not recall_query.strip():
        return "", []
    import time as _t
    _tq = _t.perf_counter()
    lines: list[str] = []
    used_ids: list[int] = []
    try:
        from memory import api as memory
        # Request a DEEP POOL (high limit) and retain DURABLE memory (mid/long): recency (SHORT, conversation
        # buffer, ephemeral messages) is ALREADY included IN FULL via `memory_cache._compose`. Including it here
        # double-counts it and, worse, recent chat (many `kind='conv'` rows) fills the retriever's top results and
        # BURIES the durable task/fact the operator asks about ("what did I ask you to write?"). With a low limit,
        # those durable rows are not retrieved at all; hence the deep request and mid/long filter → 8 durable slots.
        # `reinforce_used=False` intentionally (V2-311, 2026-08-25): reinforcement fires on DELIVERY, not
        # COMPUTATION. Composing this block no longer counts as using memory—21 of every 27 live recalls were
        # abandoned when the budget expired while the thread still finished, increasing weight and resetting
        # pill expiry for questions never answered with them. The delivery layer (`nucleo/turn/recall_budget`)
        # reinforces via `reinforce_ids`; selection still belongs to `memory/`, and only travels through here.
        res = memory.query(recall_query, limit=40, reinforce_used=False, lexical_only=lexical_only)
        if timings is not None:
            timings["recall_reinforce_ids"] = list(res.get("reinforce_ids") or [])
        mems = res.get("memories") or []
        used_ids = res.get("ids") or []
        durable = [m for m in mems if m.get("level") in ("mid", "long")]
        # V2-254 — THE THIRD SURFACE. A pill written by a widget cron is not a fact about the person, yet this
        # block—which runs EVERY TURN—mixed them: measured on 2026-08-21, "Weather in Soria now: 14.5C" ranked
        # ABOVE "Lives in central Madrid" under "this may be relevant (from your memory)," and the turn ended up
        # searching for a plumber in Soria.
        #
        # The rule has ONE home (`memory.api.background_slot_off_topic`) and is APPLIED, not rewritten, here. This
        # is the V2-252 defect: a decision repeated in two places silently diverges. The rule's own docstring lists
        # all three surfaces that must apply it. It lived on only one for five weeks; each other surface required
        # a separate live failure to discover.
        #
        # Deliberately conditional: if the operator NAMES the topic ("what is the weather in Soria?"), the pill enters.
        try:
            from memory.api import background_slot_off_topic as _off_topic
            durable = [m for m in durable if not _off_topic(m.get("slot"), recall_query)]
        except Exception:  # noqa: BLE001
            pass                     # without the rule, too much is shown, never too little: no memory is lost
        for m in durable[:8]:
            txt = (m.get("text") or "").strip().replace("\n", " ")
            if txt:
                lines.append(f"· {txt[:160]}")
        # Live observability (V2-014, gated): a query HIGHLIGHTS the pieces it touched in the viewer (blue).
        # Separate `op:"query"` signal → does not refresh data, only colors it. Gated by `memory_observability`
        # (ON by default) because it adds fine-grained traffic; off leaves the viewer working without highlighting.
        if used_ids and _observability_on():
            try:
                import bus
                bus.emit_sync("memory.updated", {"op": "query", "ids": [int(i) for i in used_ids]})
            except Exception:
                pass
    except Exception:
        pass
    if timings is not None:
        timings["mem_query_ms"] = round((_t.perf_counter() - _tq) * 1000, 1)
    if not lines:
        return "", used_ids
    block = "Puede que venga a cuento (de tu memoria):\n" + "\n".join(lines) + "\n"
    return block, used_ids
