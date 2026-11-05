"""nucleo/acts/message_channel.py — the channel HE named reaches the send door (V2-851 F2c, battery C6).

Measured (battery C6, «send Lucía a WhatsApp…», Lucía has Telegram and mail, no WhatsApp): in one language the
model's call carried `channel: whatsapp` and the door refused — right; in the other the call carried no channel, the
door read «none named» as «her preferred one» and a Telegram message left the machine. The door can only refuse a
channel it is told: the slot was lost between his words and the call.

The fix is the same rule as `message.his_recipient` (the name «as he said it»): the turn's brief carries one declared
question — which channel does HE name for this message, among the channels the cards declare, or none — and a sure
reading puts that channel in the call of any action that declares a `channel` slot. The door then decides as always
(sends, or refuses «she has no WhatsApp», or asks which channel). His words are never matched here: the brief reads
them in any language, and the choices are the declared platforms.
"""
from __future__ import annotations

KEY = "message_channel"
NONE = "none"

INSTRUCTIONS = ("If the operator's message asks to send or write a message to someone, does HE name the channel it "
                "must go by, in any wording or language (an app, a network, mail)? Pick that channel. Answer 'none' "
                "when he names no channel, or when the message is not about sending one.")


def _platforms() -> tuple:
    try:
        from widgets import directory
        return tuple(directory.PLATFORMS)
    except Exception:  # noqa: BLE001
        return ()


def question(_ctx=None) -> dict:
    """The brief's question: one choice per declared platform, plus `none`."""
    plats = _platforms()
    if not plats:
        return {}
    crit = {p: f"he names {p} as the channel this message goes by" for p in plats}
    crit[NONE] = "he names no channel, or this is not about sending a message"
    return {"instructions": INSTRUCTIONS, "criteria": crit}


def _declares_channel(wid: str, action: str) -> bool:
    try:
        from nucleo.flash import payload_fill
        return "channel" in payload_fill._payload_spec(wid, action)
    except Exception:  # noqa: BLE001
        return False


def his_channel(wid: str, action: str, payload, brief, emit=None):
    """`payload` with `channel` set to the one HE named, when the brief surely read one and the call carries another
    or none. Untouched otherwise (no reading, `none`, a doubt, an action without a channel slot). Never raises."""
    if not isinstance(payload, dict) or not _declares_channel(wid, action):
        return payload
    try:
        from nucleo.turn import verdicts
        choice, _info = verdicts.read(brief, KEY, None)
    except Exception:  # noqa: BLE001
        return payload
    if choice not in _platforms():
        return payload
    got = str(payload.get("channel") or payload.get("platform") or "").strip().lower()
    if got == choice:
        return payload
    if callable(emit):
        emit("brain", "🛑 the channel he named goes back into the send", text=f"{wid}:{action} «{got}» → «{choice}»",
             role="system", extra={"cat": "flash", "id": wid, "model": action, "was": got, "his": choice})
    out = {k: v for k, v in payload.items() if k != "platform"}
    out["channel"] = choice
    return out
