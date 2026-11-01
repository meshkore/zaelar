"""nucleo/acts/fill.py — how an EMPTY card is filled, as the card DECLARES it (V2-832).

A card whose content only a search brings (the picture viewer, the video catalogue) says so in its manifest:

    "fill": {"tool": "<turn tool>", "filled_by": "<view field>"}            — a turn tool fills it
    "fill": {"action": "<its action>", "key": "<payload key>", "filled_by": "<view field>"}   — its own search

It is EMPTY while its view (`truth.widget_view`, the instance the turn is on) has no truthy `filled_by`. This is the
one reader; the engine never names a card to know any of it, so a third card gets the behaviour by declaring it.
"""
from __future__ import annotations

from loguru import logger


def _base(card: str) -> str:
    return str(card or "").split("::", 1)[0].strip().lower()


def declared(card: str) -> dict:
    """The card's `fill` declaration ({} when it declares none)."""
    try:
        from widgets import runtime
        got = (runtime.get(_base(card)) or {}).get("fill")
        return dict(got) if isinstance(got, dict) else {}
    except Exception as e:  # noqa: BLE001 — an unreadable manifest declares nothing
        logger.debug(f"fill: {card} unreadable — {e!r}")
        return {}


def tool_of(card: str) -> str:
    """The turn tool that fills the card, or ""."""
    return str(declared(card).get("tool") or "")


def search_of(card: str) -> tuple[str, str] | None:
    """`(action, payload key)` of the card's own search that fills it, or None."""
    d = declared(card)
    return (str(d["action"]), str(d.get("key") or "query")) if d.get("action") else None


def is_empty(card: str) -> bool:
    """Does THIS card (the instance) hold nothing its declaration fills? False for an undeclared or unreadable card."""
    field = str(declared(card).get("filled_by") or "")
    if not field:
        return False
    try:
        from nucleo import truth
        view = truth.widget_view(card)
    except Exception as e:  # noqa: BLE001 — unreadable: not empty, nothing is fired on a guess
        return bool(logger.debug(f"fill: {card} view unreadable — {e!r}"))
    return isinstance(view, dict) and not view.get(field)
