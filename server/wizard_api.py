"""server/wizard_api.py — first-run WIZARD API (V2-040, Phase 2).

Serves the wizard web overlay (Phase 3) and shares the DETECTOR with the `python -m config.doctor` CLI. The server
is LOCAL, so it can (a) RE-RUN the detector live ("re-analyze" button), (b) apply a coordinated PROFILE
(local/cloud), (c) save CREDENTIALS in the store (chmod 600, redacted), and (d) RUN project-scoped installers
(pip/playwright/ollama pull) or RETURN the command for system-level ones (brew/apt/npm). Operator decisions
2026-07-15: web + system script; automate installation where possible, commands otherwise.

Endpoints (all under /api/wizard):
  GET  /state                → {first_run, active_profile, profiles[], report, installers[]}
  POST /report   {refresh}   → re-analyzes the system (doctor) and returns the report
  POST /profile  {name}      → applies the coordinated profile (settings+v2) and returns its requirements
  POST /credential {key|provider, value} → saves/updates an API key (redacted; empty value = delete)
  POST /install  {id, model?} → launches an executable installer (background job) or returns the command
  GET  /install/{job}        → installation job status
  POST /complete             → marks the wizard as done (end of first-run gate)
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Body
from loguru import logger

from nucleo import cloud_account

router = APIRouter()

_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".venv", "bin", "python")
if not os.path.exists(_PY):
    _PY = "python3"


# ── first-run marker (in settings.json, like config_profile from profiles.apply) ────────────────────────────
def _first_run() -> bool:
    if cloud_account.is_cloud_account():
        # A real account Machine boots fresh (persisted Volume, but no settings.json of its own)
        # and already gets working provider env vars from accountMachineConfig — the self-host
        # first-run wizard ("Elige un perfil") is for a human setting up their own machine once,
        # not a cloud account.
        return False
    try:
        from config import settings
        return not bool(settings.get("wizard_done"))
    except Exception:
        return True


def _mark_done(done: bool = True) -> None:
    from config import settings
    settings._write({**settings._read(), "wizard_done": bool(done)})


# ── INSTALLER catalog: what can be automated vs what is a command ──────────────────────────────────────────
# `run` = argv list executable ON THE SERVER (project-scoped: venv/ollama). `cmd` = string to copy (system-level:
# brew/curl/npm — permissions/OS-specific, not executed by the app). `needs` = binary that must exist.
def installers() -> list[dict]:
    return [
        {"id": "playwright", "label": "Navegador Chromium (Playwright)", "runnable": True,
         "run": [_PY, "-m", "playwright", "install", "chromium"],
         "why": "navegador web + búsqueda Google gratis"},
        {"id": "stt_local", "label": "STT local (Whisper)", "runnable": True,
         "run": ["make", "install-stt"], "why": "voz→texto privado y gratis"},
        {"id": "tts_local", "label": "TTS local (Kokoro)", "runnable": True,
         "run": ["make", "install-tts"], "why": "texto→voz privado y gratis"},
        {"id": "ollama_model", "label": "Modelo de Ollama (pull)", "runnable": True, "needs": "ollama",
         "run": ["ollama", "pull", "{model}"], "why": "modelo local para cerebro/memoria (requiere Ollama)"},
        # system-level → command to copy (the app does not execute it)
        {"id": "ollama", "label": "Ollama (servicio local)", "runnable": False,
         "cmd": "curl -fsSL https://ollama.com/install.sh | sh   # macOS: brew install ollama",
         "why": "motor de modelos locales (perfil local)"},
        {"id": "livekit", "label": "Servidor LiveKit (binario nativo)", "runnable": False,
         "cmd": "make install-livekit", "why": "servidor de medios de voz (sin Docker)"},
        {"id": "claude_cli", "label": "Claude Code CLI", "runnable": False,
         "cmd": "npm i -g @anthropic-ai/claude-code", "why": "agentes SlowBrain + generador de widgets"},
    ]


def _installer(iid: str) -> dict | None:
    return next((i for i in installers() if i["id"] == iid), None)


# ── background installation jobs (subprocess; status polling) ───────────────────────────────────────────────
_JOBS: dict[str, dict] = {}
_job_seq = {"n": 0}


async def _run_job(job_id: str, argv: list[str]) -> None:
    _JOBS[job_id]["status"] = "running"
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        out = bytearray()
        assert proc.stdout is not None
        async for line in proc.stdout:
            out += line
            if len(out) > 60000:                 # cap: do not accumulate MB of output
                del out[:20000]
            _JOBS[job_id]["tail"] = out.decode("utf-8", "replace")[-4000:]
        rc = await proc.wait()
        _JOBS[job_id]["returncode"] = rc
        _JOBS[job_id]["status"] = "done" if rc == 0 else "failed"
    except Exception as e:  # noqa: BLE001
        _JOBS[job_id]["status"] = "failed"
        _JOBS[job_id]["tail"] = (_JOBS[job_id].get("tail", "") + f"\n[error] {e}")[-4000:]


# ── endpoints ──────────────────────────────────────────────────────────────────────────────────────────────
@router.get("/api/wizard/state")
async def state() -> dict:
    from config import doctor, profiles
    return {
        "first_run": _first_run(),
        "active_profile": profiles.active(),
        "profiles": profiles.public(),
        "report": doctor.report(refresh=False),
        "installers": installers(),
    }


@router.post("/api/wizard/report")
async def report(refresh: bool = Body(True, embed=True)) -> dict:
    from config import doctor
    return await asyncio.to_thread(doctor.report, refresh)   # the detector does I/O (Ollama/http) → off the loop


@router.post("/api/wizard/profile")
async def profile(name: str = Body(..., embed=True)) -> dict:
    from config import profiles
    res = profiles.apply(name)
    res["requirements"] = profiles.requirements(name)
    return res


@router.post("/api/wizard/credential")
async def credential(key: str = Body("", embed=True), provider: str = Body("", embed=True),
                     value: str = Body("", embed=True)) -> dict:
    """Save an API key. Accepts `key` (direct env name) or `provider` (an id from the doctor catalog → its main env).
    Returns presence only, never the value."""
    from config import credentials, doctor
    env_name = (key or "").strip()
    if not env_name and provider:
        spec = next((c for c in doctor.CREDENTIALS if c["key"] == provider.strip()), None)
        if spec and spec.get("env"):
            env_name = spec["env"][0]
    if not env_name:
        return {"ok": False, "error": "falta 'key' o 'provider' conocido"}
    res = credentials.set_key(env_name, value)
    return res


@router.post("/api/wizard/install")
async def install(id: str = Body(..., embed=True), model: str = Body("", embed=True)) -> dict:
    """Launch an EXECUTABLE installer (background job → poll at /install/{job}) or return the COMMAND to copy if it
    is system-level. Catalog ids only (allowlist) — never an arbitrary command."""
    spec = _installer(id)
    if not spec:
        return {"ok": False, "error": f"instalador desconocido: {id}"}
    if not spec.get("runnable"):
        return {"ok": True, "runnable": False, "command": spec.get("cmd", "")}
    if spec.get("needs") and not shutil.which(spec["needs"]):
        return {"ok": False, "error": f"falta '{spec['needs']}' — instálalo primero"}
    argv = list(spec["run"])
    if "{model}" in argv:
        m = (model or "").strip()
        if not m:
            return {"ok": False, "error": "falta 'model' para el pull de Ollama"}
        argv = [m if a == "{model}" else a for a in argv]
    _job_seq["n"] += 1
    job_id = f"job{_job_seq['n']}"
    _JOBS[job_id] = {"id": job_id, "installer": id, "status": "queued", "returncode": None, "tail": ""}
    asyncio.create_task(_run_job(job_id, argv))
    return {"ok": True, "runnable": True, "job": job_id, "cmd_shown": " ".join(argv)}


@router.get("/api/wizard/install/{job}")
async def install_status(job: str) -> dict:
    j = _JOBS.get(job)
    if not j:
        return {"ok": False, "error": "job desconocido"}
    return {"ok": True, **j}


@router.post("/api/wizard/complete")
async def complete(done: bool = Body(True, embed=True)) -> dict:
    try:
        _mark_done(done)
        return {"ok": True, "first_run": _first_run()}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"wizard complete falló: {e}")
        return {"ok": False, "error": str(e)[:200]}
