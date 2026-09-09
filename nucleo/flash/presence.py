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
    name = _norm(assistant_name)
    if name and n.startswith(name + " "):
        n = n[len(name):].strip()
    elif name and n == name:
        return False                      # a bare call by name is a summons, not a presence question
    return bool(_PRESENCE_BODY_RE.match(n))


def mirror(text: str, sess, trace_id: str, spec) -> dict | None:
    """The PROBE channel's answer to a presence knock — the finished response dict, or None to fall through.
    Deterministic twin of the voice lane: first phrase of the honest pool (busy vs idle), the exchange lands
    in the window (the V2-605 canned-line lesson), and `action: "presence"` says no model resolved it."""
    try:
        try:
            from config.settings import get as _sget
            aname = str(_sget("assistant_name") or "")
        except Exception:
            aname = ""
        if not is_presence_check(text, aname):
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
