"""nucleo/workers/providers/claude.py — backend `ClaudeCodeSession` (Claude Code headless en STREAMING). V2-038.

Sesión VIVA de Claude Code sobre el transporte stream-json (`claude --print --input-format stream-json
--output-format stream-json`): el proceso NO muere tras el primer turno — se le inyectan turnos por stdin y emite
eventos por stdout, que este backend PARSEA y traduce al vocabulario NORMALIZADO `WorkerEvent` (agnosticidad O1).

Reglas heredadas del adaptador one-shot (V2-036) que se conservan:
  - **Modelo POR INVOCACIÓN** (`--model spec.model`, jamás env global).
  - **Tool-gating** por `--allowedTools`; `deny_tools` (input no confiable, V2-010) → SIN tools NI bridges (§v3·P).
  - Localización robusta del CLI (`_find_claude`).
Novedades V2-038:
  - `start_new_session=True` → poder matar el GRUPO de procesos (el `claude` tiene hijos: cada Bash tool), §v2·D.
  - Derivación de eventos ACOTADA (§v2·E·Q3): `tool_use`→`phase`, `result`→`result`, ciclo→`error`/`done`;
    el texto `assistant` NO se convierte en `say` (monólogo interno). `say`/`ask` son SIEMPRE explícitos (bridges).
  - Captura del `session_id` NATIVO (para `--resume` futuro, Q6).
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import shutil
import signal
import sys

from loguru import logger

from ..base import WorkerBackend, WorkerEvent, WorkerSpec
from . import spawned as _spawned  # a worker's session id marks every request it sends
from ..tool_steps import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    _QUOTED_RE, _URL_RE, _bash_step, _cmd_head, _nav_target, _quoted, _short_path, _tool_phase, _tool_step,
    _url_in)

_ZAELAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # providers/ → engine
# `Write` is here because OUR prompt requires it: bridge payloads go by `@file` since V2-379. Measured 2026-08-28
# (`find-best-hotel-city__us`): without it headless asked a permission nobody grants and the bridge could not read
# `informe.json`. Only `Write` — not `Edit`/`NotebookEdit`: a throwaway workdir needs no edits. `deny_tools` → none.
_DEFAULT_TOOLS = ["Read", "Write"]


def worker_shell(current: str) -> str:
    """The shell the worker's Bash tool runs in: bash, never zsh. zsh ABORTS a command whose unquoted `?` or `*`
    matches no file — `cli.nav goto https://www.amazon.com/s?k=27+inch+4k+monitor` failed with «no matches found»
    (demo run, 2026-09-26) where bash passes the word through. The operator's login shell is his; this is ours."""
    for sh in ("/bin/bash", "/usr/bin/bash"):
        if os.path.exists(sh):
            return sh
    return current
# Agnostic BRIDGES a TRUSTED worker may use (Bash bounded to these CLIs, never open): hbmem/hbnote/hbweb (V2-036),
# hbask/hbact (V2-038), hbwidget; omitted with deny_tools (§v3·P). The allowlist matches by LITERAL PREFIX, so every
# interpreter spelling is declared. Measured 2026-08-02: bare `python` does not exist here and the worker spent most
# of a 5-minute search trying spellings and narrating «the bridges keep asking for approval».
_INTERPRETERS = ("python", "python3", ".venv/bin/python", ".venv/bin/python3",
                 os.path.join(_ZAELAR, ".venv", "bin", "python"))
# V2-778 F0: plus the one `bridge_python()` DICTATES — outside a checkout venv that is `sys.executable`, which no
# spelling above matched, so the worker got a command its own allowlist would stop.
if (sys.executable or "").strip() and sys.executable.strip() not in _INTERPRETERS:
    _INTERPRETERS += (sys.executable.strip(),)
_BRIDGES = ("cli.mem", "cli.report", "cli.nav", "cli.bridge", "cli.widget", "cli.mesh")
_BRIDGE_TOOLS = [f"Bash({py} -m nucleo.{mod}:*)" for mod in _BRIDGES for py in _INTERPRETERS]


def builtin_tool_names(tools) -> list[str]:
    """The built-in tool NAMES behind an allowlist: `Bash(python -m nucleo.x:*)` → `Bash`, `Read` → `Read`.
    Sorted and unique, so the argv is stable; empty in → empty out (`--tools ""` disables every tool)."""
    return sorted({str(t).split("(", 1)[0].strip() for t in (tools or []) if str(t).strip()})


def bridge_python() -> str:
    """El intérprete EXACTO con el que el worker debe invocar los puentes: el del propio servidor (`sys.executable`,
    absoluto y garantizado), o `.venv/bin/python` si por lo que sea no resuelve. Se le da MASTICADO en el prompt y
    en `ZAELAR_PY` para que no tenga que adivinarlo — adivinar es lo que le costaba los minutos."""
    exe = (sys.executable or "").strip()
    if exe and os.path.exists(exe):
        return exe
    return os.path.join(_ZAELAR, ".venv", "bin", "python")
# límite de buffer de línea del stdout (un tool_use grande puede pasar de 64KB, el default de StreamReader).
_STREAM_LIMIT = int(os.getenv("WORKER_STREAM_LIMIT", str(16 * 1024 * 1024)))


# What a DEV worker's env may carry — an allowlist: what is not named does not travel (V2-601 T-09). ZAELAR_* stays
# whole, plus the process basics the CLI needs and the ONE credential its tier resolved; no other API key.
_DEV_ENV_KEEP = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TERM", "SHELL", "USER", "LOGNAME",
                 "PYTHONPATH", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
                 "ANTHROPIC_CUSTOM_HEADERS",
                 "NO_PROXY", "HTTP_PROXY", "HTTPS_PROXY")


