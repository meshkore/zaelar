"""
i18n_api — HTTP surface for the multilingual UI (V2-089). Thin: GET endpoints hit the runtime (hot path), the
ensure endpoint hits init (may generate). See the i18n package docstring for the runtime-vs-init separation.

  GET  /api/i18n/state          → {active, available, preset, version}   (boot: which language + what exists)
  GET  /api/i18n/bundle/{code}  → {code, version, strings, generated}    (the UI strings for one language)
  POST /api/i18n/ensure/{code}  → {code, generated, total, …}            (generate/top-up a language on demand)
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from i18n import runtime as _rt
from i18n import init as _init

router = APIRouter()


@router.get("/api/i18n/state")
async def i18n_state():
    return _rt.state()


@router.get("/api/i18n/bundle/{code}")
async def i18n_bundle(code: str):
    return _rt.bundle(code)


@router.post("/api/i18n/ensure/{code}")
async def i18n_ensure(code: str):
    try:
        return await _init.prepare(code)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"code": code, "generated": 0, "error": str(e)}, status_code=500)
