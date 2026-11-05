#
# Widget aliases: surgical manifest editing (V2-082, D1 keyword == alias).
#
# Adding an alias by voice or text must NOT regenerate the widget: it is an ATOMIC write to
# `manifest["aliases"]`, sibling to `widget_data` (which touches data) but scoped to IDENTITY. Cheap,
# deterministic, with no headless agent. Collision guard: an alias belongs to exactly one piece (widget or system
# surface), preserving resolver certainty. Lazy migration seeds `aliases` from `name` + `keywords` on first edit
# when the widget does not have the field yet, creating one identity list.
#
# V2-854 F4 — ONE OWNER PER WORD, and a shipped manifest is never his file. Measured on his engine (2026-11-05): asked
# to «add the aliases Raquel to Rakel Karó», the model called this door and «Raquel» became an alias of the CONTACTS
# card — written into the tracked `widgets/contactos/manifest.json`. Two rules close it: a word the directory resolves
# to a person is HERS (the contacts card's `set_alias` door), never a card's; and a card whose folder is engine
# source keeps his words in a per-tenant overlay (`<workspace>/widgets/_data/_system/aliases.json`, the same place
# `hidden.py` keeps his deletions), which the catalog lays over the manifest it reads. His own widgets (generated,
# forks) are his files: their manifest is still written in place.
#
from __future__ import annotations

import json
import os
import threading
import unicodedata

from loguru import logger

from nucleo import workspace as _workspace
from widgets import paths

HERE = paths.BUILTIN_ROOT

#: The door that owns a person's word (the contacts card's action), named back to whoever asked here.
PERSON_DOOR = "contactos.set_alias"

_lock = threading.Lock()
_ov_cache = {"path": "", "mtime": None, "data": {}}


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


# ── the overlay: his words for a card whose manifest ships with the engine ─────────────────────────────────
def _overlay_path() -> str:
    # Resolved per call — the workspace is an env knob (same rule as `widgets/paths.py` and `hidden.py`).
    return os.path.join(str(_workspace.root()), "widgets", "_data", "_system", "aliases.json")


def overlay() -> dict:
    """{widget_id: {"add": [...], "remove": [...]}} — his words for shipped cards. Cached by mtime (it rides the
    catalog signature, so the steady state costs a stat)."""
    p = _overlay_path()
    try:
        m = os.path.getmtime(p)
    except OSError:
        m = None
    if p == _ov_cache["path"] and m == _ov_cache["mtime"]:
        return _ov_cache["data"]
    data: dict = {}
    if m is not None:
        try:
            raw = json.load(open(p, encoding="utf-8"))
            data = {str(k): {"add": [str(a) for a in (v or {}).get("add") or []],
                             "remove": [str(a) for a in (v or {}).get("remove") or []]}
                    for k, v in (raw or {}).items() if isinstance(v, dict)}
        except Exception:
            data = {}
    _ov_cache.update(path=p, mtime=m, data=data)
    return data


def overlay_signature() -> tuple:
    """What the catalog's cache key carries for the overlay: a change to his words is a change to the catalog."""
    p = _overlay_path()
    try:
        return (p, os.path.getmtime(p))
    except OSError:
        return (p, None)


def _seeded(man: dict) -> list[str]:
    """The manifest's own aliases, seeding from name+keywords if the field does not exist yet (lazy migration)."""
    from . import registry
    if man.get("aliases"):
        return list(man["aliases"])
    return registry.widget_identity(man)["aliases"]        # name + keywords, deduped, casing preserved


def _effective(base: list[str], ov: dict) -> list[str]:
    gone = {_norm(a) for a in ov.get("remove") or []}
    out, seen = [], set()
    for a in [*base, *(ov.get("add") or [])]:
        n = _norm(a)
        if n and n not in seen and n not in gone:
            seen.add(n)
            out.append(a)
    return out


def overlaid(man: dict) -> dict:
    """`man` as the catalog serves it: his overlay words laid over a shipped manifest (a copy; `man` untouched)."""
    ov = overlay().get(str((man or {}).get("id") or ""))
    if not ov or not isinstance(man, dict):
        return man
    return {**man, "aliases": _effective(_seeded(man), ov)}


