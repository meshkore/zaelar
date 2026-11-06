"""What the engine asked the MeshKore network of live agents, ONE observer row each (capture gaps, 2026-11-06).

`nucleo/mesh_agents` asked the Oracle who can serve an errand and put the errand to one agent, and neither call left
a row of its own: an audit could see that a worker was served by the network, never what it asked, of whom, and
what came back. Kind `mesh` (family `system`):

    🌐 oracle · find               op=find · intent · coverage · agents · reached · ms · text=the query
    🌐 <agent> · ask · ✅/⚠️         op=ask · agent · status · ok · ms · fields (NAMES only) · answer · text=the prompt

The prompt and the answer are bounded and scrubbed (`observability/scrub`); the structured fields travel by name,
never by value; the bearer never enters. Never raises: a row that cannot be written is not a call that failed.
"""
from __future__ import annotations

from loguru import logger

import json

PROMPT_MAX = 300
ANSWER_MAX = 600


def _bounded(v, n: int) -> str:
    from observability import evidence as _evd
    from observability.scrub import scrub
    if not isinstance(v, str):
        try:
            v = json.dumps(v, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            v = str(v)
    return scrub(_evd.clip(v, n))


def found(query: str, out: dict, ms: int) -> None:
    try:
        from voice.observer import emit
        emit("mesh", "🌐 oracle · find", text=_bounded(query, PROMPT_MAX), role="system",
             extra={"op": "find", "ok": bool(out.get("reached")), "reached": bool(out.get("reached")),
                    "intent": str(out.get("intent") or "")[:80], "coverage": str(out.get("coverage") or "")[:40],
                    "agents": [str(a.get("agent_id") or "")[:80] for a in (out.get("agents") or [])][:8],
                    "ms": int(ms)})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"mesh: oracle find not recorded ({e!r})")


def asked(agent: dict, prompt: str, fields: dict | None, out: dict, status: int, ms: int) -> None:
    try:
        from voice.observer import emit
        aid = str((agent or {}).get("agent_id") or "?")[:80]
        ok = bool(out.get("ok"))
        extra = {"op": "ask", "agent": aid, "ok": ok, "status": int(status or 0), "ms": int(ms)}
        if fields:
            extra["fields"] = sorted(str(k)[:40] for k in fields)[:20]
        if ok:
            extra["answer"] = _bounded(out.get("data"), ANSWER_MAX)
        else:
            extra["error"] = _bounded(out.get("error") or ("payment required" if out.get("payment_required")
                                                           else "failed"), 200)
        emit("mesh", f"🌐 {aid} · ask · {'✅' if ok else '⚠️'}", text=_bounded(prompt if not fields else "", PROMPT_MAX),
             role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"mesh: ask not recorded ({e!r})")
