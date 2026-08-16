"""
i18n.init.aliases — per-language voice-command alias packs for the native system surfaces (V2-101).

The fast, hardcoded es/en aliases in `widgets/system_surfaces.py` (and their frontend mirror,
`system-surfaces.js`) are ~50 ms local accelerators for the name resolver (`widgets/runtime.py::identify`) —
not a requirement. An uncovered language simply falls through to the LLM router (a touch slower, still
correct). `.meshkore/docs/architecture/zaelar-i18n.md` already names this as a deferred extension point:
generate a per-language pack of alias words for the same closed set of surfaces, wired ADDITIVELY so the
resolver's matching logic itself never changes — only the candidate list it matches against grows.

INITIALIZATION only (never the hot path), same shape as `i18n.init.ensure`/`generate`: one batched LLM call
(all surfaces at once — there are only ~10, one call beats ten), off-thread, fail-open to an empty pack (the
LLM router covers correctness in the meantime; a missing alias pack never blocks or breaks anything).

Deliberately scoped to the SYSTEM SURFACES only — never `voice/attention.py`'s hard-interrupt vocabulary or
`nucleo/flash/router.py`'s backstop regex. Those are safety/precision-critical deterministic guards, not
"which widget did you mean" convenience matching, and localizing them is a separate, dedicated effort.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from loguru import logger

from nucleo import workspace as _workspace

_GEN_DIR = _workspace.root() / "i18n" / "generated"


def _path(code: str) -> Path:
    return _GEN_DIR / f"{code}.aliases.json"


def read(code: str) -> dict[str, list[str]]:
    """The generated alias pack for `code` — {surface_id: [alias, ...]}, or {} if never generated."""
    try:
        return json.loads(_path(code).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(code: str, pack: dict[str, list[str]]) -> None:
    _GEN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(code).with_suffix(".aliases.json.tmp")
    tmp.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _path(code))


def _system(lang_name: str) -> str:
    return (
        f"You help voice-command matching for a personal AI assistant. For each system surface (an opaque "
        f"KEY, its English NAME, and a few example English/Spanish alias words people already use to open it "
        f"by voice), give 4-6 short, natural words or 2-3 word phrases a {lang_name} speaker would say to "
        f"open THAT surface by voice. Lowercase, no punctuation. Return ONLY a JSON object mapping each KEY "
        f"to a JSON array of {lang_name} alias strings — no prose, no code fences. Do not translate the "
        f"example aliases word-for-word; give what a native speaker would naturally SAY."
    )


def _parse(raw: str) -> dict[str, list[str]]:
    if not raw:
        return {}
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    try:
        d = json.loads(s)
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in d.items():
        if isinstance(v, list):
            words = [w.strip().lower() for w in v if isinstance(w, str) and w.strip()]
            if words:
                out[k] = words
    return out


def _generate_sync(code: str) -> dict[str, list[str]]:
    from nucleo import memllm
    from i18n.init.generate import language_name
    from widgets.system_surfaces import SYSTEM_SURFACES

    payload = {sid: {"name": s["name"], "examples": s["aliases"][:4]} for sid, s in SYSTEM_SURFACES.items()}
    raw = memllm.chat_sync("i18n", _system(language_name(code)), json.dumps(payload, ensure_ascii=False),
                           max_tokens=2000, temperature=0.2, timeout=60.0)
    return _parse(raw or "")


async def ensure_aliases(code: str) -> dict:
    """Make sure `code` has an alias pack on disk. Idempotent — a cheap no-op once generated. PRESET languages
    (en/es) never call this: their aliases are already hardcoded in `system_surfaces.py` itself. Returns
    {code, generated, surfaces}."""
    import asyncio

    code = (code or "").strip().lower()
    existing = read(code)
    if existing:
        return {"code": code, "generated": 0, "surfaces": len(existing)}
    logger.info(f"i18n.aliases: no alias pack for '{code}' yet — generating…")
    try:
        pack = await asyncio.to_thread(_generate_sync, code)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.aliases[{code}]: generation failed: {str(e)[:160]}")
        pack = {}
    if pack:
        _save(code, pack)
    return {"code": code, "generated": len(pack), "surfaces": len(pack)}


def aliases_for(code: str, surface_id: str) -> list[str]:
    """Extra alias words for `surface_id` in `code`'s generated pack (empty list if none/not generated)."""
    return read(code).get(surface_id, [])
