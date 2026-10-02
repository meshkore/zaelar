"""nucleo/flash/reply_promise.py — did the REPLY promise an act, or music? Read by a verdict (V2-778 F2-16, 2026-10-02).

The question opens the promise backstops and the act repair (`router_guards.promises_action`, `promises_music`,
`playback_promise.promises_playback`). It was answered by phrase tables in Spanish and English only — blind in every
other language the engine speaks, a verb table posing as a router (V2-750). The operator's decision (2026-10-02):
ask the verdict on EVERY spoken reply.

How: each channel calls `prefetch(reply, operator_text)` ONCE, when the reply is final and before the lanes that read
it, through Jev's NON-blocking door (`ask_many`, the turn brief's own) and waited for without blocking the loop
(one question, ~300 ms, after the words were already streamed). The answer is cached by
the reply's normalised text, so every reader of this turn — whatever string slice of the reply it holds — gets the
same verdict without asking again. `verdict(reply)` returns "act" / "music" / "none" when the verdict is SURE, and
None otherwise: then the tables decide, exactly as before — they are the proposal, never removed.
"""
from __future__ import annotations

import re
import time
import unicodedata

CHOICES = {
    "act": "promises to do a task now: «I'll send it», «sending it now», «lo mando», «je l'envoie», «ich schicke es»",
    "music": "promises to play music now: «putting on X», «te pongo X», «je mets X», «ich lege X auf», «metto su X»",
    "none": "no promise: an answer, a fact, a question, a refusal («I can't», «no puedo»), or a REPORT that it is "
            "already done («Done», «Hecho», «ya está», «C'est fait», «Fatto», «Erledigt», «Pronto, já enviei»)",
}
INSTRUCTIONS = ("Classify the assistant's REPLY (any language). The operator's request is context only. "
                "Choose act if the reply promises to carry out a task (future or in progress), music if it promises to play "
                "music, none otherwise. A refusal, a negated action, or a report of something ALREADY done is none.")
TTL_S = 120.0
_CACHE: dict[str, tuple[str, float]] = {}
_MAX = 64


def _key(reply) -> str:
    t = re.sub(r"\[\[[^\]]*\]\]", " ", str(reply or ""))           # inline tags are not words
    t = unicodedata.normalize("NFKC", t).lower()
    return " ".join(t.split())[:600]


def reset() -> None:
    _CACHE.clear()


def _remember(k: str, choice: str) -> None:
    _CACHE[k] = (choice, time.time())
    if len(_CACHE) > _MAX:
        for old in sorted(_CACHE, key=lambda x: _CACHE[x][1])[: len(_CACHE) - _MAX]:
            _CACHE.pop(old, None)


def _ask(reply, operator_text: str):
    """Fire the question through `jev.ask_many` — never `choose_sync`, which blocks its thread on the network and is
    frozen by `test_no_new_blocking_jev_call`."""
    from nucleo import jev
    state = f"REPLY: {str(reply)[:500]}\nOperator said: {str(operator_text or '')[:160]}"
    return jev.ask_many(state, {"reply_promise": {"instructions": INSTRUCTIONS, "criteria": CHOICES}},
                        name="reply-promise", question_id="reply_promise")


def _settle(k: str, handle) -> str | None:
    from nucleo import jev
    choice, _info = jev.read(handle, "reply_promise", "")
    choice = choice if choice in CHOICES else ""
    _remember(k, choice)
    return choice or None


WAIT_S = 1.5


async def prefetch(reply, operator_text: str = "") -> None:
    """Ask once when the reply is final and wait WITHOUT blocking the loop (≤ `WAIT_S`), so every reader of this turn
    finds the verdict cached. A verdict that does not arrive in time leaves the tables to decide."""
    k = _key(reply)
    if not k or k in _CACHE:
        return
    try:
        import asyncio
        handle = _ask(reply, operator_text)
        if not handle:
            return
        t0 = time.monotonic()
        while not handle["event"].is_set() and time.monotonic() - t0 < WAIT_S:
            await asyncio.sleep(0.02)
        _settle(k, handle)
    except Exception:  # noqa: BLE001 — a classifier never breaks a turn
        return


def read_now(reply, operator_text: str = "") -> str | None:
    """The same question, waited for on THIS thread — for tests and manual probes, never on the event loop."""
    k = _key(reply)
    if not k:
        return None
    hit = _CACHE.get(k)
    if hit and time.time() - hit[1] < TTL_S:
        return hit[0] or None
    try:
        handle = _ask(reply, operator_text)
        if not handle:
            _remember(k, "")
            return None
        handle["event"].wait(WAIT_S)
        return _settle(k, handle)
    except Exception:  # noqa: BLE001
        _remember(k, "")
        return None


def verdict(reply) -> str | None:
    """The SURE verdict for this reply ("act" / "music" / "none"), or None — then the tables decide."""
    hit = _CACHE.get(_key(reply))
    if not hit or time.time() - hit[1] >= TTL_S or not hit[0]:
        return None
    return hit[0]


# ── the questions the phrase tables answered, verdict first ─────────────────────────────────────────────────
# Wrappers rather than edits: `router_guards` is a god file under the architecture ratchet, so the verdict is read
# here and `router` re-exports these under the old names — every caller keeps its import.

def promises_action(reply: str) -> bool:
    v = verdict(reply)
    if v is not None:
        return v in ("act", "music")
    from nucleo.flash import router_guards as _rg
    return _rg.promises_action(reply)


def promises_music(reply: str) -> bool:
    v = verdict(reply)
    if v is not None:
        return v == "music"
    from nucleo.flash import router_guards as _rg
    return _rg.promises_music(reply)
