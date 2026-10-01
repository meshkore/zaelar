"""One scrubber for what leaves the machine or lands in a file beside the timeline (V2-778 F4-37, 2026-10-01).

Two passes, both deterministic: the vault's detector (`memory.secrets.redact` — a password, a card, a code said
aloud becomes «secreto guardado») and the token shapes the cluster channel already masks (`connectors.meshkore.
store.redact` — API keys, JWTs, bearer tokens, live cluster tokens). If scrubbing itself fails the text is
WITHHELD, never passed through: the point of this function is that nothing unscrubbed gets out by accident.
"""
from __future__ import annotations

from loguru import logger

WITHHELD = "[withheld: the scrubber failed]"


def scrub(text):
    """`text` with personal secrets and token-shaped values masked; non-strings are returned untouched."""
    if not isinstance(text, str) or not text:
        return text
    try:
        from connectors.meshkore import store as _tokens
        from memory import api as _memapi
        return _tokens.redact(_memapi.redact_secrets(text))
    except Exception as e:  # noqa: BLE001 — withheld, and said: never an unscrubbed line by accident
        logger.warning(f"scrub: could not scrub a text, withheld it: {e!r}")
        return WITHHELD


def scrub_obj(obj):
    """Every string inside a JSON-shaped value, scrubbed (dict keys are left alone: they are our field names)."""
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, dict):
        return {k: scrub_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub_obj(v) for v in obj]
    return obj
