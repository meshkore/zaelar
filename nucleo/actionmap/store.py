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


def ensure_seeded(lang: str) -> None:
    """Import the shipped pack for `lang` once. Idempotent; respects every row already in the table."""
    try:
        from memory import api as _mapi
        if _mapi.action_map_has_seed(lang):
            return
        path = SEEDS_DIR / f"{lang}.json"
        if not path.exists():
            return  # no pack for this language yet — the map simply stays empty (generated packs: Phase 3)
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries") or []
        from . import executor
        ok, bad = 0, 0
        for e in entries:
            phrase = normalize(str(e.get("phrase") or ""))
            action = e.get("action")
            why = executor.validate(action) if phrase else "empty phrase"
            if why:
                bad += 1
                logger.warning(f"actionmap seed refused ({lang}): {e.get('phrase')!r} — {why}")
                continue
            _mapi.action_map_add(lang, phrase, json.dumps(action, ensure_ascii=False))
            ok += 1
        # Loud either way: the import is a one-time event worth a timeline row; refusals are an ALERT.
        _emit("alert" if bad else "system", f"action map seeded ({lang}): {ok} entries" +
              (f" · {bad} REFUSED" if bad else ""), role="system",
              extra={"cat": "flash", "lang": lang, "ok": ok, "refused": bad})
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
