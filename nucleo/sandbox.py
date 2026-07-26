#
# sandbox.py — ejecución AISLADA y LIGERA de código creado (V2-076, Parte B). El más FÁCIL y ligero (decisión del
# operador), cross-platform Win/Mac, arranque instantáneo, sin runtime extra: un SUBPROCESO efímero acotado. Soporta
# Python + SQLite (stdlib) de fábrica. Docker NO por defecto (consume/va mal); queda como fallback futuro para
# aislamiento fuerte o toolchains pesados (p.ej. Rust).
#
# Aísla por: (1) directorio de trabajo TEMPORAL dedicado (cwd ahí; el código solo ve ese dir); (2) entorno SCRUBBEADO
# (solo PATH/HOME/LANG mínimos — sin secretos, sin claves API, sin ZAELAR_*); (3) topes de RECURSOS (CPU, memoria,
# ficheros, procesos) vía `resource.setrlimit` en Mac/Linux; (4) TIMEOUT de pared que mata el grupo de procesos.
#
# LÍMITE HONESTO (documentado, no falso-verde): un subproceso NO es un aislamiento de kernel a prueba de balas —
# no bloquea la RED de forma dura cross-platform ni impide todo acceso a disco fuera del cwd por rutas absolutas.
# Es el primer nivel "ligero" para AUDITAR/observar código creado sin comprometer el host de forma casual; el
# endurecimiento fuerte (contenedor/micro-VM sin red, FS de solo-lectura) es el paso siguiente (Docker fallback).
#
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

# Topes por defecto (env-overridable, infra).
_CPU_S = int(os.getenv("SANDBOX_CPU_S", "10"))            # segundos de CPU
_WALL_S = float(os.getenv("SANDBOX_WALL_S", "15"))        # segundos de reloj de pared
_MEM_MB = int(os.getenv("SANDBOX_MEM_MB", "512"))         # memoria (address space)
_OUT_MAX = int(os.getenv("SANDBOX_OUT_MAX", str(256 * 1024)))  # recorte de stdout/stderr

# Entorno MÍNIMO: nada del proceso padre salvo lo imprescindible. Sin secretos/claves/ZAELAR_*.
_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "PATHEXT")


def _clean_env() -> dict:
    return {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}


def _rlimits():
    """preexec_fn para Mac/Linux: acota CPU, memoria (address space), nº de ficheros y de procesos. En Windows
    devuelve None (no hay `resource`; el timeout de pared es la red de seguridad)."""
    try:
        import resource
    except Exception:
        return None

    def _apply():
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (_CPU_S, _CPU_S + 1))
        except Exception:
            pass
        try:
            b = _MEM_MB * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
        except Exception:
            pass
        os.setsid()   # grupo propio → matable de una pieza al timeout
    return _apply


def run(code: str, *, lang: str = "python", stdin: str = "", timeout: float | None = None,
        workdir: str | None = None) -> dict:
    """Ejecuta `code` en un subproceso AISLADO y devuelve el resultado. NO lanza: siempre devuelve un dict
    {ok, exit, stdout, stderr, elapsed_s, timed_out, workdir}. Hoy soporta lang='python' (SQLite incluido)."""
    if lang != "python":
        return {"ok": False, "exit": -1, "stdout": "", "stderr": f"lang '{lang}' no soportado aún (solo python)",
                "elapsed_s": 0.0, "timed_out": False, "workdir": ""}
    owns_dir = workdir is None
    wd = workdir or tempfile.mkdtemp(prefix="zaelar-sbx-")
    src = os.path.join(wd, "main.py")
    with open(src, "w", encoding="utf-8") as f:
        f.write(code or "")
    wall = timeout or _WALL_S
    t0 = time.time()
    timed_out = False
    try:
        p = subprocess.run(
            [sys.executable, "-I", "main.py"],       # -I: aislado (ignora env PYTHON*, no añade cwd del usuario)
            cwd=wd, input=stdin, capture_output=True, text=True,
            env=_clean_env(), timeout=wall,
            preexec_fn=_rlimits() if os.name != "nt" else None,
        )
        out, err, code_ = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = ((e.stderr or "") if isinstance(e.stderr, str) else "") + f"\n[sandbox] timeout {wall}s — proceso matado"
        code_ = -1
    except Exception as e:  # noqa: BLE001
        out, err, code_ = "", f"[sandbox] fallo al ejecutar: {type(e).__name__}: {e}", -1
    finally:
        if owns_dir:
            shutil.rmtree(wd, ignore_errors=True)
    return {"ok": (code_ == 0 and not timed_out), "exit": code_,
            "stdout": (out or "")[:_OUT_MAX], "stderr": (err or "")[:_OUT_MAX],
            "elapsed_s": round(time.time() - t0, 2), "timed_out": timed_out, "workdir": wd}


async def arun(code: str, **kwargs) -> dict:
    """Envoltura async (corre `run` fuera del event loop) para llamadores async como el dispatcher."""
    import asyncio
    return await asyncio.to_thread(run, code, **kwargs)


# ── rlimits para el subproceso INTERACTIVO del dev-worker (auditoría 2026-07-26) ────────────────────────────────
# `_rlimits()` de arriba está afinado para `run()` (script de UN turno, wall/CPU cortos): un dev-worker interactivo
# (nucleo/workers/claude_session.py, sesión que puede durar minutos legítimamente) NO debe heredar ese CPU/wall
# corto — su ciclo de vida ya lo gobierna dispatch.py (timeouts/cancelación propios), no un rlimit. Lo que SÍ tiene
# sentido acotar sin límite de tiempo: memoria, nº de procesos y tamaño de fichero — defensa en profundidad contra
# un runaway/fork-bomb, sin arriesgar matar a mitad una tarea real.
_DEV_MEM_MB = int(os.getenv("ZAELAR_DEV_WORKER_MEM_MB", "2048"))
_DEV_NPROC = int(os.getenv("ZAELAR_DEV_WORKER_NPROC", "128"))
_DEV_FSIZE_MB = int(os.getenv("ZAELAR_DEV_WORKER_FSIZE_MB", "512"))


def dev_worker_rlimits():
    """preexec_fn para el subproceso del dev-worker. Mac/Linux only (Windows no tiene `resource` — mismo límite
    honesto que `_rlimits()`). NO llama a `os.setsid()`: `claude_session.py` ya pasa `start_new_session=True`
    (grupo propio para `killpg`); duplicarlo aquí podría chocar con eso.

    LÍMITE HONESTO (verificado empíricamente, no falso-verde): en macOS/Darwin `resource.setrlimit(RLIMIT_AS, …)`
    lanza `ValueError: current limit exceeds maximum limit` — Darwin NO soporta acotar el address-space de un
    proceso así, y punto (no es "más laxo", es un no-op silencioso, atrapado por el `except` de abajo). El tope
    de MEMORIA solo protege de verdad en Linux (producción cloud). `RLIMIT_NPROC` y `RLIMIT_FSIZE` SÍ se aplican
    en ambos (verificado). La protección REAL contra exfiltración/lectura fuera del cwd en CUALQUIER plataforma
    es el jail de rutas (`nucleo/dev_worker_guard.py`, hook PreToolUse), no este rlimit."""
    try:
        import resource
    except Exception:
        return None

    def _apply():
        try:
            b = _DEV_MEM_MB * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (_DEV_NPROC, _DEV_NPROC))
        except Exception:
            pass
        try:
            b = _DEV_FSIZE_MB * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (b, b))
        except Exception:
            pass
    return _apply
