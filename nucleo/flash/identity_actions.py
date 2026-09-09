"""nucleo/flash/identity_actions.py — a rename and the attention-mode toggle, both riding `set_style_directive`.

Two things measured live in session a9b3a813 (2026-09-09): (1) the operator renamed zaelar to "Johnny" via
`set_style_directive` — the tool worked as designed, storing "El asistente debe llamarse Johnny" as one more
line in `state.rules` alongside every other behaviour preference, with nothing to say WHOSE name is whose; three
turns later the model addressed the OPERATOR as "Cuéntame, Johnny." (2) the operator's wake-word ("solo escúchame
si dices tu nombre") kept failing after the rename because `voice/attention.py`'s wake-word list was still
hardcoded to "zaelar" — nothing had ever wired a rename to it.

Neither is a free-text preference: a rename is a STRUCTURED fact (`state.assistant_name`, declared since V2-002
and never once written) and the attention mode is a CONFIGURED setting (`config/settings.py`, the same one the
orb's 🤖 button writes). Both are detected here, on the model's OWN paraphrase in `directive` — narrower and far
more predictable than free operator speech, the trade `router_guards.looks_like_rule_removal` already makes —
and BOTH channels (voice `nucleo.py`, text `probe.py`) call `resolve()` + the matching `persist_*` instead of
duplicating the regex/DB-write pair twice (the V2-108 lesson: a parallel implementation that only one channel
gets is a parallel implementation that quietly stops working the day only that one is touched).

No new tool: the router catalog had 12 chars of headroom (23088/23100,
`tests/agent_headless/unit/flash/test_router.py::test_tool_catalog_stays_compact`) — nowhere near a new tool's
declaration, so this rides the existing `set_style_directive` catalog entry ("cómo tratarle o responder de ahora
en adelante" already covers both asks in spirit) instead of raising that ceiling.
"""
from __future__ import annotations

import asyncio
import re as _re

from .text_norm import _norm_txt

_NAME_CHANGE_RE = _re.compile(
    r"(?:el asistente(?: (?:se|debe|deber[ií]a) llamarse| se llama)|"
    r"(?:te|tu) llamas|ll[aá]mate|tu nombre (?:ahora )?es|"
    r"cambia(?:te)? (?:tu )?nombre a|"
    r"the assistant(?: should| must)?(?: be)? (?:called|named)|the assistant('?s| is) name is|"
    r"you(?:'re| are)(?: now)? call(?:ed)?|your name is|call yourself)"
    r"\s+(.+)$",
    _re.IGNORECASE,
)


def extract_name_change(directive: str) -> str | None:
    """"Johnny" from "El asistente debe llamarse Johnny" / "llámate Colmena" / "your name is Nova"; else None."""
    d = (directive or "").strip()
    if not d:
        return None
    m = _NAME_CHANGE_RE.search(d)
    if not m:
        return None
    name = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
    name = (name or "").strip(" .!?\"'“”«»").strip()
    name = _re.split(r"[,;]|\by\b|\band\b", name, maxsplit=1)[0].strip()   # a trailing clause is not the name
    return name or None


# Word-CLASSES ANDed together (same idiom as `router_guards.looks_like_modify_widget`), not a phrase chain —
# the directive's grammatical person varies ("el asistente debe escuchar solo si le llaman", "escúchame solo
# si dices mi nombre"). "respond" verbs joined 2026-09-09: measured in session 76bd0bb5, the model's paraphrase
# was "Solo RESPONDER cuando el operador diga el nombre del asistente" — listen-only word classes missed it, so
# the directive fell through to the free-text-rule branch and the mode never changed by voice.
_ATT_LISTEN_RE = _re.compile(r"\bescuch\w+\b|\blisten\w*\b|\brespond\w*\b|\bcontest\w*\b|\banswer\w*\b|\breply\w*\b",
                             _re.IGNORECASE)
_ATT_NAME_RE = _re.compile(r"\bnombre\b|\bllam\w+\b|\bname\b|\bcalled\b", _re.IGNORECASE)
_ATT_ONLY_RE = _re.compile(r"\bsolo\b|\bonly\b", _re.IGNORECASE)
_ATT_ALWAYS_RE = _re.compile(r"\bsiempre\b|\btodo\s+el\s+rato\b|\balways\b", _re.IGNORECASE)
# The mode's PRODUCT name is "Modo Wake Word" (operator decision 2026-09-09 — the wake word IS the assistant's
# current name, always). "wakeworld" is the STT's own garble of it, measured verbatim in session 8a07e8d9.
_ATT_MODE_NAME_RE = _re.compile(
    r"\bwake\s*-?\s*wor\w*\b|\bpalabra\s+(?:de\s+)?activacion\b|\bmodo\b[^.]{0,40}\bpalabra\s+clave\b|"
    r"\bmodo\s+nombre\b|\bname[\s-]only\s+mode\b",
    _re.IGNORECASE)
