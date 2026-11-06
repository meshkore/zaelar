"""connectors/meshkore/send_gate.py — a cluster message passes the ONE consent door (V2-805).

Before this, the connector's only gate was CONNECTING: once a cluster was joined, every `cluster.send` left with no
reading of his rules at all, so «pregúntame antes de escribir al cluster» reached the model as a sentence and never
the act. Now each message is an act of class `messaging.send_new` on channel `meshkore`, decided by
`nucleo/consent.decide_act` — the same rule, defaults and user rules an email or a WhatsApp reads.

Connecting was his yes to the conversation, so it travels as `his_yes` (the mandate): the class default does not
add a question to every line of a collaboration he opened, and his standing «ask»/«never» for this channel still
stop it. Asked → ONE pending row in the shared confirmation registry (`widgets/confirm.py`, the Clusters tab's
reserved id), resolved by a «yes» in any channel through `confirmed_tag` — the voice/chat resolver and the tab's
button call that same function. Refused → not sent, and said.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.meshkore.send_gate")

CLASS, CHANNEL = "messaging.send_new", "meshkore"
#: The declared effect of a held cluster send: it LEAVES the machine (`widgets.confirm._leaves` reads it).
EFFECTS = ["external.send"]


def verdict() -> dict:
    """The one consent rule for a cluster message on a connected cluster (his yes to connect is the mandate)."""
    from nucleo import consent
    return consent.decide_act(CLASS, channel=CHANNEL, his_yes=True)


def gate(name: str, to, text: str, media=None) -> str:
    """'send' | 'held' | 'refused'. Held = one pending row his «yes» (any channel) releases. Never raises: an
    unreadable rule HOLDS — a message to an outside agent is not the direction to fail open in."""
    from nucleo import consent
    try:
        v = verdict()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"send_gate: consent unreadable ({e}) — the message is held for his word")
        v = {"verdict": consent.ASK_CONSENT}
    if not consent.asks(v):
        return "send"
    if v.get("verdict") == consent.REFUSE:
        _emit(f"🚫 {name}·{to or '*'}: his rule forbids this send — not sent", name, to)
        return "refused"
    try:
        from widgets import confirm as _wconfirm
        q = f"¿Mando al cluster «{name}»{(' a ' + str(to)) if to else ''}: «{str(text or '')[:140]}»?"
        op = {"action": "cluster_send", "effects": EFFECTS, "payload": {"name": name, "to": to, "text": text, "media": media}}
        # V2-857 phase 3: the held send waits on a ROW through the one asker; in memory only when no row could open
        from nucleo.request import consent_ask as _ca
        row, _ask_id = _ca.ask_consent(_wconfirm.NATIVE_CLUSTERS, "cluster", {}, q, text=f"{name}: {text or ''}"[:200],
                                       kind="cluster", op=op)
        if not row:
            _wconfirm.request("data", _wconfirm.NATIVE_CLUSTERS, q, op=op)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"send_gate: could not hold the send ({e}) — not sent")
        return "refused"
    _emit(f"✋ {name}·{to or '*'}: held for his word ({v.get('why') or 'his rule'})", name, to)
    return "held"


def confirmed_tag(op: dict) -> tuple[str, dict] | None:
    """The tag a CONFIRMED pending cluster row runs, or None when the op is not a cluster one — the ONE reader the
    voice/chat resolver and the Clusters tab's button share, so a yes from any of them does the same thing."""
    op = op if isinstance(op, dict) else {}
    pl = op.get("payload") or {}
    if op.get("action") == "connect_cluster":
        return "cluster.connect", {"data": pl}
    if op.get("action") == "cluster_send":
        data = {k: pl[k] for k in ("to", "text", "media") if pl.get(k)}
        return "cluster.send", {"name": pl.get("name") or "", "data": data, "confirmed": True}
    return None


def _emit(label: str, name: str, to) -> None:
    try:
        from voice.observer import emit
        emit("cluster", label, extra={"cluster": name, "to": to or "*", "dir": "out"})
    except Exception as e:  # noqa: BLE001
        logger.info(f"send_gate: emit failed ({e})")
