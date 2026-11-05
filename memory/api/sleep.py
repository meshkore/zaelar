"""The sleep's doors for a higher layer (V2-854 F3): memory imports no brain, so a brain that has deep-sleep work of
its own registers it here, and reads the pure rules the sleep owns through here."""
from __future__ import annotations


def register_sleep_phase(name: str, fn) -> None:
    """Run `fn()` in every deep sleep (REM), isolated like its own phases; its report lands under `name`."""
    from .. import rem
    rem.register(name, fn)


def same_person_records(contacts: list[dict]) -> dict:
    """REM's rule for one person's address-book records: `{links, proposals}` (`memory/rem/contacts.py`)."""
    from ..rem import contacts as _rule
    return _rule.same_person(contacts)
