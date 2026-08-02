"""
i18n_api — HTTP surface for the multilingual UI (V2-089).

  GET  /api/i18n/state          → {active, available, preset, version}   (boot: which language + what exists)
  GET  /api/i18n/bundle/{code}  → {code, version, strings, generated}    (the UI strings for one language)
  POST /api/i18n/ensure/{code}  → {code, generated, total}               (generate/top-up a language on demand)

Presets (en/es) come straight from the repo; any other language is generated on the fly by the i18n engine.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import i18n_engine as _i18n

router = APIRouter()


@router.get("/api/i18n/state")
async def i18n_state():
    return _i18n.state()


@router.get("/api/i18n/bundle/{code}")
async def i18n_bundle(code: str):
    return _i18n.bundle(code)


@router.post("/api/i18n/ensure/{code}")
async def i18n_ensure(code: str):
    try:
        return await _i18n.ensure(code)
    except Exception as e:
        return JSONResponse({"code": code, "generated": 0, "error": str(e)}, status_code=500)
