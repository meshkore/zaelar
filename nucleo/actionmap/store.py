"""nucleo/actionmap/store.py — the action_map table's runtime index and seeding (V2-539).

One in-memory dict per process: `{normalized_phrase: entry}` for the ACTIVE language only. The index is
rebuilt lazily on first use, on a language change and on table writes — a miss costs one dict lookup.
All DB access goes through the `memory.api` facade (memory-boundary contract); the DDL lives in
`memory/schema.py::ACTION_MAP`.

Seeding follows the `widgets/agenda/seed.json` convention: the pack ships with the repo
(`nucleo/actionmap/seeds/<lang>.json`), is imported lazily the first time that language is indexed, and
NEVER overwrites a row the user's system has touched — a disabled seed row stays disabled across release
upgrades (UNIQUE(lang, phrase) + INSERT OR IGNORE in the facade). Import problems are LOUD (alert
event), never swallowed: a map whose seeds silently failed to load is a module born dead.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .normalize import normalize

logger = logging.getLogger("zaelar.actionmap")

SEEDS_DIR = Path(__file__).resolve().parent / "seeds"

# Process cache: {"lang": str, "index": dict[str, dict]}. Invalidated on writes and lang change.
_cache: dict = {"lang": None, "index": {}}


def _emit(kind: str, label: str, **kw) -> None:
    try:
        from voice.observer import emit
        emit(kind, label, **kw)
    except Exception:
        pass


def active_lang() -> str:
    """The locked/active language, primary subtag ('es', 'en'). One install, one language (V2-539 §3.2)."""
    try:
        from voice.engine.core import langs
        return (langs.current_code() or "en").split("-")[0].lower()
    except Exception:
        return "en"


def invalidate() -> None:
    _cache["lang"] = None
    _cache["index"] = {}


def _pack_entries(pack: dict) -> list[dict]:
    """The pack's literal `entries` plus the expansion of its `grids` (V2-545).

    A grid is a verb × object table for ONE family of orders — «{abre|ábreme|muéstrame|…} {el WhatsApp|el
    Telegram|el correo}» — expanded here into ordinary, exact-match entries. It is bookkeeping, not
    understanding: nothing at match time gets smarter, the table just stops being written by hand. Which
    matters because these families are precisely where a small model is unreliable and where the phrasings
    are many and boring: «ábreme el Telegram» left the card unmoved live while «muéstrame solo los mensajes
    de Telegram» worked, three turns apart (V2-544/545).

    `objects` maps each object phrase to the value that fills `$` in the action's payload, so one grid
    covers every lens of a widget. Any widget with a declared view action can use it.
    """
    out = list(pack.get("entries") or [])
    for g in (pack.get("grids") or []):
        verbs = [str(v).strip() for v in (g.get("verbs") or []) if str(v).strip()]
        objects = g.get("objects") or {}
        action = g.get("action") or {}
        for obj, value in objects.items():
            body = json.loads(json.dumps(action).replace('"$"', json.dumps(value)))
            for v in verbs:
                out.append({"phrase": f"{v} {obj}".strip(), "action": body})
    return out


def ensure_seeded(lang: str) -> None:
    """Import the shipped pack for `lang`, once per PACK VERSION. Respects every row the operator touched.

    It used to import once per install and never again («any seed row exists» = done), so a pack fixed later
    reached nobody: an engine seeded on day one kept day-one phrases forever. Now the pack carries a
    `version` and an upgrade re-runs the import: new phrases are inserted, and a phrase that is still an
    untouched shipped row is RETARGETED to what the pack now says. A row the operator disabled, or one the
    map learned, is never moved (V2-545)."""
    try:
        from memory import api as _mapi
        path = SEEDS_DIR / f"{lang}.json"
        if not path.exists():
            return  # no pack for this language yet — the map simply stays empty (generated packs: Phase 3)
        pack = json.loads(path.read_text(encoding="utf-8"))
        version = int(pack.get("version") or 1)
        have = _mapi.action_map_seed_version(lang)
        if have >= version:
            return
        entries = _pack_entries(pack)
        from . import executor
        ok, bad, moved = 0, 0, 0
        for e in entries:
            phrase = normalize(str(e.get("phrase") or ""))
            action = e.get("action")
            why = executor.validate(action) if phrase else "empty phrase"
            if why:
                bad += 1
                logger.warning(f"actionmap seed refused ({lang}): {e.get('phrase')!r} — {why}")
                continue
            body = json.dumps(action, ensure_ascii=False)
            _mapi.action_map_add(lang, phrase, body)
            if have and _mapi.action_map_retarget_seed(lang, phrase, body):
                moved += 1
            ok += 1
        _mapi.action_map_set_seed_version(lang, version)
        # Loud either way: the import is an event worth a timeline row; refusals are an ALERT.
        _emit("alert" if bad else "system",
              f"action map seeded ({lang}, pack v{version}): {ok} entries" +
              (f" · {moved} retargeted" if moved else "") + (f" · {bad} REFUSED" if bad else ""),
              role="system",
              extra={"cat": "flash", "lang": lang, "ok": ok, "refused": bad, "moved": moved, "version": version})
    except Exception as e:  # noqa: BLE001
        _emit("alert", "action map seeding FAILED", text=repr(e)[:200], role="system",
              extra={"cat": "flash", "lang": lang})


def index() -> dict[str, dict]:
    """The active language's `{phrase: entry}` map. entry = {id, action(dict), source}. Never raises."""
    lang = active_lang()
    if _cache["lang"] == lang:
        return _cache["index"]
    try:
        from memory import api as _mapi
        ensure_seeded(lang)
        idx: dict[str, dict] = {}
        for r in _mapi.action_map_active(lang):
            try:
                idx[r["phrase"]] = {"id": r["id"], "action": json.loads(r["action"]), "source": r["source"]}
            except Exception:
                continue
        _cache["lang"], _cache["index"] = lang, idx
        return idx
    except Exception:
        return {}


def record_hit(entry_id: int) -> None:
    try:
        from memory import api as _mapi
        _mapi.action_map_hit(entry_id)
    except Exception:
        pass
