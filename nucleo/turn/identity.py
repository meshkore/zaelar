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
#: The same fact, never consumed: the memory processor reads it to decide whether an `assistant.name` atom it distilled
#: is a rename HE ordered (V2-851 F5 — it used to ask Jev its own question after the reply, `rename_decision`).
_HEARD: dict = {"name": "", "at": 0.0}
#: How long after the turn the memory processor may still read it: the processor runs off the turn, seconds later.
HEARD_S = 600.0


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


def sentences_with(name: str, text: str) -> list[str]:
    """The sentences of `text` that carry `name` (whole word, any case), each on its own — [] when none does."""
    import re
    n = (name or "").strip()
    if not n:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[.!?¡¿;\n])\s+|\n+", str(text or "")) if p.strip()]
    return [p for p in parts if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", p, re.I)]


#: How many of his sentences naming the assistant the narrow verdict reads — a bound, not a tuning: a rename lives in one.
SENTENCES_READ = 3


def sentence_verdict(name: str, text: str) -> str:
    """The identity verdict over the sentences of his turn that carry the name the model declared, at `SURE`; NONE
    otherwise (no such sentence, Jev off, unsure).

    Demo sandbox 2026-11-05, INIT step 1: «Your name is Johnny. When I say "Johnny", I am talking to you. Act as my
    personal digital assistant. Use information you already know…» — the model declared `name="Johnny"` and the brief's
    verdict over the THREE-sentence step read `rename` at 0.21-0.32 (3 of 3), while «Your name is Johnny.» alone reads
    0.96: nothing was stored, the reply said «Johnny it is», and the list counted the step done. A long step dilutes a
    verdict about one of its sentences; the question is asked over the sentence that names him."""
    carry = sentences_with(name, text)
    if not carry or (len(carry) == 1 and carry[0] == str(text or "").strip()):
        return NONE                      # the brief already judged exactly that sentence
    # One sentence at a time: the two carrying sentences of the measured step JOINED still read 0.36 («When I say
    # "Johnny", I am talking to you» is about listening, not naming); «Your name is Johnny.» alone reads 0.96.
    try:
        from nucleo import jev
        q = question()
        for sentence in carry[:SENTENCES_READ]:
            got = jev.choose_sync(KEY, sentence, instructions=q["instructions"], criteria=q["criteria"],
                                  question_id="identity-sentence") or {}
            choice, conf = str(got.get("choice") or ""), float(got.get("confidence") or 0.0)
            if choice == RENAME and conf >= SURE:
                return RENAME            # only the rename: a listening-mode change stays the whole turn's verdict
    except Exception as e:  # noqa: BLE001 — fails closed
        logger.debug(f"identity: sentence verdict unread — {e!r}")
    return NONE


def rename_ordered_since(since: float) -> dict | None:
    """`{"name"}` when a turn's sure verdict ordered a rename at or after `since` (the model's name, maybe ""), once."""
    if _LAST["at"] < since:
        return None
    got = {"name": _LAST["name"]}
    _LAST.update(name="", at=0.0)
    return got


def rename_heard(value: str, *, now: float | None = None) -> bool:
    """Did a turn's SURE verdict order a rename in the last `HEARD_S` — to this name, when the model gave one? The
    read the memory processor makes before it writes `assistant.name` (V2-752's incident: «He dicho, Apollo once»
    renamed him on the distiller's signature alone). No verdict, an old one or another name → False: fails closed."""
    t = time.time() if now is None else now
    if not _HEARD["at"] or t - _HEARD["at"] > HEARD_S:
        return False
    said = " ".join(str(_HEARD["name"] or "").lower().split())
    return not said or said == " ".join(str(value or "").lower().split())


async def settle(brief, name: str, emit, *, ingest: bool = True, text: str = "") -> str:
    """Apply what the brief's identity verdict says, with the model's declared `name`. Returns `rename`, an attention
    value, or "" when nothing changed (the directive is then an ordinary rule). Never raises.

    `text` is HIS sentence of the turn. When the model declared a name and the brief's verdict over the whole turn is
    unsure, the question is asked once more over the sentences that carry that name (`sentence_verdict`): the verdict
    completes the model (CRIT-K2), it never contradicts a name he gave. Still fail-closed: a verdict decides."""
    try:
        v = verdict(brief)
        if v == NONE and (name or "").strip() and (text or "").strip():
            v = await asyncio.to_thread(sentence_verdict, name, text)
        if v == RENAME:
            _LAST.update(name=(name or "").strip()[:32], at=time.time())
            _HEARD.update(name=(name or "").strip()[:32], at=time.time())
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