def _current_aliases(man: dict) -> list[str]:
    """The card's aliases as the catalog serves them (manifest + his overlay)."""
    return list(overlaid(man).get("aliases") or _seeded(man))


def _shipped(path: str) -> bool:
    """The manifest at `path` is engine source (the folder test `paths.is_repo_source` owns): never his file."""
    return paths.is_repo_source(os.path.dirname(path))


def _write_overlay(wid: str, base: list[str], aliases: list[str]) -> None:
    """Record `aliases` for the shipped card `wid` as his delta over `base` (the manifest's own words)."""
    bn, an = {_norm(a) for a in base}, {_norm(a) for a in aliases}
    with _lock:
        data = {k: dict(v) for k, v in overlay().items()}
        entry = {"add": [a for a in aliases if _norm(a) not in bn], "remove": [a for a in base if _norm(a) not in an]}
        if entry["add"] or entry["remove"]:
            data[wid] = entry
        else:
            data.pop(wid, None)
        p = _overlay_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
        os.replace(tmp, p)
        _ov_cache["mtime"] = None


# ── one owner per word: a person's name is hers ──────────────────────────────────────────────────────────────
def _tokens(s: str) -> list[str]:
    return [t for t in "".join(c if c.isalnum() else " " for c in _norm(s)).split() if t]


def names_a_person(alias: str) -> list[dict]:
    """The contacts this word NAMES — an alias he gave them, or every word of it a whole word of one of their names
    (the directory's own reading, `directory.resolve` without its spelling-tolerant last resort; a substring of a
    longer name is not naming). [] when it names nobody or the directory cannot answer."""
    words = _tokens(alias)
    if not words:
        return []
    try:
        from widgets import directory
        hits = directory.resolve(alias, tolerant=False)
    except Exception as e:  # noqa: BLE001 — no directory is no person: the card door goes on as before
        logger.debug(f"aliases: the directory could not say whether «{alias}» names a person — {e!r}")
        return []
    out = []
    for c in hits or []:
        if not isinstance(c, dict) or str(c.get("kind") or "person") != "person":
            continue        # a group, a company or a place named like a card is not a person's word
        said = [_tokens(a) for a in c.get("aliases") or []]
        try:
            from widgets import directory
            said += [_tokens(n) for n in directory.names(c)]
        except Exception:  # noqa: BLE001
            said.append(_tokens(c.get("name") or ""))
        if any(t == words or all(w in t for w in words) for t in said):
            out.append(c)
    return out


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
    people = names_a_person(alias)
    if people:
        # His word for a PERSON is hers: the contacts card's door owns it, never a card's identity (V2-854 F4).
        return {"ok": False, "error": f"«{alias}» names a contact — it belongs to {PERSON_DOOR}, not to a card",
                "person": True, "door": PERSON_DOOR,
                "contacts": [str(c.get("id") or "") for c in people if c.get("id")][:3]}
    owner, surface = _owner_of(alias, wid)
    if owner is not None:
        return {"ok": False, "error": f"el alias «{alias}» ya lo usa "
                f"{'la superficie de sistema' if surface == 'system' else 'el widget'} «{owner}»", "owner": owner}
    cur = cur + [alias]
    _save(wid, man, path, cur)
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
    _save(wid, man, path, new)
    return {"ok": True, "aliases": new, "id": wid}


def _save(wid: str, man: dict, path: str, aliases: list[str]) -> None:
    """His words for this card: the overlay for a shipped manifest, the manifest itself for one of his own."""
    if _shipped(path):
        _write_overlay(wid, _seeded(man), aliases)
        from . import runtime
        runtime.invalidate()
        try:
            from . import registry
            registry.refresh_state()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"aliases: the overlay for {wid} was written but the registry was not refreshed — {e!r}")
        return
    _write(man, path, aliases)


def check_collision(widget_id: str, alias: str) -> str | None:
    """Generator facade: return the id that already owns `alias` (widget/surface), or None. Reusable to reject
    creation of a widget with an occupied alias."""
    owner, _ = _owner_of(alias, _safe(widget_id))
    return owner
