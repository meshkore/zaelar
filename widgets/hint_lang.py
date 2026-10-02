"""widgets/hint_lang.py — the language a reference HINT is written in (V2-778 F3-30, 2026-10-02).

A `ref_index` row's `hint` is read twice: by the brain (the menus `widgets/refs.py` builds) and ALOUD — after an
edit, `nucleo/flash/widget_data_turn.named_ack` says «Done. Right now it holds: «label (hint)» …». Every widget
wrote its hints in Spanish whatever the agent spoke, and an English agent said «(cita … · todos los miércoles hasta
el …)» live. One question, asked the same way by every widget: does the agent speak English now?
"""
from __future__ import annotations


def en() -> bool:
    """True when the agent's current language is English; Spanish (the default) when it cannot be read."""
    try:
        from i18n.langs import current_language
        return str(getattr(current_language(), "code", "") or "es")[:2] == "en"
    except Exception:  # noqa: BLE001
        return False


def pick(es: str, en_: str) -> str:
    """The hint word in the agent's language."""
    return en_ if en() else es
