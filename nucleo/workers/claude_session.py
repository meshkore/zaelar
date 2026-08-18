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
import sys

from loguru import logger

from .base import WorkerBackend, WorkerEvent, WorkerSpec

_ZAELAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_TOOLS = ["Read"]
# PUENTES agnósticos que un worker CONFIABLE puede usar (Bash acotado a estos CLIs, nunca un Bash abierto).
# hbmem/hbnote/hbweb (V2-036) + hbask/hbact (V2-038, plano request/response). Se omiten si deny_tools (§v3·P).
# Puentes del worker (hbmem/hbnote/hbweb/hbask/hbwidget). El allowlist casa por PREFIJO LITERAL del comando, así
# que hay que declarar TODAS las formas con las que se puede escribir el intérprete — si no, el worker escribe una
# variante razonable, el sandbox le pide una aprobación que en headless nadie va a dar, y se pone a hacer
# arqueología de permisos en vez de la tarea.
#
# Medido el 2026-08-02 en cuanto la narración del worker se hizo visible (antes esto era invisible): en esta
# máquina **`python` a secas NI SIQUIERA EXISTE** (solo `python3` y el venv), y el prompt le decía justo eso. El
# worker se pasó minutos probando `python`, `.venv/bin/python`, `python3`, `python3 -m nucleo.*`… y narrándolo:
# «los puentes del worker siguen pidiendo aprobación», «voy a revisar la configuración de permisos». Ahí se iba la
# mayor parte de los 5 minutos de una búsqueda, no en buscar.
_INTERPRETERS = ("python", "python3", ".venv/bin/python", ".venv/bin/python3",
                 os.path.join(_ZAELAR, ".venv", "bin", "python"))
_BRIDGES = ("mem_cli", "agent_report", "nav_cli", "worker_bridge", "widget_cli")
_BRIDGE_TOOLS = [f"Bash({py} -m nucleo.{mod}:*)" for mod in _BRIDGES for py in _INTERPRETERS]


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


