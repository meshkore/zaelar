"""server/wizard_api.py — API del WIZARD de primer arranque (V2-040, Fase 2).

Sirve al overlay web del wizard (Fase 3) y comparte el DETECTOR con el CLI `python -m config.doctor`. El server es
LOCAL, así que puede (a) RE-EJECUTAR el detector en caliente (botón «re-analizar»), (b) aplicar un PERFIL coordinado
(local/cloud), (c) guardar CREDENCIALES en el store (chmod 600, redactadas), y (d) EJECUTAR los instaladores acotados
al proyecto (pip/playwright/ollama pull) o DEVOLVER el comando para los de sistema (brew/apt/npm). Decisiones del
operador 2026-07-15: web + script de sistema; automatizar la instalación en lo posible, comandos si no.

Endpoints (todos bajo /api/wizard):
  GET  /state                → {first_run, active_profile, profiles[], report, installers[]}
  POST /report   {refresh}   → re-analiza el sistema (doctor) y devuelve el informe
  POST /profile  {name}      → aplica el perfil coordinado (settings+v2) y devuelve sus requisitos
  POST /credential {key|provider, value} → guarda/actualiza una API key (redactado; valor vacío = borra)
  POST /install  {id, model?} → lanza un instalador ejecutable (job en background) o devuelve el comando
  GET  /install/{job}        → estado de un job de instalación
  POST /complete             → marca el wizard como hecho (fin del gate de primer arranque)
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Body
from loguru import logger

router = APIRouter()

_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".venv", "bin", "python")
if not os.path.exists(_PY):
    _PY = "python3"


# ── first-run marker (en settings.json, como config_profile de profiles.apply) ─────────────────────────────
def _demo_session() -> bool:
    """Same gate as nucleo/demo_limits.py and nucleo/energy_meter.py — true only on an ephemeral
    demo Fly Machine (cloud/infra/demo-session-worker's demoMachineConfig sets this), never on a
    self-host install."""
    return bool((os.getenv("ZAELAR_DEMO_SESSION") or "").strip())


def _first_run() -> bool:
    if _demo_session():
        # A demo Machine boots fresh every time (ephemeral, auto_destroy=true, no persisted
        # settings.json) — without this the self-host first-run wizard ("Elige un perfil") would
        # show unconditionally to every anonymous demo visitor, even though demoMachineConfig
        # already sets working provider env vars (BASE_PROVIDER_ENV) for them. This wizard is for a
        # human setting up their own machine once, not a public demo session.
        return False
    try:
        from config import settings
        return not bool(settings.get("wizard_done"))
    except Exception:
        return True


def _mark_done(done: bool = True) -> None:
    from config import settings
    settings._write({**settings._read(), "wizard_done": bool(done)})


# ── catálogo de INSTALADORES: qué se puede automatizar vs qué es comando ──────────────────────────────────
# `run` = lista argv ejecutable EN EL SERVER (acotado al proyecto: venv/ollama). `cmd` = string para copiar
# (sistema: brew/curl/npm — permisos/OS-específico, no lo ejecuta la app). `needs` = binario que debe existir.
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
        # sistema → comando para copiar (no lo ejecuta la app)
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


# ── jobs de instalación en background (subprocess; poll de estado) ─────────────────────────────────────────
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
            if len(out) > 60000:                 # cap: no acumular MB de salida
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
    return await asyncio.to_thread(doctor.report, refresh)   # el detector hace I/O (Ollama/http) → fuera del loop


@router.post("/api/wizard/profile")
async def profile(name: str = Body(..., embed=True)) -> dict:
    from config import profiles
    res = profiles.apply(name)
    res["requirements"] = profiles.requirements(name)
    return res


@router.post("/api/wizard/credential")
async def credential(key: str = Body("", embed=True), provider: str = Body("", embed=True),
                     value: str = Body("", embed=True)) -> dict:
    """Guarda una API key. Acepta `key` (nombre de env directo) o `provider` (un id del catálogo de doctor →
    su env principal). Devuelve solo presencia, nunca el valor."""
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
    """Lanza un instalador EJECUTABLE (job en background → poll en /install/{job}) o devuelve el COMANDO para
    copiar si es de sistema. Solo ids del catálogo (allowlist) — nunca un comando arbitrario."""
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
