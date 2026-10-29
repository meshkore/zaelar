"""nucleo/workers/providers/codex.py — backend `CodexSession` (Codex CLI headless en JSONL). V2-038.

Adaptador REAL (2026-08-12; hasta hoy era un stub que emitía «no implementado» y cerraba — con el proveedor puesto
a `codex` en la config, el operador se quedaba SIN workers y el síntoma era una tarea que moría al instante).

Transporte: `codex exec --json`, que escribe **JSONL** por stdout. La agnosticidad (O1) se cumple traduciendo ese
vocabulario nativo al NORMALIZADO `WorkerEvent`, igual que `claude_session` hace con stream-json:

    thread.started   → spawned(native_session_id=<thread_id>)   ← el id con el que se REANUDA (`exec resume`)
    item.started     → step        (la fila del panel: dónde trabaja y sobre qué)
    item.completed   → step_result (la EVIDENCIA: qué le contestaron) / note (su narración)
    turn.completed   → result + done, con `usage` REAL → Energy (session.py::_finish lo tariffa)
    error/turn.failed→ error(fatal=True) + done

Diferencias de FONDO con Claude Code, que el operador debe conocer (no son detalles de implementación):

1. **NO hay allowlist de tools.** Claude Code acota `Bash` a los puentes (`--allowedTools "Bash(python -m
   nucleo.cli.mem:*)"…`), que es el invariante del ESCRITOR ÚNICO de la memoria. Codex no tiene ese eje: tiene
   MODOS de sandbox (`read-only` / `workspace-write` / `danger-full-access`). Para trabajar headless hace falta
   `workspace-write` (verificado: en ese modo ejecuta comandos SIN pedir aprobación, que en headless nadie daría),
   y eso es un shell COMPLETO. Un worker de Codex tiene por tanto MÁS radio de acción que uno de Claude Code.
   Se usa el modo más conservador que funciona; NUNCA `--dangerously-bypass-approvals-and-sandbox`.
2. **Por eso `deny_tools` y `kind="dev"` se RECHAZAN aquí** (fail-closed): los dos existen justo para acotar a un
   worker que digiere entrada NO confiable (V2-010) o que corre por encargo de un peer de cluster, y esa
   acotación no es expresable en Codex. Se emite un error CLARO que nombra el backend correcto, en vez de correr
   con menos contención de la que el llamador pidió.
3. **`send()` no puede inyectar en vivo**: `codex exec` no lee turnos por stdin como el transporte stream-json.
   No es un agujero: la vía PRINCIPAL de inyección es el **piggyback** en las respuestas de los puentes
   (`/api/worker/act`, §v2·A), que es HTTP y por tanto agnóstica del backend — un «además, en verde» le llega al
   worker de Codex la próxima vez que toca un puente, igual que al de Claude Code.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import shutil
import signal

from loguru import logger

from ..base import WorkerBackend, WorkerEvent, WorkerSpec
from . import spawned as _spawned  # a worker's session id marks every request it sends

_ZAELAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # providers/ → engine
_STREAM_LIMIT = int(os.getenv("WORKER_STREAM_LIMIT", str(16 * 1024 * 1024)))

# Modo de sandbox. `workspace-write` es el mínimo con el que un turno headless llega a ejecutar algo (ver nota 1);
# `ZAELAR_CODEX_SANDBOX` deja al power-user bajarlo a `read-only` para una tarea de solo lectura.
_SANDBOX = (os.getenv("ZAELAR_CODEX_SANDBOX") or "workspace-write").strip()

# NETWORK: Codex's sandbox cuts it by default, and ALL our bridges speak HTTP to the live server (127.0.0.1:43917).
# First live test (2026-08-12): the worker ran blind, with no memory or progress reports. The sandbox is
# all-or-nothing, so this opens the internet too (as WebSearch/WebFetch already do). Off: `ZAELAR_CODEX_NETWORK=0`.
_NET_ARGS = ([] if (os.getenv("ZAELAR_CODEX_NETWORK") or "1").strip() in ("0", "false", "no")
             else ["-c", "sandbox_workspace_write.network_access=true"])


_VER_RE = re.compile(r"(\d+\.\d+\.\d+)")


from nucleo.workers.providers import codex_map as _xmap, codex_start as _xst  # noqa: E402


class CodexSession(WorkerBackend):
    name = "codex"

    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._q: asyncio.Queue[WorkerEvent] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._task_id = ""
        self._native_sid = ""
        self._model = ""
        self._done = False
        self._paused = False
        self._last_message = ""      # último `agent_message` = el RESULTADO (Codex no marca cuál es el final)
        self._usage: dict = {}
        self._failed = ""            # texto del error si el turno falló (para `result.ok=False`)

    start = _xst.start

    async def _fail(self, message: str) -> None:
        """Muere DICIENDO por qué (con su `done`, para que la sesión cierre limpia). Un backend que se cae en
        silencio deja al operador esperando un resultado que no va a llegar."""
        logger.warning(f"worker[{self._task_id}]: codex: {message}")
        await self._q.put(self._ev("error", message=message, fatal=True))
        await self._q.put(self._ev("done"))
        self._done = True

    async def send(self, text: str) -> None:
        """No-op DELIBERADO: `codex exec` no acepta turnos nuevos por stdin (nota 3 de la cabecera). La inyección
        llega por el piggyback de los puentes, que es agnóstico del backend. Se registra para que un refinamiento
        que no se entregue no sea invisible."""
        logger.info(f"worker[{self._task_id}]: codex no admite inyección en vivo; «{text[:60]}» irá por piggyback")

    async def events(self):
        while True:
            ev = await self._q.get()
            yield ev
            if ev.type == "done":
                return

    async def stop(self, *, grace: float = 3.0) -> None:
        """SIGTERM al GRUPO → espera grace → SIGKILL. Nunca lanza. Calca `claude_session.stop`."""
        p = self._proc
        if p is None:
            return
        try:
            if p.returncode is None:
                self._killpg(signal.SIGTERM)
                try:
                    await asyncio.wait_for(p.wait(), timeout=grace)
                except asyncio.TimeoutError:
                    pass
            # V2-831 T-27 — the GROUP is reaped whatever the leader did: a child it left behind (a shell, a bridge
            # call, a subprocess) used to outlive the errand when the leader had already exited.
            self._killpg(signal.SIGKILL)
            try:
                await asyncio.wait_for(p.wait(), timeout=2.0)
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._task_id}]: stop() falló: {e}")

    def _killpg(self, sig) -> None:
        p = self._proc
        if p is None or p.pid is None:
            return
        try:
            os.killpg(p.pid, sig)   # the GROUP (start_new_session: its id IS the leader's pid, even after it exits)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                p.send_signal(sig)
            except Exception:
                pass

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None and not self._done

    # V2-065: pausar ≠ matar. Mismo mecanismo que Claude Code — SIGSTOP congela el grupo donde estaba.
    def pause(self) -> bool:
        if not self.alive or self._paused:
            return False
        self._killpg(signal.SIGSTOP)
        self._paused = True
        return True

    def resume(self) -> bool:
        if not self._paused:
            return False
        self._killpg(signal.SIGCONT)
        self._paused = False
        return True

    @property
    def paused(self) -> bool:
        return self._paused

    def native_session_id(self) -> str:
        return self._native_sid

    _pump = _xst._pump

    _map = _xmap._map
        # turn.started y el resto → sin evento (ruido de protocolo).

    _map_item = _xmap._map_item

    def _ev(self, etype: str, **data) -> WorkerEvent:
        return WorkerEvent(task_id=self._task_id, type=etype, data=data, backend=self.name)


def _short_path(p) -> str:
    p = str(p or "").strip()
    if not p:
        return ""
    parts = p.rstrip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) > 1 else p


def _cmd_head(cmd: str) -> str:
    """El comando SIN el envoltorio del shell que Codex le pone (`/bin/zsh -lc '…'`), que en la fila del panel
    ocupa todo el ancho y no dice nada."""
    c = (cmd or "").strip()
    m = re.match(r"""^\S*(?:sh|zsh|bash)\s+-\S*c\s+(['"])(.*)\1$""", c, re.S)
    if m:
        c = m.group(2)
    return " ".join(c.split()[:8])[:120]

from nucleo.workers.providers.codex_start import (  # noqa: E402,F401
    find_codex, detect, _stderr_reason)
from nucleo.workers.providers.codex_map import (  # noqa: E402,F401
    _URL_RE, _item_step, _item_result_text)
