"""nucleo/flash/done_backing.py — «Done.» is a claim about the screen, checked against it (2026-10-14).

Measured in `docs-single-recipe-not-a-list__us` (sandbox 20261014-120418-en). The recipe was owed on the document
sheet — an end state the turn itself opened («documento.empty» = false) and re-read every five seconds as UNMET.
He answered «just the recipe is fine, no need to build anything» to the build question; that «no» resolved the gate,
and the canned acknowledgement for a resolved «no» said «Done.» over an empty sheet. He had to ask «can you paste
it here? not seeing it».

A bare «Done.» on a turn that wrote to a card, or that answered a confirmation, stands only when no end state owed
on the cards it is about is still unmet now, and when no errand the turn just started is still running. Otherwise
the line says what is true. A reply with any content of its own is left as the model wrote it.
"""
from __future__ import annotations

import re
import unicodedata

_ACTIONS = ("widget_data", "confirm_task_no")


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or "").lower())
    return " ".join(re.findall(r"\w+", "".join(c for c in s if not unicodedata.combining(c))))


def unmet(cards: set[str] | None = None) -> dict | None:
    """The first end state still owed on `cards` (any card when None) that the product reads as NOT met now."""
    from nucleo import spec, verify
    for e in spec.open_specs():
        card = str(e.get("target") or "").split(":", 1)[0]
        if card in ("", "desktop", "canvas") or (cards is not None and card not in cards):
            continue
        if verify.check(e.get("done_when")) is False:
            return e
    return None


def backed(spoken, action: str, extra) -> str:
    """`spoken`, or the true line when it is a bare «Done.» the screen does not back."""
    if action not in _ACTIONS or not isinstance(spoken, str) or not spoken.strip():
        return spoken
    from i18n import langs as _langs
    lang = _langs.current_language()
    if _fold(spoken) != _fold(lang.data_ack):
        return spoken
    extra = extra if isinstance(extra, dict) else {}
    if any(extra.get("beside") or []):
        return lang.done_just_started
    cards = ({str(op.get("widget") or "").split("::", 1)[0] for op in extra.get("ops") or [] if isinstance(op, dict)}
             if action == "widget_data" else None)
    return lang.done_not_on_card if unmet(cards) else spoken
