"""
i18n.init.ensure — the idempotent language readiness check (V2-089).

ONE function, run at boot / after a language switch / after an upgrade: does the active language have every
manifest key at its CURRENT English source? If yes → instant no-op. If not (brand-new language, or new keys
shipped in an update), translate JUST the missing/changed keys with the LLM and persist them. First-run and
upgrade take the exact same path — the difference is only how many keys are missing.

This is INITIALIZATION, not execution: it may call an LLM and take a few seconds, so callers gate it behind the
'preparing language' boot veil. The hot path (i18n.runtime) never touches this.
"""
from __future__ import annotations

from loguru import logger

from i18n import runtime as _rt, store as _store


async def ensure_language(code: str) -> dict:
    """Make `code` complete against the manifest. Returns {code, generated, total, missing_before}."""
    code = (code or _rt.BASE).strip().lower()
    man = _rt.manifest()
    total = len(man)

    if code in _rt.PRESET:
        return {"code": code, "generated": 0, "total": total, "missing_before": 0}

    missing = _rt.missing_keys(code)
    if not missing:
        return {"code": code, "generated": 0, "total": total, "missing_before": 0}

    logger.info(f"i18n.init: language '{code}' missing {len(missing)}/{total} keys — generating…")
    from i18n.init import generate
    translated = await generate.translate(code, {k: man[k] for k in missing})

    gen = _store.read(code)
    strings = dict(gen.get("strings", {}))
    src = dict(gen.get("src", {}))
    for k, v in (translated or {}).items():
        if isinstance(v, str) and v.strip():
            strings[k] = v
            src[k] = man[k]                       # snapshot the English we translated FROM (upgrade diff)
    _store.save(code, _rt.MANIFEST_VERSION, strings, src)
    logger.info(f"i18n.init: language '{code}' generated {len(translated or {})} keys.")
    return {"code": code, "generated": len(translated or {}), "total": total, "missing_before": len(missing)}
