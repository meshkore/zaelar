"""A list step that renames the assistant leaves the name STORED, or is not done (V2-781, 2026-10-10).

Measured on `demo-initialization__es`: the INIT's first section («Te llamas Johnny…») ran as one step, the model answered
as Johnny, and nothing was written — the list still closed «28 de 28», because a step's verdict was its reply. Since
refactor2710-07 the step's own turn decides it like any turn: the brief's sure `identity_change = rename` and the name the
model declared (`nucleo/turn/identity`). Here the step is judged on the STORE: when its turn's verdict ordered a rename,
`state.assistant_name` must hold that name afterwards, whatever the reply said.
"""
from __future__ import annotations

import asyncio


def _stored() -> str:
    from memory import api as _mem
    return str((_mem.state() or {}).get("assistant_name") or "").strip()


async def settle(since: float) -> dict | None:
    """None when no turn since `since` was ordered to rename. Otherwise `{"name", "stored"}`: whether the store holds the
    name the model gave (an ordered rename with no name from the model is not stored). Never raises."""
    try:
        from nucleo.turn import identity
        got = identity.rename_ordered_since(since)
        if got is None:
            return None
        name = got["name"]
        stored = bool(name) and (await asyncio.to_thread(_stored)).casefold() == name.casefold()
        return {"name": name, "stored": stored}
    except Exception as e:  # noqa: BLE001 — unverifiable is not stored: the step reports it
        return {"name": "", "stored": False, "error": f"{type(e).__name__}: {e}"}
