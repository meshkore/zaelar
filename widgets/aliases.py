#
# Widget aliases: surgical manifest editing (V2-082, D1 keyword == alias).
#
# Adding an alias by voice or text must NOT regenerate the widget: it is an ATOMIC write to
# `manifest["aliases"]`, sibling to `widget_data` (which touches data) but scoped to IDENTITY. Cheap,
# deterministic, with no headless agent. Collision guard: an alias belongs to exactly one piece (widget or system
# surface), preserving resolver certainty. Lazy migration seeds `aliases` from `name` + `keywords` on first edit
# when the widget does not have the field yet, creating one identity list.
#
from __future__ import annotations

import json
import os
import unicodedata

from widgets import paths

HERE = paths.BUILTIN_ROOT


def _safe(wid: str) -> str:
    return "".join(c for c in os.path.basename(wid or "") if c.isalnum() or c in "-_")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _manifest_path(wid: str) -> str:
    folder = paths.dir_for(_safe(wid))
    # A widget that does not exist yet still needs a path to point at (the caller reports "not found" from the
    # missing file); the generated root is the only sane guess, since that is where a new one would be written.
    return os.path.join(folder or paths.new_dir(_safe(wid)), "manifest.json")


def _load(wid: str):
    p = _manifest_path(wid)
    if not _safe(wid) or not os.path.isfile(p):
        return None, p
    try:
        return json.load(open(p, encoding="utf-8")), p
    except Exception:
        return None, p


def _current_aliases(man: dict) -> list[str]:
    """Current manifest aliases, seeding from name+keywords if the field does not exist yet (lazy migration)."""
    from . import registry
    if man.get("aliases"):
        return list(man["aliases"])
    return registry.widget_identity(man)["aliases"]        # name + keywords, deduped, casing preserved


def _owner_of(alias: str, exclude_id: str):
    """(owner_id, surface) for whoever already owns `alias` (widget or surface), or (None, None). Excludes `exclude_id`."""
    from . import registry
    an = _norm(alias)
    for r in registry.registry():
        if r["id"] == exclude_id:
            continue
        if any(_norm(a) == an for a in r["aliases"]):
            return r["id"], r["surface"]
    return None, None


def _write(man: dict, path: str, aliases: list[str]) -> None:
    """Write `aliases` into the manifest atomically (tmp + os.replace) and invalidate resolver caches."""
    man = dict(man)
    man["aliases"] = aliases
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    from . import runtime
    runtime.invalidate()
    try:
        from . import registry
        registry.refresh_state()
    except Exception:
        pass


def add(widget_id: str, alias: str) -> dict:
    """Add an alias to the widget. Reject collisions with another widget or a system surface. Idempotent
    if already present. Returns {ok, aliases} or {ok:False, error[, owner]}."""
    wid = _safe(widget_id)
    alias = str(alias or "").strip()
    if not alias:
        return {"ok": False, "error": "alias vacío"}
    man, path = _load(wid)
    if man is None:
        return {"ok": False, "error": f"widget '{widget_id}' no existe"}
    cur = _current_aliases(man)
    if any(_norm(a) == _norm(alias) for a in cur):
        return {"ok": True, "aliases": cur, "unchanged": True}
    owner, surface = _owner_of(alias, wid)
    if owner is not None:
        return {"ok": False, "error": f"el alias «{alias}» ya lo usa "
                f"{'la superficie de sistema' if surface == 'system' else 'el widget'} «{owner}»", "owner": owner}
    cur = cur + [alias]
    _write(man, path, cur)
    return {"ok": True, "aliases": cur, "id": wid}


def remove(widget_id: str, alias: str) -> dict:
    """Remove a widget alias. Does NOT allow removing the canonical name, because the widget needs a name to open. Idempotent."""
    wid = _safe(widget_id)
    alias = str(alias or "").strip()
    man, path = _load(wid)
    if man is None:
        return {"ok": False, "error": f"widget '{widget_id}' no existe"}
    name = str(man.get("name") or man.get("title") or wid).strip()
    if _norm(alias) == _norm(name):
        return {"ok": False, "error": f"«{alias}» es el nombre del widget; no se puede quitar (renómbralo)"}
    cur = _current_aliases(man)
    new = [a for a in cur if _norm(a) != _norm(alias)]
    if len(new) == len(cur):
        return {"ok": True, "aliases": cur, "unchanged": True}
    _write(man, path, new)
    return {"ok": True, "aliases": new, "id": wid}


def check_collision(widget_id: str, alias: str) -> str | None:
    """Generator facade: return the id that already owns `alias` (widget/surface), or None. Reusable to reject
    creation of a widget with an occupied alias."""
    owner, _ = _owner_of(alias, _safe(widget_id))
    return owner
