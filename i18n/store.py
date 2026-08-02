"""
i18n.store — persistence of GENERATED language bundles (V2-089).

Preset bundles (en/es) are DATA in the repo at i18n/bundles/. GENERATED bundles (any other language the LLM
produced) are RUNTIME data: they live in the workspace, out of the repo, and are written by i18n.init and read
by i18n.runtime. This module owns those paths + atomic IO — nothing else touches the generated store directly.

A generated bundle on disk:
  {"version": <manifest version it was built at>,
   "strings": {key: translated-text},
   "src":     {key: the ENGLISH text it was translated FROM}}   ← lets the upgrade diff detect changed sources
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from nucleo import workspace as _workspace

_GEN_DIR = _workspace.root() / "i18n" / "generated"


def _path(code: str) -> Path:
    return _GEN_DIR / f"{code}.json"


def read(code: str) -> dict:
    """The generated bundle for `code` (or {} if it hasn't been generated yet)."""
    try:
        return json.loads(_path(code).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(code: str, version: int, strings: dict, src: dict) -> None:
    """Persist a generated bundle atomically (tmp + os.replace) so a crash mid-write can't corrupt it."""
    _GEN_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": version, "strings": strings, "src": src}
    tmp = _path(code).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _path(code))


def codes() -> list[str]:
    """Language codes that have a generated bundle on disk."""
    try:
        return sorted(f.stem.lower() for f in _GEN_DIR.glob("*.json"))
    except Exception:
        return []
