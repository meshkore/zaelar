"""nucleo/workers/claude_session.py — backend `ClaudeCodeSession` (Claude Code headless en STREAMING). V2-038.

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

from loguru import logger

from .base import WorkerBackend, WorkerEvent, WorkerSpec

_ZAELAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_TOOLS = ["Read"]
# PUENTES agnósticos que un worker CONFIABLE puede usar (Bash acotado a estos CLIs, nunca un Bash abierto).
# hbmem/hbnote/hbweb (V2-036) + hbask/hbact (V2-038, plano request/response). Se omiten si deny_tools (§v3·P).
_BRIDGE_TOOLS = [
    "Bash(python -m nucleo.mem_cli:*)", "Bash(.venv/bin/python -m nucleo.mem_cli:*)",
    "Bash(python -m nucleo.agent_report:*)", "Bash(.venv/bin/python -m nucleo.agent_report:*)",
    "Bash(python -m nucleo.nav_cli:*)", "Bash(.venv/bin/python -m nucleo.nav_cli:*)",
    "Bash(python -m nucleo.worker_bridge:*)", "Bash(.venv/bin/python -m nucleo.worker_bridge:*)",
    "Bash(python -m nucleo.widget_cli:*)", "Bash(.venv/bin/python -m nucleo.widget_cli:*)",   # hbwidget (V2-061)
]
# límite de buffer de línea del stdout (un tool_use grande puede pasar de 64KB, el default de StreamReader).
_STREAM_LIMIT = int(os.getenv("WORKER_STREAM_LIMIT", str(16 * 1024 * 1024)))


def _find_claude() -> str:
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


def _user_msg(text: str) -> bytes:
    """Una línea stream-json de mensaje de usuario (turno inicial o inyección)."""
    return (json.dumps({"type": "user", "message": {"role": "user", "content": text}},
                       ensure_ascii=False) + "\n").encode("utf-8")


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

    # ── ciclo de vida ─────────────────────────────────────────────────────────────────────────────────────
    async def start(self, prompt: str, *, spec: "WorkerSpec") -> None:
        self._task_id = spec.task_id or ""
        self._model = spec.model or ""
        claude = _find_claude()
        if not claude:
            await self._q.put(self._ev("error", message="Claude Code CLI no encontrado (define CLAUDE_BIN)",
                                       fatal=True))
            await self._q.put(self._ev("done"))
            self._done = True
            return

        cmd = [claude, "--print", "--verbose",
               "--input-format", "stream-json", "--output-format", "stream-json",
               "--permission-mode", "acceptEdits"]
        # V2-049 CONTINUIDAD: reanuda el razonamiento de un worker anterior de la MISMA gestión (no empieza de cero →
        # no re-navega ni re-teclea lo ya hecho; recuerda qué falló). Fail-soft: si `--resume` no valida el id, el
        # CLI arranca sesión nueva — el resto de la continuidad (misma pestaña + datos en memoria + prompt «reanudas»
        # + visión) igualmente evita el reinicio ciego.
        if spec.resume_sid:
            cmd += ["--resume", spec.resume_sid]
            logger.info(f"worker[{spec.task_id}]: REANUDA sesión nativa {spec.resume_sid[:12]}…")
        if spec.deny_tools:
            tools: list[str] = []
        else:
            tools = spec.tools if spec.tools is not None else list(_DEFAULT_TOOLS)
            if not (spec.env or {}).get("ZAELAR_NO_BRIDGE_TOOLS"):
                tools = list(tools) + [t for t in _BRIDGE_TOOLS if t not in tools]
        cmd += ["--allowedTools", " ".join(tools)]
        if spec.model:
            cmd += ["--model", spec.model]
        if spec.extra_args:
            cmd += list(spec.extra_args)

        env = dict(os.environ)
        env["PATH"] = os.path.dirname(claude) + os.pathsep + env.get("PATH", "")
        env.update(spec.env or {})
        # Backend de razonamiento EXTERNO (2026-07-31): si §code_agent.base_url apunta a un endpoint Anthropic-
        # compatible (Z.AI GLM coding plan, "una API para usar desde Claude Code"), el worker `claude` lo usa vía
        # ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN. OFF por defecto (base_url vacío → cuenta Anthropic normal).
        # El token se resuelve del credential store POR ENDPOINT (z.ai → Z_AI_API_KEY), nunca desde config JSON.
        # spec.env (del dispatch) manda si ya lo trae; esto es el default config-driven. Fail-open (nunca rompe).
        if "ANTHROPIC_BASE_URL" not in env:
            try:
                from config import v2 as _v2
                _ca = _v2.get("code_agent") or {}
                _base = (_ca.get("base_url") or "").strip()
                if _base:
                    _tok = (_ca.get("api_key") or "").strip()
                    if not _tok and "z.ai" in _base.lower():
                        _tok = os.getenv("Z_AI_API_KEY", "")
                    if _tok:
                        env["ANTHROPIC_BASE_URL"] = _base
                        env["ANTHROPIC_AUTH_TOKEN"] = _tok
                        # el CLI avisa si conviven API key + base_url; quitamos la key de Anthropic para no ambiguar.
                        env.pop("ANTHROPIC_API_KEY", None)
            except Exception:
                pass
        # marcadores para el barrido de huérfanos al arrancar (§v2·D) + auth de bridges por-tarea (§v2·D).
        env["ZAELAR_WORKER"] = "1"
        env["ZAELAR_TASK_ID"] = spec.task_id or ""
        if spec.token:
            env["ZAELAR_TASK_TOKEN"] = spec.token
        cwd = spec.cwd or _ZAELAR

        logger.info(f"worker[{self._task_id}]: ClaudeCodeSession start (model={spec.model or 'default'}, "
                    f"tools={len(tools)}, deny={spec.deny_tools}, cwd={cwd})")
        preexec = None
        if spec.kind == "dev" and os.name != "nt":
            # topes de recursos (memoria/nproc/fsize, SIN límite de CPU/pared) — auditoría 2026-07-26, defensa en
            # profundidad además del guard de confinamiento de rutas (--settings, ver spec.extra_args).
            try:
                from nucleo import sandbox as _sandbox
                preexec = _sandbox.dev_worker_rlimits()
            except Exception:
                preexec = None
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=cwd, env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,           # grupo propio → killpg (§v2·D)
                limit=_STREAM_LIMIT,
                preexec_fn=preexec,
            )
        except Exception as e:  # noqa: BLE001
            await self._q.put(self._ev("error", message=f"no se pudo arrancar el worker: {e}", fatal=True))
            await self._q.put(self._ev("done"))
            self._done = True
            return

        # turno inicial por stdin (la sesión queda VIVA para inyecciones posteriores).
        try:
            self._proc.stdin.write(_user_msg(prompt))
            await self._proc.stdin.drain()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._task_id}]: no pude escribir el prompt inicial: {e}")
        self._reader_task = asyncio.create_task(self._pump(), name=f"worker-pump-{self._task_id}")

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

    # ── V2-065: PAUSAR ≠ matar (botón ⏻ del operador). SIGSTOP congela el GRUPO de procesos en el sitio exacto
    # donde estaba (el `claude` y sus hijos Bash) — el kernel simplemente deja de darles CPU; los pipes de
    # stdin/stdout quedan abiertos y con su buffer intacto, así que SIGCONT lo continúa sin perder nada de lo que
    # ya había en vuelo. `start_new_session=True` (arriba) ya nos da el grupo propio que esto necesita — mismo
    # mecanismo que `_killpg`, sin matar nada.
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

    # ── lector: stream-json nativo → WorkerEvent ──────────────────────────────────────────────────────────
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
                    continue                     # línea no-JSON → ignorar (robusto ante ruido)
                for ev in self._map(obj):
                    await self._q.put(ev)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._task_id}]: pump error: {e}")
        finally:
            # cierre: emite done UNA vez (con error si el proceso salió mal y no hubo result).
            try:
                await p.wait()
            except Exception:
                pass
            rc = p.returncode or 0
            if not self._done:
                if rc not in (0, None):
                    stderr = b""
                    try:
                        stderr = await p.stderr.read()
                    except Exception:
                        pass
                    await self._q.put(self._ev("error", message=(stderr.decode("utf-8", "replace")[:400]
                                                                 or f"claude salió {rc}"), fatal=True))
                await self._q.put(self._ev("done"))
                self._done = True

    def _map(self, obj: dict):
        """Traduce UN objeto stream-json de Claude a 0..N WorkerEvent. Conservador: lo que no encaja, se ignora."""
        t = obj.get("type")
        if t == "system" and obj.get("subtype") == "init":
            self._native_sid = obj.get("session_id") or ""
            self._model = self._model or obj.get("model") or ""   # init trae el modelo RESUELTO (si spec venía vacío)
            yield self._ev("spawned", native_session_id=self._native_sid, model=self._model)
            return
        if t == "assistant":
            # Derivación de PROGRESO (§v2·E·Q3): cada tool_use → una fase coarse (rec.phase, para el prompt) Y un
            # `step` RICO para la observabilidad (V2-048): DÓNDE trabaja (web/memoria/navegador/código/archivo/zaelar)
            # + QUÉ usa (la tool + su objetivo concreto: URL, query, slot, fichero, ref del navegador). El texto
            # assistant sigue SIN convertirse en say (monólogo interno).
            msg = obj.get("message") or {}
            for block in (msg.get("content") or []):
                if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                    continue
                name = block.get("name") or ""
                tin = block.get("input") or {}
                step = _tool_step(name, tin)
                lbl = _tool_phase(name, tin)
                if lbl:                          # "" = no pisar la fase (p.ej. hbnote la fija él mismo, más rica)
                    # quiet=True cuando hay `step`: el step ES la fila del panel → no duplicar con la fase coarse,
                    # pero rec.phase (el prompt "PROCESOS DE FONDO") SÍ se actualiza con la coarse.
                    yield self._ev("phase", label=lbl, quiet=bool(step))
                if step:
                    yield self._ev("step", tool=name, model=self._model, **step)
            return
        if t == "result":
            summary = obj.get("result") or ""
            ok = obj.get("subtype") == "success" and not obj.get("is_error")
            usage = obj.get("usage") or {}
            yield self._ev("result", summary=str(summary), ok=bool(ok), usage=usage,
                           cost=obj.get("total_cost_usd"), model=self._model)
            yield self._ev("done")
            self._done = True
            return
        # user (tool_result), etc. → sin evento (ruido interno).

    def _ev(self, etype: str, **data) -> WorkerEvent:
        return WorkerEvent(task_id=self._task_id, type=etype, data=data, backend=self.name)


def _tool_phase(tool: str, tin: dict | None = None) -> str:
    """Etiqueta de fase humana a partir de la tool que el worker acaba de invocar. Para Bash mira el COMANDO
    (demo 2026-07-14: un worker web emitía «ejecutando un paso…» perpetuo — la tarjeta/chip no contaban nada).
    Devuelve "" para NO emitir fase (hbnote: la fase legible la fija el propio reporte, no la pisamos)."""
    t = (tool or "").lower()
    if "webfetch" in t or "websearch" in t:
        return "buscando en la web…"
    if t.startswith("bash"):
        c = str((tin or {}).get("command") or "").lower()
        if "nav_cli" in c:
            for verb, label in (("snapshot", "mirando la página…"), ("navigate", "abriendo una página…"),
                                ("click", "interactuando con la página…"), ("type", "escribiendo en la página…"),
                                ("scroll", "recorriendo la página…"), ("extract", "recogiendo resultados…")):
                if f" {verb}" in c:
                    return label
            return "conduciendo el navegador…"
        if "agent_report" in c:
            return ""                                   # la fase la pone el propio hbnote (más rica) — no pisar
        if "mem_cli" in c:
            return "consultando la memoria…"
        if "widget_cli" in c:
            return "actualizando un widget…"
        if "worker_bridge" in c:
            return "consultando con zaelar…"
        return "ejecutando un paso…"
    if t in ("write", "edit", "multiedit"):
        return "escribiendo cambios…"
    if t == "read":
        return "leyendo…"
    return f"usando {tool}…" if tool else "trabajando…"


# ── V2-048: observabilidad RICA — cada tool_use → DÓNDE + QUÉ concreto ────────────────────────────────────────
# El one-shot solo dejaba una fase coarse ("consultando la memoria…"); el operador quiere ver, por paso, en qué
# LUGAR trabaja el worker y qué OBJETIVO concreto toca. `_tool_step` extrae esa estructura del tool_use nativo (que
# el motor stream-json ya nos da entero) SIN tocar los puentes: para Bash mira el COMANDO y lo atribuye al puente
# (nav_cli→navegador, mem_cli→memoria, worker_bridge→zaelar); para las tools nativas mira sus args (url/query/path).
_URL_RE = re.compile(r"https?://[^\s'\"]+")
_QUOTED_RE = re.compile(r"\"([^\"]{1,200})\"|'([^']{1,200})'")


def _url_in(cmd: str) -> str:
    m = _URL_RE.search(cmd or "")
    return m.group(0) if m else ""


def _quoted(cmd: str) -> str:
    """Primer trozo entre comillas (simples o dobles) — el argumento textual típico de los CLIs puente."""
    m = _QUOTED_RE.search(cmd or "")
    return ((m.group(1) or m.group(2)) if m else "").strip()


def _short_path(p) -> str:
    p = str(p or "").strip()
    if not p:
        return ""
    parts = p.rstrip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) > 1 else p


def _cmd_head(cmd: str) -> str:
    return " ".join((cmd or "").split()[:6])[:100]


def _nav_target(cmd: str, verb: str) -> str:
    url = _url_in(cmd)
    if verb == "navigate":
        return f"→ {url}" if url else (f"→ {_quoted(cmd)}" if _quoted(cmd) else "")
    if verb in ("click", "scroll", "press"):
        m = re.search(rf"\b{verb}\s+(\S+)", cmd)
        return f"[{m.group(1)}]" if m else ""
    if verb == "type":
        q = _quoted(cmd)
        return f"«{q}»" if q else ""
    if verb == "extract":
        return "resultados"
    if verb == "snapshot":
        return "mira la página"
    return url or _quoted(cmd)


def _bash_step(cmd: str):
    """Un comando Bash acotado a un PUENTE → dónde/qué. Devuelve None para no emitir fila (agent_report)."""
    c = (cmd or "").lower()
    if "nav_cli" in c:
        verb = next((v for v in ("navigate", "click", "type", "scroll", "snapshot", "extract", "press", "back")
                     if re.search(rf"\b{v}\b", c)), "")
        return {"where": "navegador", "action": verb or "conduce", "target": _nav_target(cmd, verb)[:160]}
    if "agent_report" in c:
        return None                                  # la fase legible la fija el propio hbnote — no duplicar
    if "mem_cli" in c:
        if "recall" in c:
            return {"where": "memoria", "action": "recall", "target": _quoted(cmd)[:120]}
        if "remember" in c:
            m = re.search(r"--slot\s+(\S+)", cmd)
            slot = m.group(1) if m else ""
            tgt = (f"[{slot}] " if slot else "") + _quoted(cmd)
            return {"where": "memoria", "action": "guarda", "target": tgt[:120]}
        return {"where": "memoria", "action": "memoria", "target": ""}
    if "widget_cli" in c:
        m = re.search(r"widget_cli\s+(read|data|show|close)\s+([\w-]+)", cmd)
        verb = m.group(1) if m else "opera"
        wid = m.group(2) if m else ""
        return {"where": "widget", "action": verb, "target": wid[:80]}
    if "worker_bridge" in c:
        verb = next((v for v in ("ask", "act", "say") if re.search(rf"\b{v}\b", c)), "")
        return {"where": "zaelar", "action": verb or "consulta", "target": _quoted(cmd)[:120]}
    return {"where": "sistema", "action": "ejecuta", "target": _cmd_head(cmd)}


def _tool_step(tool: str, tin: dict | None = None):
    """Estructura RICA de un tool_use: {where, action, target}. `where` = el lugar del panel; `action`+`target` =
    qué hace y sobre qué. Devuelve None cuando no procede emitir fila (p.ej. hbnote fija su propia fase)."""
    t = (tool or "").lower()
    tin = tin or {}
    if "websearch" in t:
        return {"where": "web", "action": "web_search", "target": str(tin.get("query") or "")[:160]}
    if "webfetch" in t:
        return {"where": "web", "action": "fetch", "target": str(tin.get("url") or "")[:160]}
    if t == "read":
        return {"where": "archivo", "action": "lee", "target": _short_path(tin.get("file_path"))}
    if t in ("write", "edit", "multiedit"):
        return {"where": "codigo", "action": "escribe", "target": _short_path(tin.get("file_path"))}
    if t in ("grep", "glob"):
        return {"where": "archivo", "action": "busca",
                "target": str(tin.get("pattern") or tin.get("query") or "")[:120]}
    if t.startswith("bash"):
        return _bash_step(str(tin.get("command") or ""))
    if t.startswith("mcp__"):
        return {"where": "sistema", "action": tool.split("__")[-1] or tool, "target": ""}
    return {"where": "sistema", "action": tool or "paso", "target": ""}
