"""i18n.init.fillers — per-language lead-in filler pack (V2-114, 2026-08-17).

Same shape and rationale as `i18n.init.aliases` (V2-101): the hardcoded es/en filler pool in
`voice/engine/core/langs.py::LangSpec.fillers` is a fast, verified-native accelerator, not a hard requirement —
`voice/engine/speech/filler_audio.py` (via `langs.pick_filler()`) checks THIS generated store first, per language,
and only fall back to the hardcoded pool (today: only present for es/en, itself falling back to English for any
other onboarded language — see `voice/engine/core/langs.py::current_code()`) when nothing was generated.

Deliberately NOT wired to an LLM generation call yet (unlike `aliases.ensure_aliases`, which DOES generate at
onboarding) — the operator scoped this pass to "fail gracefully for now", the same decision already governing
the rest of the voice pipeline (STT/TTS/reply language) for non-preset languages. This module exists so that
decision can be revisited later — generate + call `save()` here — WITHOUT touching the read side that
`pick_filler()` already depends on.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from nucleo import workspace as _workspace

_GEN_DIR = _workspace.root() / "i18n" / "generated"


def _path(code: str) -> Path:
    return _GEN_DIR / f"{code}.fillers.json"


def _smalltalk_path(code: str) -> Path:
    return _GEN_DIR / f"{code}.smalltalk.json"


def read(code: str) -> list[str]:
    """The generated filler pool for `code` — [] if never generated (caller falls back to the hardcoded pool)."""
    try:
        data = json.loads(_path(code).read_text(encoding="utf-8"))
        return [str(f) for f in (data.get("fillers") or []) if str(f).strip()]
    except Exception:
        return []


def read_covers(code: str, kind: str) -> list[str]:
    """The generated WORK-COVER pool for `code` (V2-669) — the short line said at the TOOL SEAM, per kind
    ("widget" | "search" | "recall"). Same contract as `read`: [] when never generated, and the caller falls
    back to the hardcoded es/en pool in `langs.LangSpec`. It shares this file on purpose — a language pack is
    one artefact, so whatever eventually generates fillers generates these in the same pass."""
    try:
        data = json.loads(_path(code).read_text(encoding="utf-8"))
        return [str(f) for f in (data.get(f"covers_{kind}") or []) if str(f).strip()]
    except Exception:
        return []


def read_smalltalk(code: str) -> dict:
    """The generated PHRASEBOOK for `code` (V2-674) — `{}` if never generated, so the caller keeps its own
    hardcoded es/en table. It lives in its OWN file rather than in the filler pack: a phrasebook is a nested
    structure that a translator fills intent by intent, while the pack above is flat lists, and a partial
    write of one must not be able to truncate the other."""
    try:
        data = json.loads(_smalltalk_path(code).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_smalltalk(code: str, book: dict) -> None:
    """Persist a generated phrasebook atomically (tmp + os.replace) — same crash-safety as `save`."""
    _GEN_DIR.mkdir(parents=True, exist_ok=True)
    p = _smalltalk_path(code)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(book or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def save(code: str, fillers: list[str], covers: dict | None = None) -> None:
    """Persist a generated pool atomically (tmp + os.replace) — same crash-safety pattern as `i18n.store.save`."""
    _GEN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(code).with_suffix(".fillers.json.tmp")
    payload: dict = {"fillers": list(fillers or [])}
    if covers:
        payload.update({f"covers_{k}": list(v or []) for k, v in covers.items()})
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _path(code))
