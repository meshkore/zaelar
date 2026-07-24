"""nucleo/agentes/claude_code.py — `CodeAgent` sobre Claude Code headless (`claude -p`). V2-006 · T78.

Implementación por defecto del SlowBrain: lanza Claude Code en modo headless como subproceso, con
sandbox/cwd/timeout de `RunSpec` y **modelo POR INVOCACIÓN** (`--model spec.model`, nunca una env global).
Es el mismo patrón que ya programa widgets (`widgets/generator.py`), promovido a agente de trabajo general
del cerebro — pero AISLADO del circuito de widgets (copia propia de `_find_claude`, sin acoplar el SlowBrain
al módulo de widgets, que sobrevive al entierro de Hermes mientras que esto es cerebro nuevo).

Diferencias con el generador de widgets:
  - `async` de verdad (el SlowBrain corre off-voz en el loop del server): usa `asyncio.create_subprocess_exec`
    + `wait_for(timeout)`, no `subprocess.run` bloqueante.
  - Modelo por invocación desde `spec.model` (el generador usa una env global; aquí está PROHIBIDO).
  - Política de tools por `spec`: `deny_tools=True` (input NO confiable, V2-010) → NINGUNA tool; si no,
    `spec.tools` (allowlist) o el default seguro `Read` (solo lectura, sin Bash/Write salvo que se pida).
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import shutil

from loguru import logger

from .base import CodeAgent, RunResult, RunSpec

# Raíz de zaelar = cwd por defecto del agente (dos niveles arriba de este fichero: nucleo/agentes/ → zaelar/).
_ZAELAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Default de tools SEGURO para un turno confiable sin allowlist explícita: solo lectura. Trabajo que necesite
# escribir/ejecutar lo pide con `spec.tools=["Write","Edit",...]` o `["Bash"]` explícitamente (decisión del
# dispatcher, V2-007). Un turno NO confiable (deny_tools) corre sin ninguna.
_DEFAULT_TOOLS = ["Read"]
# PUENTES V2-036: un turno CONFIABLE puede USAR la memoria de zaelar (recall/remember, pieza serial que habla por
# HTTP con el server vivo → preserva el escritor único) y REPORTAR su progreso al FlashBrain (`hbnote`). Bash
# ACOTADO solo a esos CLIs (no un Bash abierto). Se añaden a la allowlist salvo en turnos no confiables.
_MEM_TOOLS = [
    "Bash(python -m nucleo.mem_cli:*)", "Bash(.venv/bin/python -m nucleo.mem_cli:*)",
    "Bash(python -m nucleo.agent_report:*)", "Bash(.venv/bin/python -m nucleo.agent_report:*)",
    "Bash(python -m nucleo.nav_cli:*)", "Bash(.venv/bin/python -m nucleo.nav_cli:*)",   # F3: conducir el navegador
]


def _find_claude() -> str:
    """Localiza el CLI de Claude Code robustamente — el PATH del server (lanzado desde un venv) suele no tener
    el bin de nvm donde vive `claude`. Env override → PATH → ubicaciones habituales. (Copia propia: el SlowBrain
    no debe depender de `widgets/generator`.)"""
    cand = os.getenv("CLAUDE_BIN")
    if cand and os.path.exists(os.path.expanduser(cand)):
        return os.path.expanduser(cand)
    found = shutil.which("claude")
    if found:
        return found
    for pat in ("~/.nvm/versions/node/*/bin/claude", "/opt/homebrew/bin/claude",
                "/usr/local/bin/claude", "~/.local/bin/claude"):
        hits = glob.glob(os.path.expanduser(pat))
        if hits:
            return sorted(hits)[-1]
    return ""


def _extract_output(stdout: str) -> str:
    """`claude -p --output-format json` emite un objeto con el resultado en `result`. Toleramos texto plano
    (si el formato cambia) devolviendo el stdout crudo."""
    s = (stdout or "").strip()
    if not s:
        return ""
    try:
        obj = json.loads(s)
    except Exception:
        return s
    if isinstance(obj, dict):
        for key in ("result", "response", "text", "content"):
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return json.dumps(obj, ensure_ascii=False)
    return s


class ClaudeCodeAgent(CodeAgent):
    name = "claude_code"

    async def run(self, prompt: str, *, spec: "RunSpec") -> "RunResult":
        """Corre un Claude Code headless atómico. Prompt por STDIN (claude trunca prompts posicionales largos).
        Nunca lanza: cualquier fallo (CLI ausente, timeout, salida no-cero) vuelve como `RunResult.ok=False`."""
        claude = _find_claude()
        if not claude:
            return RunResult(ok=False, error="Claude Code CLI no encontrado (define CLAUDE_BIN)")

        cmd = [claude, "-p", "--permission-mode", "acceptEdits", "--output-format", "json"]
        # Política de tools: input no confiable → SIN ninguna; si no, la allowlist del spec o el default de lectura.
        if spec.deny_tools:
            tools: list[str] = []
        else:
            tools = spec.tools if spec.tools is not None else list(_DEFAULT_TOOLS)
            # Puente de memoria disponible para todo turno confiable (salvo que el caller lo desactive con
            # spec.env["ZAELAR_NO_MEM_TOOL"]). Serial y acotado — pide/guarda datos y sigue (V2-036).
            if not (spec.env or {}).get("ZAELAR_NO_MEM_TOOL"):
                tools = list(tools) + [t for t in _MEM_TOOLS if t not in tools]
        cmd += ["--allowedTools", " ".join(tools)]      # cadena vacía = sin herramientas
        if spec.model:                                  # MODELO POR INVOCACIÓN (jamás una env global)
            cmd += ["--model", spec.model]

        env = dict(os.environ)
        env["PATH"] = os.path.dirname(claude) + os.pathsep + env.get("PATH", "")
        env.update(spec.env or {})
        cwd = spec.cwd or _ZAELAR

        logger.info(f"slowbrain: ClaudeCodeAgent run (model={spec.model or 'default'}, "
                    f"tools={tools}, deny={spec.deny_tools}, cwd={cwd})")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=cwd, env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:  # noqa: BLE001
            return RunResult(ok=False, error=f"no se pudo arrancar el agente: {e}")

        try:
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")), timeout=spec.timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return RunResult(ok=False, error=f"el agente superó el timeout ({spec.timeout}s)")
        except Exception as e:  # noqa: BLE001
            return RunResult(ok=False, error=f"fallo ejecutando el agente: {e}")

        stdout = (out_b or b"").decode("utf-8", "replace")
        stderr = (err_b or b"").decode("utf-8", "replace")
        rc = proc.returncode or 0
        if rc != 0:
            logger.warning(f"slowbrain: claude salió {rc}: {stderr[:300]}")
            return RunResult(ok=False, output=_extract_output(stdout),
                             error=stderr[:500] or f"claude salió con código {rc}",
                             meta={"returncode": rc, "model": spec.model})
        return RunResult(ok=True, output=_extract_output(stdout),
                         meta={"returncode": rc, "model": spec.model})