# A worker's endpoint comes from `spec.env` or the provider chain — NEVER the inherited process env. Measured
# 2026-09-28 (demo A1): an engine restarted from a Claude Code shell inherited `ANTHROPIC_BASE_URL`, the chain was
# skipped, `glm-5.3` was asked of Anthropic, and every errand died in 2 s («issue with the selected model»).
_HOST_ROUTING = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL", "CLAUDECODE")
_HOST_ROUTING_PREFIXES = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_")


def _without_host_routing(env: dict) -> dict:
    return {k: v for k, v in env.items()
            if k not in _HOST_ROUTING and not k.startswith(_HOST_ROUTING_PREFIXES)}


def _dev_env_allowlist(env: dict) -> dict:
    return {k: v for k, v in env.items() if k in _DEV_ENV_KEEP or k.startswith("ZAELAR_")}


def _user_msg(text: str) -> bytes:
    """Una línea stream-json de mensaje de usuario (turno inicial o inyección)."""
    return (json.dumps({"type": "user", "message": {"role": "user", "content": text}},
                       ensure_ascii=False) + "\n").encode("utf-8")


# The two long halves of the session live beside it (start/pump, the stream reader); the class names them.
from nucleo.workers.providers import claude_map as _cmap, claude_start as _cst  # noqa: E402


class ClaudeCodeSession(WorkerBackend):
    name = "claude_code"

    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._q: asyncio.Queue[WorkerEvent] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._task_id = ""
        self._native_sid = ""
        self._model = ""          # modelo POR INVOCACIÓN (de spec o resuelto del init) — viaja en los eventos (V2-048)
        self._done = False
        self._stdin_closed = False
        self._paused = False
        self._tier: dict | None = None   # escalón de proveedor con el que arrancó (para culpar al correcto si cae)
        self._ctx_tokens = 0             # context size of the LAST message (see `_ctx_size`) — the supervisor
                                         # watches it to compact BEFORE the ceiling (incident 2026-08-18)
        self._real_model = ""            # the model the provider says it ACTUALLY ran, when it says so: `_model`
                                         # above is the ALIAS we asked for (2026-08-18: `claude-opus-4-8[1m]`
                                         # recorded for a run `glm-4.7` performed)
        # EVIDENCE attribution: `tool_use_id` → its step; `_last_step` is the fallback when no id is sent.
        self._steps_by_id: dict[str, dict] = {}
        self._last_step: dict = {}

    start = _cst.start

    async def send(self, text: str) -> None:
        """Inyecta un turno por stdin (vía SECUNDARIA; la principal es piggyback en bridges, §v2·A)."""
        p = self._proc
        if p is None or p.stdin is None or self._stdin_closed or not self.alive:
            return
        try:
            p.stdin.write(_user_msg(text))
            await p.stdin.drain()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._task_id}]: send() falló: {e}")

    async def events(self):
        while True:
            ev = await self._q.get()
            yield ev
            if ev.type == "done":
                return

    async def stop(self, *, grace: float = 3.0) -> None:
        """Cierra stdin (fin de entrada) → SIGTERM al GRUPO → espera grace → SIGKILL. Nunca lanza."""
        p = self._proc
        if p is None:
            return
        try:
            if p.stdin and not self._stdin_closed:
                self._stdin_closed = True
                try:
                    p.stdin.close()
                except Exception:
                    pass
            if p.returncode is not None:
                return
            self._killpg(signal.SIGTERM)
            try:
                await asyncio.wait_for(p.wait(), timeout=grace)
                return
            except asyncio.TimeoutError:
                pass
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
            os.killpg(os.getpgid(p.pid), sig)   # mata el GRUPO (el claude + sus hijos Bash)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                p.send_signal(sig)              # fallback: solo el padre
            except Exception:
                pass

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None and not self._done

    # ── V2-065: PAUSE ≠ kill (operator's ⏻). SIGSTOP freezes the process GROUP in place, pipes and buffers intact,
    # so SIGCONT resumes losing nothing; `start_new_session=True` gives the group (same mechanism as `_killpg`).
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

    _pump = _cst._pump

    _map = _cmap._map
        # el resto (system de cierre, etc.) → sin evento.

    # ── SEAM for backends with the SAME wire format (2026-08-13) ─────────────────────────────────────────────
    # Grok Build's `streaming-messages-json` is Claude Code's stream-json vocabulary with other tool names and
    # evidence shapes. `_map` calls these three methods via `self`, so `GrokSession` only overrides the vocabulary.
    def _tool_step(self, tool: str, tin: dict | None = None):
        return _tool_step(tool, tin)

    def _tool_phase(self, tool: str, tin: dict | None = None) -> str:
        return _tool_phase(tool, tin)

    def _result_text(self, content) -> str:
        return _result_text(content)

    _steps = _cmap._steps

    async def _fail_fast(self, message: str) -> None:
        """End the session as an error before any process starts (no CLI, or no routed tier in a container)."""
        await self._q.put(self._ev("error", message=message, fatal=True))
        await self._q.put(self._ev("done"))
        self._done = True

    def _ev(self, etype: str, **data) -> WorkerEvent:
        return WorkerEvent(task_id=self._task_id, type=etype, data=data, backend=self.name)


#: Public name for the widget generator, which strips the same host routing (widgets/generator.py).
without_host_routing = _without_host_routing

from nucleo.workers.providers.claude_start import (  # noqa: E402,F401
    _find_claude, _ctx_size, _mark_the_worker_env)
from nucleo.workers.providers.claude_map import (  # noqa: E402,F401
    _result_text)
