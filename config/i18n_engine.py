"""
i18n_engine — the multilingual backbone (V2-089). "Best of both worlds": PRESET bundles shipped in the repo
(English = base/manifest, Spanish = preset) for instant, deterministic UI; and GENERATED bundles for ANY other
language, produced on the fly by an LLM the first time an operator speaks it (and topped up on every upgrade).

SINGLE SOURCE OF TRUTH = `config/i18n/en.json` (the English manifest: every UI string key → its English text).
Adding a user-facing string ⇒ add its key here. `es.json` is the preset Spanish translation of the same keys.

Language resolution flows from ONE active code (`ZAELAR_LANGUAGE`, via voice/engine/core/langs). The frontend
fetches its bundle from /api/i18n/bundle/<code>; presets come straight from the repo, generated ones from the
workspace store. `ensure(code)` (see below) is the ONE idempotent function that runs at boot / after a language
switch: it checks whether the active language has every manifest key at its current English source and, if any
are missing or the English changed since (new user OR new keys after an update), translates just those with a
strong LLM and persists them. Same function for first-run and for upgrades.

Preset bundles:   <repo>/config/i18n/<code>.json                      (tracked)
Generated bundles: <workspace>/config/i18n/generated/<code>.json      (gitignored, runtime)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from loguru import logger

from nucleo import workspace as _workspace

# Bump when the SET of manifest keys or their English text changes in a way that should invalidate the browser's
# cached bundles and force generated languages to be topped up. (Generation diffing itself uses the per-key
# English snapshot stored in each generated bundle — see ensure(); this version is the coarse cache-buster.)
MANIFEST_VERSION = 1

PRESET = ("en", "es")            # shipped in the repo; never generated
BASE = "en"                      # the manifest language every other bundle is translated FROM

_PRESET_DIR = Path(__file__).resolve().parent / "i18n"
_GEN_DIR = _workspace.root() / "config" / "i18n" / "generated"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def manifest() -> dict[str, str]:
    """The English base: {key: english text}. The canonical list of translatable UI strings."""
    return _read_json(_PRESET_DIR / f"{BASE}.json")


def _preset_bundle(code: str) -> dict[str, str] | None:
    p = _PRESET_DIR / f"{code}.json"
    return _read_json(p) if p.exists() else None


def _gen_path(code: str) -> Path:
    return _GEN_DIR / f"{code}.json"


def _generated_bundle(code: str) -> dict | None:
    """A generated bundle on disk: {"version", "strings": {k:translated}, "src": {k:english-it-was-made-from}}."""
    p = _gen_path(code)
    return _read_json(p) if p.exists() else None


def strings(code: str) -> dict[str, str]:
    """The UI strings for `code`, ready for the frontend. Preset → repo file; else → generated bundle's strings
    (may be empty if it hasn't been generated yet — the frontend falls back to English)."""
    code = (code or BASE).strip().lower()
    if code in PRESET:
        return _preset_bundle(code) or {}
    gen = _generated_bundle(code)
    return dict(gen.get("strings", {})) if gen else {}


def available() -> list[str]:
    """Language codes that have a bundle right now (presets + whatever's been generated)."""
    codes = set(PRESET)
    try:
        for f in _GEN_DIR.glob("*.json"):
            codes.add(f.stem.lower())
    except Exception:
        pass
    return sorted(codes)


def active_code() -> str:
    """The active UI/operator language — the SAME single source of truth the voice pipeline uses."""
    try:
        from voice.engine.core import langs
        return langs.current_code()
    except Exception:
        return BASE


def state() -> dict:
    """What the frontend needs at boot: the active language + which bundles exist."""
    return {"active": active_code(), "available": available(), "preset": list(PRESET),
            "version": MANIFEST_VERSION}


def bundle(code: str) -> dict:
    """Serve one bundle to the frontend: {code, version, strings, generated}."""
    code = (code or BASE).strip().lower()
    return {"code": code, "version": MANIFEST_VERSION, "strings": strings(code),
            "generated": code not in PRESET}


# ── generation / upgrade (P2) ──────────────────────────────────────────────────────────────────────────────
# ensure(code) lives here; it is imported lazily by the boot/detection path. Implemented in i18n_gen.py to keep
# the LLM dependency out of this hot, import-cheap module. This thin shim keeps callers stable.
def missing_keys(code: str) -> list[str]:
    """Keys the active language still needs: absent, or whose English source changed since it was generated.
    Presets are always complete (empty list). Drives ensure() and the 'preparing language' boot veil."""
    code = (code or BASE).strip().lower()
    if code in PRESET:
        return []
    man = manifest()
    gen = _generated_bundle(code) or {}
    have = gen.get("strings", {}) or {}
    src = gen.get("src", {}) or {}
    out = []
    for k, en_text in man.items():
        if k not in have or src.get(k) != en_text:
            out.append(k)
    return out


async def ensure(code: str) -> dict:
    """Idempotent: make sure `code` has every manifest key at its current English source, translating the
    missing/changed ones with an LLM and persisting them. Returns {code, generated:int, total:int}. No-op (and
    cheap) for presets or an already-current language. Delegates the actual LLM work to i18n_gen."""
    code = (code or BASE).strip().lower()
    if code in PRESET:
        return {"code": code, "generated": 0, "total": len(manifest())}
    from config import i18n_gen
    return await i18n_gen.generate_missing(code)


def _save_generated(code: str, merged_strings: dict, merged_src: dict) -> None:
    """Persist a generated bundle atomically (tmp + replace). Used by i18n_gen."""
    _GEN_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": MANIFEST_VERSION, "strings": merged_strings, "src": merged_src}
    tmp = _gen_path(code).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _gen_path(code))
