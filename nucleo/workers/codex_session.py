"""nucleo/workers/codex_session.py — backend `CodexSession` (Codex CLI headless en JSONL). V2-038.

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
   nucleo.mem_cli:*)"…`), que es el invariante del ESCRITOR ÚNICO de la memoria. Codex no tiene ese eje: tiene
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

from .base import WorkerBackend, WorkerEvent, WorkerSpec

_ZAELAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STREAM_LIMIT = int(os.getenv("WORKER_STREAM_LIMIT", str(16 * 1024 * 1024)))

# Modo de sandbox. `workspace-write` es el mínimo con el que un turno headless llega a ejecutar algo (ver nota 1);
# `ZAELAR_CODEX_SANDBOX` deja al power-user bajarlo a `read-only` para una tarea de solo lectura.
_SANDBOX = (os.getenv("ZAELAR_CODEX_SANDBOX") or "workspace-write").strip()

# RED: el sandbox de Codex la corta por defecto, y TODOS nuestros puentes hablan HTTP con el server vivo
# (127.0.0.1:43917) — memoria, navegador, widgets, preguntar al operador. Sin esto el worker arranca, trabaja y
# entrega… pero SIN memoria y sin poder reportar su fase; medido en la primera prueba en vivo (2026-08-12), donde
# narró «no puedo publicar el progreso en el puente local, la llamada queda bloqueada por permisos» y siguió a
# ciegas. Un worker que puede menos y no lo dice a gritos es peor que uno que falla.
# El sandbox de Codex es todo-o-nada con la red (no hay allowlist de hosts), así que esto abre internet, no solo el
# loopback. No es una clase de riesgo NUEVA —un worker de Claude Code ya tiene WebSearch/WebFetch— pero conviene
# tenerlo escrito. Apagable: `ZAELAR_CODEX_NETWORK=0` (worker sin puentes, para una tarea puramente local).
_NET_ARGS = ([] if (os.getenv("ZAELAR_CODEX_NETWORK") or "1").strip() in ("0", "false", "no")
             else ["-c", "sandbox_workspace_write.network_access=true"])


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


_VER_RE = re.compile(r"(\d+\.\d+\.\d+)")


def detect() -> dict:
    """¿Está Codex en ESTA máquina, con qué versión y con qué modelo por defecto? Lo consume el catálogo de
    proveedores de la config (`server/config_api.py`) para que la UI no ofrezca un proveedor que no existe aquí ni
    invente un modelo por defecto distinto del que el propio CLI usaría.

    Barato y sin red: `--version` (proceso local, ~50 ms) + una lectura del `config.toml`. Nunca lanza."""
    path = find_codex()
    out: dict = {"installed": bool(path), "path": path, "version": "", "default_model": ""}
    if not path:
        return out
    try:
        import subprocess
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=8)
        m = _VER_RE.search((r.stdout or "") + (r.stderr or ""))
        out["version"] = m.group(1) if m else ""
    except Exception:
        pass
    # El modelo por defecto REAL es el del `config.toml` del usuario, no uno que elijamos nosotros: si el operador
    # ya decidió cuál usa su Codex, la UI debe arrancar de ahí. Parseo mínimo (`model = "x"`) para no traer un
    # lector de TOML por una línea.
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

        codex = find_codex()
        if not codex:
            await self._fail("Codex CLI no encontrado (instálalo con `npm i -g @openai/codex` o define CODEX_BIN)")
            return

        cwd = spec.cwd or _ZAELAR
        cmd = [codex, "exec", "--json", "--skip-git-repo-check", "-s", _SANDBOX, "-C", cwd] + _NET_ARGS
        # CONTINUIDAD (V2-049): Codex reanuda por `exec resume <thread_id>`, no por un flag. El id es el
        # `thread.started` de la sesión anterior, que ya guardamos como `native_session_id`.
        if spec.resume_sid:
            cmd = [codex, "exec", "resume", spec.resume_sid, "--json", "--skip-git-repo-check",
                   "-s", _SANDBOX, "-C", cwd]
            logger.info(f"worker[{self._task_id}]: codex REANUDA hilo {spec.resume_sid[:12]}…")
        if spec.model:
            cmd += ["-m", spec.model]
        if spec.extra_args:
            cmd += list(spec.extra_args)
        cmd += ["-"]                     # el prompt entra por stdin (no por argv: un prompt largo revienta el límite)

        env = dict(os.environ)
        env["PATH"] = os.path.dirname(codex) + os.pathsep + env.get("PATH", "")
        env.update(spec.env or {})
        # Codex se autentica con SU propia sesión (`~/.codex/auth.json`) o con OPENAI_API_KEY — NO con la cadena de
        # relevo Anthropic-compatible de `providers.py`, que es de Claude Code. Se limpia lo que pudiera venir del
        # entorno del server para no confundir al CLI con credenciales que no son suyas.
        for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
            env.pop(k, None)
        env["ZAELAR_WORKER"] = "1"                    # marcador para el barrido de huérfanos (§v2·D)
        env["ZAELAR_TASK_ID"] = spec.task_id or ""
        if spec.token:
            env["ZAELAR_TASK_TOKEN"] = spec.token     # auth de los puentes por-tarea (§v2·D)

        logger.info(f"worker[{self._task_id}]: CodexSession start (model={spec.model or 'default'}, "
                    f"sandbox={_SANDBOX}, cwd={cwd})")
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=cwd, env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,               # grupo propio → killpg mata al codex Y a sus hijos (§v2·D)
                limit=_STREAM_LIMIT,
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
            os.killpg(os.getpgid(p.pid), sig)
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
                    msg = self._failed or _stderr_reason(stderr) or f"codex salió {rc}"
                    await self._q.put(self._ev("error", message=msg[:400], fatal=True))
                await self._q.put(self._ev("result", summary=self._last_message, ok=not (rc or self._failed),
                                           usage=self._usage, model=self._model))
                await self._q.put(self._ev("done"))
                self._done = True

    def _map(self, obj: dict):
        """Traduce UN objeto JSONL de Codex a 0..N WorkerEvent. Conservador: lo desconocido se ignora o cae a una
        fila genérica — un `item.type` nuevo del CLI no puede romper el stream de una sesión viva."""
        t = obj.get("type")
        if t == "thread.started":
            self._native_sid = str(obj.get("thread_id") or "")
            yield self._ev("spawned", native_session_id=self._native_sid, model=self._model)
            return
        if t in ("item.started", "item.completed", "item.updated"):
            it = obj.get("item") or {}
            yield from self._map_item(t, it)
            return
        if t == "turn.completed":
            self._usage = obj.get("usage") or {}
            yield self._ev("result", summary=self._last_message, ok=True, usage=self._usage, model=self._model)
            yield self._ev("done")
            self._done = True
            return
        if t in ("error", "turn.failed"):
            err = obj.get("error") if isinstance(obj.get("error"), dict) else {}
            msg = str(obj.get("message") or err.get("message") or "el turno de Codex falló")
            self._failed = msg
            yield self._ev("error", message=msg[:400], fatal=True)
            # `error` puede venir SEGUIDO de `turn.failed`: el `done` lo cierra el pump al morir el proceso, así no
            # se emiten dos cierres para el mismo fallo.
            return
        # turn.started y el resto → sin evento (ruido de protocolo).

    def _map_item(self, phase: str, it: dict):
        kind = str(it.get("type") or "")
        started = phase == "item.started"

        if kind == "agent_message":
            # La NARRACIÓN del worker (lo que va diciendo) es observabilidad, no voz — igual que en Claude Code. El
            # ÚLTIMO mensaje es además el RESULTADO: Codex no lo marca de ninguna forma, así que se retiene el
            # último y lo entrega `turn.completed`.
            txt = " ".join(str(it.get("text") or "").split())
            if txt and not started:
                self._last_message = txt
                yield self._ev("note", text=txt, model=self._model)
            return

        if kind == "reasoning":
            # El resumen de razonamiento es RUIDO para el panel (y puede ser largo): no se convierte en fila.
            return

        step = _item_step(kind, it)
        if not step:
            return
        if started:
            yield self._ev("phase", label=step.pop("_phase", "trabajando…"), quiet=True)
            yield self._ev("step", tool=step.get("_tool", kind), model=self._model,
                           **{k: v for k, v in step.items() if not k.startswith("_")})
            return
        # completado → la EVIDENCIA (qué le contestó ese paso), para poder auditar al worker.
        body = _item_result_text(kind, it)
        if body or it.get("exit_code") not in (None, 0):
            yield self._ev("step_result", text=body, tool=step.get("_tool", kind),
                           where=step.get("where", ""),
                           is_error=bool(it.get("exit_code") not in (None, 0)))

    def _ev(self, etype: str, **data) -> WorkerEvent:
        return WorkerEvent(task_id=self._task_id, type=etype, data=data, backend=self.name)


# ── traducción de items a la fila del panel (mismo vocabulario `where/action/target` que claude_session) ───────
_URL_RE = re.compile(r"https?://[^\s'\"]+")


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


def _item_step(kind: str, it: dict):
    """`{where, action, target}` + `_phase`/`_tool` internos. None = no emitir fila."""
    if kind == "command_execution":
        cmd = str(it.get("command") or "")
        # Un comando que ES un puente se atribuye a SU lugar (memoria/navegador/widget/zaelar), igual que el Bash
        # acotado de Claude Code: si no, todo el trabajo de un worker de Codex se ve como «sistema».
        low = cmd.lower()
        for needle, where, phase in (("nav_cli", "navegador", "conduciendo el navegador…"),
                                     ("mem_cli", "memoria", "consultando la memoria…"),
                                     ("widget_cli", "widget", "actualizando un widget…"),
                                     ("worker_bridge", "zaelar", "consultando con zaelar…"),
                                     ("agent_report", "", "")):
            if needle in low:
                if not where:
                    return None                       # hbnote fija su propia fase — no duplicar
                return {"where": where, "action": "puente", "target": _cmd_head(cmd),
                        "_phase": phase, "_tool": "Bash"}
        return {"where": "sistema", "action": "ejecuta", "target": _cmd_head(cmd),
                "_phase": "ejecutando un paso…", "_tool": "Bash"}
    if kind in ("file_change", "patch_apply", "apply_patch"):
        changes = it.get("changes") or it.get("files") or []
        first = ""
        if isinstance(changes, list) and changes:
            c0 = changes[0]
            first = _short_path(c0.get("path") if isinstance(c0, dict) else c0)
        elif isinstance(changes, dict) and changes:
            first = _short_path(next(iter(changes)))
        return {"where": "codigo", "action": "escribe", "target": first,
                "_phase": "escribiendo cambios…", "_tool": "Edit"}
    if kind == "file_read":
        return {"where": "archivo", "action": "lee", "target": _short_path(it.get("path")),
                "_phase": "leyendo…", "_tool": "Read"}
    if kind in ("web_search", "web_search_call"):
        return {"where": "web", "action": "web_search", "target": str(it.get("query") or "")[:160],
                "_phase": "buscando en la web…", "_tool": "WebSearch"}
    if kind in ("mcp_tool_call", "tool_call", "custom_tool_call"):
        tool = str(it.get("tool") or it.get("name") or "tool")
        return {"where": "sistema", "action": tool, "target": str(it.get("server") or "")[:80],
                "_phase": f"usando {tool}…", "_tool": tool}
    if kind == "todo_list":
        return None                                   # su plan interno no es una fila de trabajo
    if kind == "error":
        return {"where": "sistema", "action": "error", "target": str(it.get("message") or "")[:160],
                "_phase": "", "_tool": kind}
    return None                                       # item nuevo/desconocido → sin fila, nunca una excepción


def _item_result_text(kind: str, it: dict) -> str:
    raw = ""
    if kind == "command_execution":
        raw = str(it.get("aggregated_output") or "")
    elif kind in ("web_search", "web_search_call"):
        raw = str(it.get("results") or it.get("output") or "")
    elif kind in ("mcp_tool_call", "tool_call", "custom_tool_call"):
        raw = str(it.get("output") or it.get("result") or "")
    elif kind == "error":
        raw = str(it.get("message") or "")
    if not raw:
        return ""
    try:
        from observability import evidence as _evd
        return _evd.body(raw)
    except Exception:
        return raw[:1500]


def _stderr_reason(blob: bytes) -> str:
    """La causa REAL del stderr de Codex, que mete su propio ruido: el `failed to load models cache` sale en CADA
    invocación con un CLI viejo y NO es el motivo por el que la tarea murió — devolverlo mandaba a mirar el sitio
    equivocado. Se prefiere la última línea que parezca un error de verdad."""
    txt = blob.decode("utf-8", "replace")
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    noise = ("models cache", "failed to refresh available models", "Reading additional input from stdin")
    real = [ln for ln in lines if not any(n in ln for n in noise)]
    return (real[-1] if real else (lines[-1] if lines else ""))[:400]