def _ctx_size(usage: dict) -> int:
    """Context size of ONE request: fresh input + cache read + cache written (incident 2026-08-18).

    The three counters in an Anthropic-shaped `usage` are parts of the SAME prompt, not separate things: with
    caching on, `input_tokens` stays in the low hundreds while the real prefix travels in
    `cache_read_input_tokens`. Looking only at `input_tokens` reported "956 tokens" when the real context was
    138,492 — the number to watch is the sum, which is why the ceiling was reached with nothing seeing it coming."""
    try:
        return sum(int(usage.get(k) or 0) for k in
                   ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    except (TypeError, ValueError):
        return 0


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
        self._tier: dict | None = None   # escalón de proveedor con el que arrancó (para culpar al correcto si cae)
        self._ctx_tokens = 0             # context size of the LAST message (see `_ctx_size`) — the supervisor
                                         # watches it to compact BEFORE the ceiling (incident 2026-08-18)
        self._real_model = ""            # the model the provider says it ACTUALLY ran, when it says so: `_model`
                                         # above is the ALIAS we asked for, and in the 2026-08-18 incident we
                                         # recorded `claude-opus-4-8[1m]` for a run that `glm-4.7` performed
        # Atribución de la EVIDENCIA: `tool_use_id` → el paso que la pidió, para casar cada `tool_result` con SU
        # herramienta. `_last_step` es el respaldo cuando el id no viene (algunos backends no lo mandan).
        self._steps_by_id: dict[str, dict] = {}
        self._last_step: dict = {}

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
        # `read_dirs` → `--add-dir` (incident 2026-08-18). This backend's translation of "besides your cwd, you may
        # read here", for the CONFINED cwd of `workers/workdir.py`. Defence in depth, not a requirement: measured
        # against the real CLI that an absolute path outside the cwd is already readable without this. With no tools
        # there is nothing to widen.
        if spec.read_dirs and not spec.deny_tools:
            cmd += ["--add-dir", *[str(d) for d in spec.read_dirs if d]]
        if spec.model:
            cmd += ["--model", spec.model]
        if spec.extra_args:
            cmd += list(spec.extra_args)

        env = dict(os.environ)
        env["PATH"] = os.path.dirname(claude) + os.pathsep + env.get("PATH", "")
        env.update(spec.env or {})
        # Endpoint de razonamiento EXTERNO (2026-07-31): si §code_agent.base_url apunta a un proveedor Anthropic-
        # compatible (Z.AI GLM coding plan), el agente headless `claude` lo usa vía ANTHROPIC_BASE_URL +
        # ANTHROPIC_AUTH_TOKEN → NO consume tokens de la licencia Claude Teams. OFF por defecto (base_url vacío).
        # spec.env (del dispatch) manda si ya lo trae. Helper ÚNICO `v2.external_worker_env()` (comparte con el
        # generador de widgets — así NINGÚN spawn de `claude` se queda sin enrutar). Fail-open.
        # 2026-08-02: ya no es UN proveedor sino una CADENA (`workers/providers.py`) — se elige el primer escalón
        # SANO en cada spawn, así el worker siguiente a una cuota agotada arranca solo en el de relevo.
        if "ANTHROPIC_BASE_URL" not in env:
            try:
                from nucleo.workers import providers as _prov
                _ext = _prov.env_for_worker()
                self._tier = _prov.pick()
                if _ext:
                    env.update(_ext)
                    env.pop("ANTHROPIC_API_KEY", None)   # evita ambigüedad key-vs-base_url en el CLI
            except Exception:
                pass
        else:
            # ATTRIBUTION when the endpoint arrived PRE-SET in `spec.env` (incident 2026-08-18). `self._tier` used to
            # be assigned only inside the branch above, so on this path it stayed None and every piece of provider
            # attribution went blind: the events reported an empty `base_url`, and a failure could not name who
            # served the session — which is why the dead worker's row said nothing about running on a gateway.
            # Choosing the endpoint and KNOWING which one is in play are two different jobs; only the first one
            # belonged in that `if`.
            try:
                from nucleo.workers import providers as _prov
                _url = (env.get("ANTHROPIC_BASE_URL") or "").strip()
                self._tier = next((t for t in _prov.chain() if (t.get("base_url") or "") == _url), None) or {
                    "name": _url.split("//")[-1].split("/")[0] or "preconfigurado", "base_url": _url}
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
            # REAL MODEL (incident 2026-08-18). Every `assistant` message states which model produced it, and it
            # need NOT be the one we asked for: the run we recorded as `claude-opus-4-8[1m]` was actually performed
            # by `glm-4.7` (the gateway accepts the Claude alias and serves its own). The panel lied about the model
            # and the cost was priced at the alias's rate. `<synthetic>` is discarded: that is the label the CLI puts
            # on messages IT fabricates (the error notice, for one), not a model.
            # `getattr`/`setattr`-safe like the `_tier` reads elsewhere in this file: several call sites build a
            # session with `object.__new__` (no `__init__`) to exercise `_map` in isolation, and a mapper that only
            # works on a fully constructed object is a mapper that cannot be tested — which is how this attribute
            # first shipped broken (caught by the suite, 2026-08-18).
            _m = str(msg.get("model") or "").strip()
            if _m and _m != "<synthetic>":
                self._real_model = _m
            elif not hasattr(self, "_real_model"):
                self._real_model = ""
            # CONSUMO PARCIAL (2026-08-13): cada mensaje `assistant` trae SU `usage`, y el del `result` final es solo
            # la suma (verificado sondeando: 61.969+127 = 62.096). Se emite por mensaje para que un worker que NO
            # llega a su `result` —el caso NORMAL cuando el supervisor lo mata por presupuesto— siga habiendo
            # declarado lo que gastó. Antes, matar a un worker era metrar CERO: una corrida medida quemó 704 s, 256
            # pasos y ~$0,20 de tokens reales y se facturó a €0. La factura no puede depender de que el proceso
            # tenga la cortesía de despedirse.
            if isinstance(msg.get("usage"), dict):
                # CURRENT CONTEXT SIZE (incident 2026-08-18) — different from the accumulated spend above, and
                # conflating the two is exactly what left us blind: spend is SUMMED message by message, but the
                # context is the TOTAL OF THE LAST message (fresh + cache read + cache written). Summing it would
                # give a number that grows without meaning anything; the one that predicts death is this.
                self._ctx_tokens = _ctx_size(msg["usage"])
                yield self._ev("usage", usage=msg["usage"], model=self._model,
                               real_model=getattr(self, "_real_model", ""),
                               ctx_tokens=getattr(self, "_ctx_tokens", 0),
                               base_url=(getattr(self, "_tier", None) or {}).get("base_url", ""))
            for block in (msg.get("content") or []):
                if not isinstance(block, dict):
                    continue
                # NARRACIÓN del worker (2026-08-02). Hasta hoy solo se traducían los `tool_use`, así que entre que
                # nacía y tocaba su primera herramienta el operador veía un hueco NEGRO (medido: 21 s hasta el primer
                # paso y 2m21s sin una sola fila en una tarea de 5 min). El worker SÍ está hablando todo ese rato —
                # dice qué va a hacer, qué ha encontrado, por qué cambia de plan — y eso es justo lo que hay que ver.
                # Sigue SIN convertirse en `say` (no se habla por voz, §v2·E): es observabilidad pura.
                if block.get("type") == "text":
                    txt = " ".join(str(block.get("text") or "").split())
                    if txt:
                        yield self._ev("note", text=txt, model=self._model)
                    continue
                if block.get("type") != "tool_use":
                    continue
                name = block.get("name") or ""
                tin = block.get("input") or {}
                step = self._tool_step(name, tin)
                lbl = self._tool_phase(name, tin)
                if lbl:                          # "" = no pisar la fase (p.ej. hbnote la fija él mismo, más rica)
                    # quiet=True cuando hay `step`: el step ES la fila del panel → no duplicar con la fase coarse,
                    # pero rec.phase (el prompt "PROCESOS DE FONDO") SÍ se actualiza con la coarse.
                    yield self._ev("phase", label=lbl, quiet=bool(step))
                if step:
                    # Se recuerda el ÚLTIMO paso para poder atribuirle su respuesta: el `tool_result` llega en el
                    # mensaje siguiente (rol `user`) y NO dice de qué tool era más que por `tool_use_id`.
                    self._steps().setdefault(str(block.get("id") or ""), {"tool": name, "where": step.get("where", "")})
                    self._last_step = {"tool": name, "where": step.get("where", "")}
                    yield self._ev("step", tool=name, model=self._model, **step)
            return
        if t == "user":
            # LA EVIDENCIA DEL PASO (2026-08-10). Esto se descartaba entero como «ruido interno», y con ello lo
            # único que permite auditar a un worker: qué le CONTESTARON. Se veía «busca en la web: ferry Dénia
            # Ibiza» y «abre esta URL», pero no si volvió el horario correcto o una página de error — un worker que
            # trae basura dejaba el mismo rastro que uno que acierta.
            msg = obj.get("message") or {}
            for block in (msg.get("content") or []):
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                meta = self._steps().pop(str(block.get("tool_use_id") or ""), None) \
                    or getattr(self, "_last_step", None) or {}
                yield self._ev("step_result", text=self._result_text(block.get("content")),
                               tool=meta.get("tool", ""), where=meta.get("where", ""),
                               is_error=bool(block.get("is_error")),
                               # el escalón con el que corre ESTA sesión: si sus tools se agotan, hay que culpar al
                               # que las sirve, no al que esté primero en la cadena ahora mismo (tras un relevo son
                               # distintos, y atribuirlo mal manda al operador a mirar el proveedor equivocado)
                               provider=(getattr(self, "_tier", None) or {}).get("name", ""))
            return
        if t == "result":
            summary = obj.get("result") or ""
            ok = obj.get("subtype") == "success" and not obj.get("is_error")
            usage = obj.get("usage") or {}
            # ¿murió por el PROVEEDOR (plan/cuota agotada) y no por la tarea? Hasta hoy ese «API Error … Weekly
            # Limit Exhausted» se le entregaba al operador como si fuera el RESULTADO de su búsqueda, sin alerta
            # ni relevo. Marcar aquí pone el escalón en cooldown, dispara la alerta del panel y deja elegido el
            # siguiente proveedor para el próximo spawn.
            if not ok:
                try:
                    from nucleo.workers import providers as _prov
                    # BLOWN CONTEXT first (incident 2026-08-18): it is not the provider, it is the size of the
                    # context. It takes its own lane — compact and continue — and NEVER `note_failure`, which would
                    # put a healthy tier on cooldown and migrate the fault to the next one.
                    if _prov.is_context_overflow(str(summary)):
                        yield self._ev("context_full", text=str(summary)[:300],
                                       tokens=int(getattr(self, "_ctx_tokens", 0) or 0))
                    else:
                        nxt = _prov.note_failure(str(summary), self._tier)
                        if nxt is not None or _prov.classify_failure(str(summary)):
                            yield self._ev("provider_down", text=str(summary)[:300],
                                           provider=(self._tier or {}).get("name", ""),
                                           next=(nxt or {}).get("name", ""))
                except Exception:
                    pass
            yield self._ev("result", summary=str(summary), ok=bool(ok), usage=usage,
                           cost=obj.get("total_cost_usd"), model=self._model,
                           real_model=getattr(self, "_real_model", ""),
                           base_url=(getattr(self, "_tier", None) or {}).get("base_url", ""))
            yield self._ev("done")
            self._done = True
            return
        # el resto (system de cierre, etc.) → sin evento.

    # ── COSTURA para backends del MISMO wire format (2026-08-13) ──────────────────────────────────────────
    # Grok Build emite `--output-format streaming-messages-json`, que es el MISMO vocabulario que el stream-json
    # de Claude Code (`system/init` · `assistant` con bloques · `user` con `tool_result` · `result` con usage y
    # coste). Lo que cambia son los NOMBRES de sus tools (`run_terminal_command` en vez de `Bash`, `read_file` en
    # vez de `Read`…) y la forma de su evidencia. Estos tres métodos son el único punto de variación: `_map` los
    # llama a través de `self`, así que `GrokSession` hereda la traducción entera y solo sobrescribe el vocabulario.
    # (Antes `_map` llamaba a las funciones de módulo directamente, lo que obligaba a duplicar el mapper.)
    def _tool_step(self, tool: str, tin: dict | None = None):
        return _tool_step(tool, tin)

    def _tool_phase(self, tool: str, tin: dict | None = None) -> str:
        return _tool_phase(tool, tin)

    def _result_text(self, content) -> str:
        return _result_text(content)

    def _steps(self) -> dict:
        """`tool_use_id` → el paso que lo pidió, para casar cada `tool_result` con SU herramienta.

        Se resuelve PEREZOSAMENTE en vez de confiar en `__init__`: `_map` es el bombeo de eventos del worker y un
        `AttributeError` ahí mata el stream entero de una sesión viva. (Y el test del mapper construye la sesión
        con `object.__new__` a propósito, para probar la traducción pura sin montar colas ni procesos.)"""
        d = getattr(self, "_steps_by_id", None)
        if d is None:
            d = {}
            self._steps_by_id = d
        return d

    def _ev(self, etype: str, **data) -> WorkerEvent:
        return WorkerEvent(task_id=self._task_id, type=etype, data=data, backend=self.name)


def _result_text(content) -> str:
    """El cuerpo de un `tool_result`, que llega en dos formas según la tool: un string pelado, o una lista de
    bloques `{type:"text"|"image", ...}`. De las imágenes solo se anota que había una (una captura en base64 no
    cabe en un evento y no se audita leyéndola en el log). Recortado con el presupuesto de `evidence`."""
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(str(b.get("text") or ""))
                elif b.get("type") == "image":
                    parts.append("[imagen]")
    else:
        parts = [str(content or "")]
    try:
        from observability import evidence as _evd
        return _evd.body(" ".join(p for p in parts if p))
    except Exception:
        return " ".join(p for p in parts if p)[:1500]


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
