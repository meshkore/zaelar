"""The assistant's own name and attention mode change by a VERDICT, never by a regex, and fail CLOSED (refactor2710-07).

CRIT-V8. A rename and the attention-mode toggle ride `set_style_directive`, but neither is a free-text rule: a rename is
the structured fact `state.assistant_name` (the wake word follows it, `voice.attention.set_assistant_name`) and the mode
is the configured setting `attention_mode`. WHICH of them his turn orders is the brief's `identity_change` question, read
after the model at `SURE`; the NEW NAME is the model's own declared argument (`set_style_directive.name`), never words
pulled out of his sentence. Absent, unsure, or no name from the model → nothing changes and the directive is an ordinary
rule: renaming takes one model turn, and the agent is never renamed by a guess (2026-09-09, «Cuéntame, Johnny»).
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

KEY = "identity_change"
SURE = 0.85
RENAME, NAME_ONLY, ALWAYS, NONE = "rename", "attention_name_only", "attention_always", "none"
CHOICES = {
    RENAME: "he tells the assistant to call itself by a different name from now on",
    NAME_ONLY: "he asks the assistant to answer only when he says its name (wake-word mode on)",
    ALWAYS: "he asks the assistant to listen to him always again (wake-word mode off)",
    NONE: "anything else: no change to the assistant's own name or to when it listens",
}
#: When a turn's sure verdict last ordered a rename, with the name the model gave (maybe ""): a list step that renames
#: the assistant must prove the name was STORED (`nucleo/batch/identity`).
_LAST: dict = {"name": "", "at": 0.0}


def question(_ctx=None) -> dict:
    return {"instructions": "Does the operator, in this message, change the assistant's OWN name or when it listens?",
            "criteria": dict(CHOICES)}


def verdict(brief) -> str:
    """The sure identity verdict of this turn, or NONE (absent, unsure, still in flight)."""
    from nucleo.turn import verdicts
    choice, info = verdicts.read(brief, KEY, NONE, min_confidence=SURE)
    return str(choice) if info and info.get("used") and choice in CHOICES else NONE


def apply_rename_now(name: str) -> None:
    """Process-level: the session's wake word tracks the new name at once, before the durable write."""
    from voice import attention
    attention.set_assistant_name(name)


async def persist_rename(name: str) -> None:
    from memory import api as _mem
    await asyncio.to_thread(_mem.set_state, {"assistant_name": name})


async def persist_attention_mode(mode_val: str) -> None:
    from config import settings as _cfg
    await asyncio.to_thread(_cfg.update, {"attention_mode": mode_val})


def rename_ordered_since(since: float) -> dict | None:
    """`{"name"}` when a turn's sure verdict ordered a rename at or after `since` (the model's name, maybe ""), once."""
    if _LAST["at"] < since:
        return None
    got = {"name": _LAST["name"]}
    _LAST.update(name="", at=0.0)
    return got


async def settle(brief, name: str, emit, *, ingest: bool = True) -> str:
    """Apply what the brief's identity verdict says, with the model's declared `name`. Returns `rename`, an attention
    value, or "" when nothing changed (the directive is then an ordinary rule). Never raises."""
    try:
        v = verdict(brief)
        if v == RENAME:
            _LAST.update(name=(name or "").strip()[:32], at=time.time())
        if v == RENAME and (name or "").strip():
            name = name.strip()[:32]
            apply_rename_now(name)
            emit("brain", "🏷️ zaelar se renombra", text=name, role="system", extra={"cat": "flash", "verdict": v})
            emit("ui", "orb:name", extra={"name": name})
            if ingest:
                await persist_rename(name)
            return RENAME
        if v in (NAME_ONLY, ALWAYS):
            mode = "smart" if v == NAME_ONLY else "always"
            if ingest:
                await persist_attention_mode(mode)
            emit("brain", "🎙️ modo de atención cambiado por voz", text=mode, role="system", extra={"mode": mode})
            emit("ui", "orb:attention", extra={"state": mode, "src": "voice"})
            return mode
        if (name or "").strip():
            emit("brain", "🏷️ rename not applied: no sure verdict", text=name[:40], role="system",
                 extra={"cat": "flash", "verdict": v})
    except Exception as e:  # noqa: BLE001 — fails closed: nothing renamed
        logger.warning(f"identity: not applied — {type(e).__name__}: {e}")
    return ""
