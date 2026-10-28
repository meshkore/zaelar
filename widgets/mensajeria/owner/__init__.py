#
# owner/: live backend for the messaging widget (V2-008, kind:"backed", gate:"nucleo"). Connectors publish incoming
# messages (connector.msg) and link status (connector.status) to the bus; this owner triages them with a LOCAL model,
# dumps durable content to memory, notifies only what deserves it and reflects everything into the UI store. It is
# the ONLY WRITER of widgets/_data/mensajeria/; data.py/widget.js are read + enqueue faces, and actions arrive
# through the supervisor mailbox -> handle().
#
# Orders to the apps (mark read, send, archive…) go out only as bus events the right connector executes: the owner
# knows the bus, never WhatsApp or Telegram. Without BRAIN=nucleo (manifest gate) the owner does not run and the
# widget behaves as the passive version (actions fall to data.apply_action).
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
