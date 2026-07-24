"""nucleo/agentes/codex.py — `CodeAgent` sobre Codex (proveedor alternativo). V2-006 · T79.

Segunda implementación de la interfaz `CodeAgent`, intercambiable con `ClaudeCodeAgent` sin tocar el
SlowBrain — prueba viva de que la costura `CodeAgent` desacopla al cerebro del proveedor. **Modelo POR
INVOCACIÓN** (idéntica regla).

Estado: adaptador **verificable pero no probado en vivo** — localiza el CLI de Codex (`codex`) y, si existe,
lo corre en modo no interactivo; si NO está instalado, devuelve un `RunResult.ok=False` LIMPIO (nunca lanza),
de modo que cambiar el proveedor a `codex` por config no rompe la firma ni el dispatcher (el operador ve un
error claro, no un crash). Cuando se adopte Codex de verdad, aquí se afina el mapeo de flags; la interfaz no
cambia.
"""
from __future__ import annotations

import asyncio
import os
import shutil

from loguru import logger

from .base import CodeAgent, RunResult, RunSpec


def _find_codex() -> str:
    cand = os.getenv("CODEX_BIN")
    if cand and os.path.exists(os.path.expanduser(cand)):
        return os.path.expanduser(cand)
    return shutil.which("codex") or ""


class CodexAgent(CodeAgent):
    name = "codex"

    async def run(self, prompt: str, *, spec: "RunSpec") -> "RunResult":
        codex = _find_codex()
        if not codex:
            return RunResult(ok=False, error="Codex CLI no encontrado (define CODEX_BIN); "
                                             "el proveedor por defecto es claude_code")
        # Ejecución no interactiva. Modelo POR INVOCACIÓN (--model). El mapeo fino de flags/sandbox de Codex se
        # afina al adoptarlo; la firma (async, RunSpec→RunResult) es la misma que ClaudeCodeAgent.
        cmd = [codex, "exec"]
        if spec.model:
            cmd += ["--model", spec.model]
        if spec.deny_tools:
            cmd += ["--sandbox", "read-only"]
        env = dict(os.environ)
        env["PATH"] = os.path.dirname(codex) + os.pathsep + env.get("PATH", "")
        env.update(spec.env or {})
        cwd = spec.cwd or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        logger.info(f"slowbrain: CodexAgent run (model={spec.model or 'default'}, cwd={cwd})")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=cwd, env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")), timeout=spec.timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill(); await proc.wait()
            except Exception:
                pass
            return RunResult(ok=False, error=f"el agente Codex superó el timeout ({spec.timeout}s)")
        except Exception as e:  # noqa: BLE001
            return RunResult(ok=False, error=f"fallo ejecutando Codex: {e}")
        stdout = (out_b or b"").decode("utf-8", "replace").strip()
        stderr = (err_b or b"").decode("utf-8", "replace")
        rc = proc.returncode or 0
        if rc != 0:
            return RunResult(ok=False, output=stdout, error=stderr[:500] or f"codex salió {rc}",
                             meta={"returncode": rc, "model": spec.model})
        return RunResult(ok=True, output=stdout, meta={"returncode": rc, "model": spec.model})
