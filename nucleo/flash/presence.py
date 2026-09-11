"""The PRESENCE knock, as vocabulary + the probe channel's mirror (V2-640).

«¿Sigues ahí?» is a knock on the door, not a task. The DETECTOR lives here — in nucleo, the neutral ground —
so both channels read the same words: the voice lane (`voice/.../fast_lane.presence`, which owns speaking)
imports it downward, and the probe channel calls `mirror()` below (parallel impl, V2-539's rule: wire BOTH
channels or the probe hands out verdicts the product never gives). The voice-side vocabulary (`langs.spec`)
is INJECTED by the caller, never imported: the dependency-direction ratchet (7.32) refused probe modules
reaching into `voice.engine.core`, and it was right — see `probe_actionmap.py`'s docstring.
"""
from __future__ import annotations

import re
import unicodedata

_PRESENCE_BODY_RE = re.compile(
    r"^(?:oye |hola |hey |eh )?(?:"
    r"(?:sigues|estas) (?:ahi|por ahi|conmigo)(?: o no| o que)?"
    r"|me (?:oyes|escuchas|recibes)(?: bien)?(?: o no)?"
    r"|hay alguien(?: ahi)?"
    r"|(?:estas|sigues) (?:disponible|operativo|conectado|despierto|vivo)(?: o no)?"
    r"|estas(?: ahi)?"
    r"|are you (?:there|still there|listening|awake|alive|okay|with me)"
    r"|can you hear me"
    r"|(?:you )?still there"
    r"|anybody there"
    r")$")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[¿?¡!.,;:]+", " ", t)).strip()


def is_presence_check(text: str, assistant_name: str = "") -> bool:
    """True only when the WHOLE utterance is a presence knock (≤7 words). A leading vocative — the
    assistant's own name, «oye» — is stripped first (V2-635's lesson: a leading name must not hide a known
    phrase); any other content means a real turn and falls through to the model."""
    n = _norm(text)
    if not n or len(n.split()) > 7:
        return False
    for name in sorted({x for x in ({_norm(assistant_name)} | set(assistant_names())) if x},
                       key=len, reverse=True):
        if n.startswith(name + " "):
            n = n[len(name):].strip()
            break
        if n == name:
            return False                  # a bare call by name is a summons — `is_summons` below owns it
    return bool(_PRESENCE_BODY_RE.match(n))


# A bare call by NAME is an address, not a request — it opens the window and asks for attention, and the only
# honest answer is «dime». V2-665, session e82f7fcb (2026-09-11): «Johnny.» alone reached the model with a
# memory pill about a video he had asked for the night before still in the window, and the model ANSWERED «Voy
# a buscar el vídeo del Apolo 11» and fired a `widget_data` search on his behalf — inventing a request out of
# a summons. Six seconds later a second bare «Johnny.» got «Dime, Ricardo.», which is the right answer: the
# most frequent utterance in wake-word mode was non-deterministic, and half the time it acted. Now it never
# reaches a model and never reaches a tool.
_SUMMONS_LEAD_RE = re.compile(r"^(?:oye|hey|eh|hola|perdona|oiga)\s+")
_SUMMONS_TAIL_RE = re.compile(r"\s+(?:por favor|porfa|please)$")


def assistant_names() -> tuple[str, ...]:
    """Every word that counts as HIS NAME, normalized — the wake words the attention gate actually uses.

    ⚠️ Measured while building V2-665 and it is a defect OLDER than this batch: both callers of
    `is_presence_check` read `config.settings.get("assistant_name")`, and **that key is never written**.
    A rename lands in MEMORY state (`memory.state()["assistant_name"]`) and is pushed into `voice.attention`
    by `memory_cache`; the settings file has held `None` the whole time. So the vocative strip that lets
    «Johnny, ¿sigues ahí?» be recognised has been dead for a renamed assistant since V2-640 shipped, and the
    summons check would have been born dead the same way. One source now, and it is the one the gate itself
    consults — anything else is a second opinion that drifts.
    """
    try:
        from voice import attention
        ws = tuple(n for n in (_norm(w) for w in attention.wakewords()) if n)
        if ws:
            return ws
    except Exception:  # noqa: BLE001 — the probe may run with no voice engine at all
        pass
    return ("zaelar",)


def is_summons(text: str, assistant_name: str = "") -> bool:
    """True when the WHOLE utterance is the assistant's name and nothing else (a leading interjection and a
    trailing courtesy are allowed — they carry no request either). Anything after the name is a real turn."""
    n = _norm(text)
    if not n:
        return False
    n = _SUMMONS_TAIL_RE.sub("", _SUMMONS_LEAD_RE.sub("", n)).strip()
    if not n:
        return False
    names = {x for x in ({_norm(assistant_name)} | set(assistant_names())) if x}
    return n in names


def mirror(text: str, sess, trace_id: str, spec) -> dict | None:
    """The PROBE channel's answer to a presence knock — the finished response dict, or None to fall through.
    Deterministic twin of the voice lane: first phrase of the honest pool (busy vs idle), the exchange lands
    in the window (the V2-605 canned-line lesson), and `action: "presence"` says no model resolved it."""
    try:
        aname = ""                      # `assistant_names()` is the authority; this stays for an explicit caller
        if not (is_presence_check(text, aname) or is_summons(text, aname)):
            return None
        busy = False
        try:
            from nucleo import dispatch
            busy = dispatch.has_active()
        except Exception:
            pass
        pool = list(getattr(spec(), "presence_busy" if busy else "presence_idle", ()) or ())
        if not pool:
            return None
        phrase = pool[0]
        from nucleo.flash import dialog
        dialog.push_user(sess.window, text)
        sess.window.append({"role": "assistant", "content": phrase})
        return {"ok": True, "reply": [phrase], "action": "presence", "tool_calls": [], "tags": [],
                "trace": trace_id}
    except Exception:
        return None
