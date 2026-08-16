"""
i18n_api — HTTP surface for the multilingual UI (V2-089). Thin: GET endpoints hit the runtime (hot path), the
ensure/choose endpoints hit init (may generate). See the i18n package docstring for the runtime-vs-init
separation.

  GET  /api/i18n/state          → {active, available, preset, version, chosen}  (boot: which language + what
                                    exists + whether ANY language has ever been explicitly chosen — V2-101,
                                    drives whether the first-run language-onboarding modal shows at all)
  GET  /api/i18n/bundle/{code}  → {code, version, strings, generated}    (the UI strings for one language)
  POST /api/i18n/ensure/{code}  → {code, generated, total, …}            (generate/top-up a language on demand)
  POST /api/i18n/choose/{code}  → {ok, code, confirm_text}               (V2-101: the onboarding modal's
                                    quick-pick chips — locks a KNOWN code directly, no STT classification)
  POST /api/i18n/detect-text    → {ok, code, confirm_text}               (V2-101: the onboarding modal's typed
                                    fallback — classifies free text the same way a spoken answer would be)
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from i18n import runtime as _rt
from i18n import init as _init
from i18n.init import detect as _detect

router = APIRouter()


@router.get("/api/i18n/state")
async def i18n_state():
    state = _rt.state()
    state["chosen"] = not _detect.should_detect()
    return state


@router.get("/api/i18n/bundle/{code}")
async def i18n_bundle(code: str):
    return _rt.bundle(code)


@router.post("/api/i18n/ensure/{code}")
async def i18n_ensure(code: str):
    try:
        return await _init.prepare(code)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"code": code, "generated": 0, "error": str(e)}, status_code=500)


async def _lock_and_speak(code: str) -> dict:
    result = await _detect.lock(code, onboarding=True)
    if result.get("ok") and result.get("confirm_text"):
        try:
            from voice import proactive
            await proactive.notify("", result["confirm_text"], kind="language")
        except Exception:
            pass
    return result


@router.post("/api/i18n/choose/{code}")
async def i18n_choose(code: str):
    try:
        return await _lock_and_speak(code)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "code": code, "error": str(e)}, status_code=500)


@router.post("/api/i18n/detect-text")
async def i18n_detect_text(request: Request):
    """The onboarding modal's typed fallback (V2-101): classify free text the SAME way a spoken answer would
    be, for an operator who'd rather type than talk (mic denied, noisy room, prefers keyboard)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = str((body or {}).get("text") or "").strip()
    if len(text) < 2:
        return JSONResponse({"ok": False, "error": "empty_text"}, status_code=400)
    try:
        code = await asyncio.to_thread(_detect.classify, text)
        if not code:
            return {"ok": False, "error": "not_recognized"}
        return await _lock_and_speak(code)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
