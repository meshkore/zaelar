#
# owner/: live backend for the messaging widget (V2-008, kind:"backed", gate:"nucleo"). This closes the v2
# central-diagram reshape: connectors (WhatsApp/Telegram) publish incoming messages to the bus (connector.msg) and
# their link status (connector.status); this owner consumes them, triages with its internal agent (LOCAL model,
# privacy), dumps durable content to central memory, proactively notifies only relevant items, and reflects
# everything into the widget UI store. It is the ONLY WRITER of widgets/_data/mensajeria/ (backed contract:
# data.py/widget.js become read + enqueue faces; operator/brain actions arrive through the supervisor mailbox ->
# handle()).
#
# Mark-read is symmetrical: a read/clear/readchat action does NOT talk to any app directly. It publishes
# msg.mark_read to the bus, which the connector for the correct platform drains and executes in its app. The owner
# does not know WhatsApp or Telegram, only the bus. Connectors are genuinely stateless.
#
# STRANGLER-FIG: the supervisor only starts this owner with BRAIN=nucleo (manifest gate). Under duo/hermes, the
# widget behaves as the previous passive version (owner does NOT run -> actions fall to data.apply_action and
# connectors write the store through their direct path). Zero regression until burial (V2-009).
#
# The owner lives by concern: `lifecycle` (subscriptions, start/stop, the beat), `apply` (what the bus brought,
# triage, autoresponder), `handle` (the action door and the queue flush) and `seams` (the small doors they share).
# `_Owner` is composed here from those mixins; every name a test imports or patches stays reachable on this module.
#
import os

from loguru import logger  # noqa: F401

# Re-exported on purpose: tests reach `owner.msgstore` / `owner.ingest` to patch what the owner calls.
from connectors.messaging import config as msgcfg  # noqa: F401
from connectors.messaging import ingest, notify  # noqa: F401
from connectors.messaging import store as msgstore  # noqa: F401

_LABEL = {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "Email"}
_BATCH = float(os.getenv("MSG_TRIAGE_BATCH", "2.0"))   # seconds between triage batches; groups bursts into one call

from .seams import _note, _scrub, _origin, _settle, _record_left  # noqa: E402,F401
from .lifecycle import _Lifecycle  # noqa: E402
from .apply import _Apply  # noqa: E402
from .handle import _Handle  # noqa: E402


class _Owner(_Lifecycle, _Apply, _Handle):
    """Owner of the messaging widget. Lifecycle governed by widgets/supervisor.py (start/stop/handle + restart)."""


# Single instance governed by the supervisor (contract: async start()/stop()/handle(action,payload)).
_OWNER = _Owner()


async def start() -> None:
    await _OWNER.start()


async def stop() -> None:
    await _OWNER.stop()


async def handle(action: str, payload: dict) -> None:
    await _OWNER.handle(action, payload)
