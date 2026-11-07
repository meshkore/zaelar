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


def fold_concepts(group_fn) -> dict:
    """V2-858 T549 — fold the concept hubs that mean the same into one (`memory/concepts.fold_pass`). `group_fn` is
    the brain's: `names -> [[name, …], …]`, or None when it cannot answer (nothing is folded)."""
    from .. import concepts as _concepts
    from .. import db as _db
    from ..consolidator import _kv_get, _kv_set, _now
    return _concepts.fold_pass(_db.get_db(), group_fn, _now(), kv_get=_kv_get, kv_set=_kv_set)


def concept_names(limit: int = 40) -> list[str]:
    """The canonical hubs the distiller should reuse, most-used first (the prompt's open-vocabulary anchor)."""
    from .. import concepts as _concepts
    from .. import db as _db
    return [h["name"] for h in _concepts.hubs(_db.get_db())[:limit]]
