"""A list step that names the assistant leaves the name STORED, or is not done (V2-781, 2026-10-10).

Measured on `demo-initialization__es`: the INIT's first section («Te llamas Johnny. Cuando diga «Johnny», te
estoy hablando a ti. Actúa como mi asistente…») ran as one step, the model answered as Johnny, and nothing was
written — `state.assistant_name` stayed «Zaelar». The list still closed «28 de 28», because a step's verdict
was its reply. Two holes, one fix each:

  · the rename lane (`identity_actions.spoken_identity_order`) reads ONE sentence: on the whole step the name
    it extracted was «Johnny. Cuando diga «Johnny»», which is not a name, so the lane stood aside. Here the
    step is read sentence by sentence — the same strict lane, never a looser one — so «Te llamas Johnny.»
    renames and nothing else in the step does;
  · a step whose sentence names the assistant is judged on the STORE: if `state.assistant_name` does not hold
    that name afterwards, the step failed, whatever the reply said.

Only the list path uses this. A live utterance keeps its own lane, where one sentence is the whole turn.
"""
from __future__ import annotations

import asyncio
import re

_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+|\n+")


def named_in(goal: str) -> str | None:
    """The assistant's new name if one sentence of `goal` gives it (the strict rename lane), else None."""
    from nucleo.flash import identity_actions as _ident
    for s in _SENTENCE_RE.split(str(goal or "")):
        got = _ident.spoken_identity_order(s.strip())
        if got:
            return got[1]
    return None


def _stored() -> str:
    from memory import api as _mem
    return str((_mem.state() or {}).get("assistant_name") or "").strip()


async def settle(goal: str) -> dict | None:
    """None when the step names no assistant. Otherwise the name is made durable if it is not already, and
    `{"name", "stored"}` says whether the store holds it now. Never raises."""
    try:
        name = named_in(goal)
        if not name:
            return None
        if _stored().casefold() != name.casefold():
            from nucleo.flash import identity_actions as _ident
            await _ident.persist_rename(name)
        return {"name": name, "stored": (await asyncio.to_thread(_stored)).casefold() == name.casefold()}
    except Exception as e:  # noqa: BLE001 — unverifiable is not stored: the step reports it
        return {"name": "", "stored": False, "error": f"{type(e).__name__}: {e}"}