_ATT_OFF_RE = _re.compile(r"\bdesactiv\w*\b|\bquita\w*\b|\bdeja\s+de\b|\bapaga\w*\b|\bturn\s+off\b|\bdisable\w*\b",
                          _re.IGNORECASE)
_ATT_ON_RE = _re.compile(r"\bactiv\w*\b|\benciend\w*\b|\bturn\s+on\b|\benable\w*\b", _re.IGNORECASE)


def extract_attention_mode_change(directive: str) -> str | None:
    """"always" | "name_only" | None."""
    d = _norm_txt(directive or "")
    if not d:
        return None
    if _ATT_MODE_NAME_RE.search(d):
        return "always" if _ATT_OFF_RE.search(d) else "name_only"
    if _ATT_LISTEN_RE.search(d) and _ATT_NAME_RE.search(d) and _ATT_ONLY_RE.search(d) and not _ATT_OFF_RE.search(d):
        return "name_only"
    if _ATT_LISTEN_RE.search(d) and _ATT_ALWAYS_RE.search(d) and not _ATT_ON_RE.search(d):
        return "always"
    return None


def resolve(directive: str) -> tuple[str, str] | None:
    """`("rename", "Johnny")` | `("attention", "smart"|"always")` | None. The attention value is already
    mapped to `voice.attention`'s own vocabulary — "name_only" (product-facing: wake-word OR an active
    conversation window, so the operator says the name once and keeps talking through short pauses) means
    `smart`, never raw `wakeword` (which re-demands the name every utterance with no window — measured live
    the same session: even correctly named, that mode would have kept failing on turn 2). Callers never
    juggle the product label."""
    name = extract_name_change(directive)
    if name:
        return ("rename", name)
    att = extract_attention_mode_change(directive)
    if att:
        return ("attention", "smart" if att == "name_only" else "always")
    return None


def apply_rename_now(name: str) -> None:
    """Immediate, PROCESS-level: the session's wake-word tracks the new name at once, before the DB write
    below even starts (mirrors `brain._directive = directive`'s immediate layer for ordinary style rules)."""
    from voice import attention
    attention.set_assistant_name(name)


async def persist_rename(name: str) -> None:
    from memory import api as _mem
    await asyncio.to_thread(_mem.set_state, {"assistant_name": name})


async def persist_attention_mode(mode_val: str) -> None:
    from config import settings as _cfg
    await asyncio.to_thread(_cfg.update, {"attention_mode": mode_val})


def handle_voice(directive: str, emit, spawn) -> bool:
    """VOICE channel (`nucleo.py`'s `_on_tool_call`): fire-and-forget persistence via the caller's own
    `spawn(coro, tag)`. True if `directive` was a rename/attention-mode change (already applied)."""
    resolved = resolve(directive)
    if not resolved:
        return False
    kind, val = resolved
    if kind == "rename":
        apply_rename_now(val)
        emit("brain", "🏷️ zaelar se renombra", text=val, role="system")
        emit("ui", "orb:name", extra={"name": val})   # the 🤖 tooltip reflects it live, no reload
        spawn(persist_rename(val), "assistant-rename")
    else:
        from config import settings as _cfg
        _cfg.update({"attention_mode": val})
        emit("brain", "🎙️ modo de atención cambiado por voz", text=val, role="system", extra={"mode": val})
        emit("ui", "orb:attention", extra={"state": val, "src": "voice"})
    return True


async def handle_probe(directive: str, *, ingest: bool) -> str | None:
    """PROBE channel (`probe.py`, V2-108's "wire both" lesson): awaited, gated by `ingest` (routing-only
    tests pass `ingest=False`, same convention as every other branch in that file). Returns the action label
    ("rename_assistant"/"attention_mode") or None if `directive` was neither."""
    resolved = resolve(directive)
    if not resolved:
        return None
    kind, val = resolved
    if ingest:
        if kind == "rename":
            apply_rename_now(val)
            await persist_rename(val)
        else:
            await persist_attention_mode(val)
    return "rename_assistant" if kind == "rename" else "attention_mode"
