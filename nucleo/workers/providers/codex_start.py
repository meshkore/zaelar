"""How the Codex worker STARTS: the CLI found and its version checked, the process spawned and its stream
pumped, a dead start's reason read from stderr. Part of providers.codex; module names are read through _x."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nucleo.workers.base import WorkerSpec

from loguru import logger
import asyncio
import glob
import json
import os
import re
import shutil

from nucleo.workers.providers import codex as _x


def find_codex() -> str:
    """Localiza el CLI de Codex. Mismo problema que `claude` en esta clase de máquinas: se instala con npm bajo un
    nvm que NO está en el PATH del server, así que `which` no basta y hay que mirar donde nvm los pone."""
    cand = os.getenv("CODEX_BIN")
    if cand and os.path.exists(os.path.expanduser(cand)):
        return os.path.expanduser(cand)
    found = shutil.which("codex")
    if found:
        return found
    for pat in ("~/.nvm/versions/node/*/bin/codex", "/opt/homebrew/bin/codex",
                "/usr/local/bin/codex", "~/.local/bin/codex", "~/.bun/bin/codex"):
        hits = glob.glob(os.path.expanduser(pat))
        if hits:
            return sorted(hits)[-1]
    return ""


def detect() -> dict:
    """¿Está Codex en ESTA máquina, con qué versión y con qué modelo por defecto? Lo consume el catálogo de
    proveedores de la config (`server/config_api.py`) para que la UI no ofrezca un proveedor que no existe aquí ni
    invente un modelo por defecto distinto del que el propio CLI usaría.

    Barato y sin red: `--version` (proceso local, ~50 ms) + una lectura del `config.toml`. Nunca lanza."""
    path = _x.find_codex()
    out: dict = {"installed": bool(path), "path": path, "version": "", "default_model": ""}
    if not path:
        return out
    try:
        import subprocess
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=8)
        m = _x._VER_RE.search((r.stdout or "") + (r.stderr or ""))
        out["version"] = m.group(1) if m else ""
    except Exception:
        pass
    # The REAL default model is the user's `config.toml` one; minimal parse (`model = "x"`), no TOML reader.
    try:
        home = os.getenv("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
        with open(os.path.join(home, "config.toml"), encoding="utf-8") as fh:
            for line in fh:
                mm = re.match(r'\s*model\s*=\s*"([^"]+)"', line)
                if mm:
                    out["default_model"] = mm.group(1)
                    break
    except Exception:
        pass
    return out


# ── ciclo de vida ─────────────────────────────────────────────────────────────────────────────────────
async def start(self, prompt: str, *, spec: "WorkerSpec") -> None:
    self._task_id = spec.task_id or ""
    self._model = spec.model or ""

    # FAIL-CLOSED (nota 2 de la cabecera): lo que pide contención que Codex no sabe expresar, no corre en Codex.
    if spec.deny_tools or (spec.kind or "") == "dev":
        why = ("entrada NO confiable (deny_tools)" if spec.deny_tools else "worker de desarrollo (kind=dev)")
        await self._fail(f"el backend «codex» no puede acotar sus herramientas y esta tarea es {why}: "
                         f"Codex solo tiene modos de sandbox, no una allowlist de puentes como Claude Code. "
                         f"Cambia el proveedor de Brain Workers a «claude_code» para este tipo de tarea.")
        return

    codex = _x.find_codex()
    if not codex:
        await self._fail("Codex CLI no encontrado (instálalo con `npm i -g @openai/codex` o define CODEX_BIN)")
        return

    cwd = spec.cwd or _x._ZAELAR
    cmd = [codex, "exec", "--json", "--skip-git-repo-check", "-s", _x._SANDBOX, "-C", cwd] + _x._NET_ARGS
    # CONTINUIDAD (V2-049): Codex reanuda por `exec resume <thread_id>`, no por un flag. El id es el
    # `thread.started` de la sesión anterior, que ya guardamos como `native_session_id`.
    if spec.resume_sid:
        cmd = [codex, "exec", "resume", spec.resume_sid, "--json", "--skip-git-repo-check",
               "-s", _x._SANDBOX, "-C", cwd]
        logger.info(f"worker[{self._task_id}]: codex REANUDA hilo {spec.resume_sid[:12]}…")
    if spec.model:
        cmd += ["-m", spec.model]
    if spec.extra_args:
        cmd += list(spec.extra_args)
    cmd += ["-"]                     # el prompt entra por stdin (no por argv: un prompt largo revienta el límite)

    env = dict(os.environ)
    env["PATH"] = os.path.dirname(codex) + os.pathsep + env.get("PATH", "")
    env.update(spec.env or {})
    # Codex authenticates with its own session (`~/.codex/auth.json`) or OPENAI_API_KEY, not Claude Code's relay
    # chain, which is cleared so the CLI never sees credentials that are not its own.
    for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        env.pop(k, None)
    env["ZAELAR_WORKER"] = "1"                    # marcador para el barrido de huérfanos (§v2·D)
    env["ZAELAR_TASK_ID"] = spec.task_id or ""
    if spec.token:
        env["ZAELAR_TASK_TOKEN"] = spec.token     # auth de los puentes por-tarea (§v2·D)

    logger.info(f"worker[{self._task_id}]: CodexSession start (model={spec.model or 'default'}, "
                f"sandbox={_x._SANDBOX}, cwd={cwd})")
    try:
        self._proc = await _x._spawned.spawn(
            *cmd, cwd=cwd, env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,               # grupo propio → killpg mata al codex Y a sus hijos (§v2·D)
            limit=_x._STREAM_LIMIT,
        )
    except Exception as e:  # noqa: BLE001
        await self._fail(f"no se pudo arrancar el worker: {e}")
        return

    try:
        self._proc.stdin.write(prompt.encode("utf-8"))
        await self._proc.stdin.drain()
        self._proc.stdin.close()                  # `exec` espera el EOF del prompt para empezar a trabajar
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker[{self._task_id}]: no pude escribir el prompt inicial: {e}")
    self._reader_task = asyncio.create_task(self._pump(), name=f"worker-pump-{self._task_id}")


# ── lector: JSONL nativo → WorkerEvent ────────────────────────────────────────────────────────────────
async def _pump(self) -> None:
    p = self._proc
    assert p is not None and p.stdout is not None
    try:
        while True:
            line = await p.stdout.readline()
            if not line:
                break
            s = line.decode("utf-8", "replace").strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue                          # ruido no-JSON → ignorar
            for ev in self._map(obj):
                await self._q.put(ev)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker[{self._task_id}]: pump error: {e}")
    finally:
        try:
            await p.wait()
        except Exception:
            pass
        rc = p.returncode or 0
        if not self._done:
            # Codex NO siempre cierra con `turn.completed` (un fallo de auth/red muere antes). El cierre lo
            # emite el pump para que la sesión no quede colgada esperando un evento que nunca llega.
            if rc not in (0, None) or self._failed:
                stderr = b""
                try:
                    stderr = await p.stderr.read()
                except Exception:
                    pass
                msg = self._failed or _x._stderr_reason(stderr) or f"codex salió {rc}"
                await self._q.put(self._ev("error", message=msg[:400], fatal=True))
            await self._q.put(self._ev("result", summary=self._last_message, ok=not (rc or self._failed),
                                       usage=self._usage, model=self._model))
            await self._q.put(self._ev("done"))
            self._done = True


def _stderr_reason(blob: bytes) -> str:
    """La causa REAL del stderr de Codex, que mete su propio ruido: el `failed to load models cache` sale en CADA
    invocación con un CLI viejo y NO es el motivo por el que la tarea murió — devolverlo mandaba a mirar el sitio
    equivocado. Se prefiere la última línea que parezca un error de verdad."""
    txt = blob.decode("utf-8", "replace")
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    noise = ("models cache", "failed to refresh available models", "Reading additional input from stdin")
    real = [ln for ln in lines if not any(n in ln for n in noise)]
    return (real[-1] if real else (lines[-1] if lines else ""))[:400]
