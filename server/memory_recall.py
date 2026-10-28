"""The read behind `/api/memory/recall`: three lanes, never fused, each row with its provenance (V2-802 T-06; from
`server/memory_routes.py`, refactor2710-13 T-03). `memory_routes` imports it back."""
from memory import api as memapi

#: Window the default recall reads the conversation record over, in hours. The buffer keeps about this long.
_CONVERSATION_HOURS = 48.0


def _session_at(ts) -> str:
    """The work session open when a conversation line was written — from observability, which owns the event log.
    Unknown is '' and is said so; a broken read is reported, never swallowed into an empty field."""
    try:
        from observability import flows as _flows
        return _flows.session_at(float(ts or 0))
    except Exception as e:  # noqa: BLE001
        from voice.observer import emit
        emit("memory", "session lookup failed", text=str(e)[:160], extra={"module": "server.memory_routes"})
        return "?"


def _line(m: dict) -> str:
    """One digest line a worker can read and CITE: [when · where · who] text."""
    where = {"memory": f"memory/{m.get('kind') or '?'}", "conversation": "conversation",
             "message": "message"}.get(m.get("lane"), m.get("lane") or "?")
    tags = [m.get("created") or "?", where]
    if m.get("lane") == "conversation":
        if m.get("session"):
            tags.append(f"session {m['session'][:8]}")
        tags.append(m.get("who") or "?")
    else:
        if m.get("source"):
            tags.append(str(m["source"]))
        if m.get("entity"):
            tags.append(str(m["entity"]))
    return f"- [{' · '.join(tags)}] {m.get('text', '')}"


def _recall_sync(q: str, k: int, source: str, kind: str, hours: float) -> dict:
    # The lanes a recall can be filtered to (V2-802 T-06). Any other `source` value is read as a writer's
    # `meta.source` («whatsapp», «email», «voice», «worker:…») and narrows every lane to that source.
    is_lane = source in ("all", "memory", "messages", "conversation")
    lane = source if is_lane else "all"
    by_source = "" if is_lane else source
    kinds = {x.strip() for x in (kind or "").split(",") if x.strip()}
    out: list[dict] = []
    if q and lane in ("all", "memory", "messages"):
        r_lane = {"all": "all", "memory": "own", "messages": "messages"}[lane]
        res = memapi.query(q, limit=k, lane=r_lane)
        # `conv` rows are in the own lane of the retriever, but here they are served by the conversation reader
        # below, with who said them and when — not as a bare pill.
        mems = [m for m in (res.get("memories") or []) if m.get("text") and m.get("kind") != "conv"]
        prov = memapi.provenance([m["id"] for m in mems])
        for m in mems:
            p = prov.get(int(m["id"])) or {}
            out.append({"id": m["id"], "text": m.get("text", ""), "kind": m.get("kind", ""),
                        "slot": m.get("slot") or "", "level": m.get("level", ""), "created": p.get("created", ""),
                        "source": p.get("source"), "entity": p.get("entity"), "lane": p.get("lane", "memory")})
    if lane in ("all", "conversation") and (q or lane == "conversation"):
        h = hours or _CONVERSATION_HOURS
        sessions: dict[int, str] = {}                            # one lookup per turn, not per line
        for c in memapi.conversation(hours=h, query=q, limit=k if lane == "all" else 4 * k):
            if c["id"] not in sessions:
                sessions[c["id"]] = _session_at(c["ts"])
            out.append({"id": c["id"], "text": c["text"], "kind": "conv", "slot": "", "level": "short",
                        "created": c["at"], "source": "conv", "entity": None, "lane": "conversation",
                        "who": c["who"], "session": sessions[c["id"]]})
    if by_source:
        out = [m for m in out if str(m.get("source") or "") == by_source]
    if kinds:
        out = [m for m in out if m.get("kind") in kinds]
    # Lane order is the ranking contract: his own memory, then what he said, then what others wrote to him.
    order = {"memory": 0, "conversation": 1, "message": 2}
    out.sort(key=lambda m: order.get(m.get("lane"), 3))         # stable: each lane keeps its own order
    return {"memories": out, "text": "\n".join(_line(m) for m in out) or "(sin recuerdos relevantes)"}
