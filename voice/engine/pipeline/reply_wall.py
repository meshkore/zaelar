"""reply_wall.py — the reply reaches the wall even when the voice cannot (V2-773, 2026-09-27).

Measured on the operator's engine with Inworld out of credits (a 402 on every synthesis): the model answered
«I'm on a deep search for three 27-inch 4K monitors…», LiveKit retried the TTS, gave up (`tts_error`,
recoverable=False) and never added the assistant item to the conversation — and the assistant transcript is
emitted from `conversation_item_added`. The chat wall stayed blank while a worker started; the operator saw
the errand and never the answer. The text was ready the whole time: it is what `tts_node` was fed.

The tee remembers what the current speech is fed; when the session reports an unrecoverable TTS error, that
text is surfaced as the transcript it would have been, marked `tts_failed`. If LiveKit still adds the item
afterwards, `already_surfaced` keeps the wall from painting it twice. A voice provider without credit is a
voice problem; it must never be a text problem too.
"""
from __future__ import annotations

import time

_REPEAT_S = 60.0                  # the same text again inside this window is the same reply
_cur: dict = {"parts": [], "t": 0.0}
_shown: dict = {"text": "", "t": 0.0}


def tee(text):
    """Remember what a speech is fed — a str or a stream of str — and hand it on unchanged."""
    _cur["parts"], _cur["t"] = [], time.time()
    if isinstance(text, str):
        _cur["parts"].append(text)
        return text

    async def _gen():
        async for chunk in text:
            _cur["parts"].append(str(chunk))
            yield chunk
    return _gen()


def pending_text() -> str:
    return "".join(_cur["parts"]).strip()


def is_tts_dead(error) -> bool:
    """LiveKit's session error for a synthesis it has given up on (its retries are `recoverable=True`)."""
    return (str(getattr(error, "type", "") or "") == "tts_error"
            and getattr(error, "recoverable", True) is False)


def surface(emit) -> str:
    """Emit the pending reply as the assistant transcript it would have been. Returns it, or '' when there
    is nothing new to show."""
    t = pending_text()
    if not t or already_surfaced(t):
        return ""
    _shown["text"], _shown["t"] = t, time.time()
    emit("transcript", "zaelar", text=t, role="assistant", extra={"tts_failed": True})
    return t


def already_surfaced(text) -> bool:
    t = str(text or "").strip()
    return bool(t) and t == _shown["text"] and (time.time() - _shown["t"]) < _REPEAT_S
