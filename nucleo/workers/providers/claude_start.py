"""How the Claude Code worker STARTS: the CLI found, the context size read, the env marked, the process
spawned and its stream pumped. Part of providers.claude; module names are read through _c."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nucleo.workers.base import WorkerSpec

from loguru import logger
import asyncio
import glob
import json
import os
import shutil

from nucleo.workers.providers import claude as _c


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


def _mark_the_worker_env(env: dict, task_id: str) -> None:
    """The worker's own markers: for the orphan sweep at boot and the per-task bridge auth (§v2·D), and — through
    mediated egress — the task every model call serves, so usage adds up per task."""
    env["ZAELAR_WORKER"] = "1"
    env["ZAELAR_TASK_ID"] = task_id
    try:
        from nucleo.energy import egress as _egress
        for _k, _v in _egress.task_header_env(env.get("ANTHROPIC_BASE_URL", ""), task_id).items():
            env.setdefault(_k, _v)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"worker[{task_id}]: no task header for egress: {e!r}")


# ── ciclo de vida ─────────────────────────────────────────────────────────────────────────────────────
async def start(self, prompt: str, *, spec: "WorkerSpec") -> None:
    self._task_id = spec.task_id or ""
    self._model = spec.model or ""
    claude = _c._find_claude()
    if not claude:
        return await self._fail_fast("Claude Code CLI no encontrado (define CLAUDE_BIN)")

    cmd = [claude, "--print", "--verbose",
           "--input-format", "stream-json", "--output-format", "stream-json",
           "--permission-mode", "acceptEdits"]
    # V2-049 CONTINUITY: resume a previous worker of the SAME errand (no re-navigating, remembers what failed).
    # Fail-soft: an invalid `--resume` id starts a new session; same tab + memory + «resuming» prompt still help.
    if spec.resume_sid:
        cmd += ["--resume", spec.resume_sid]
        logger.info(f"worker[{spec.task_id}]: REANUDA sesión nativa {spec.resume_sid[:12]}…")
    if spec.deny_tools:
        tools: list[str] = []
    else:
        tools = spec.tools if spec.tools is not None else list(_c._DEFAULT_TOOLS)
        if not (spec.env or {}).get("ZAELAR_NO_BRIDGE_TOOLS"):
            tools = list(tools) + [t for t in _c._BRIDGE_TOOLS if t not in tools]
    cmd += ["--allowedTools", " ".join(tools)]
    # V2-698 — `--allowedTools` gates PERMISSION, but the CLI still ships EVERY built-in schema. 2026-09-15:
    # DeepSeek `400 Invalid schema for function 'Artifact'` (`\p{Cc}`) and z.ai `400 [1210]` sent a three-tool
    # worker to the paid tier for $1.23. `--tools` names the built-in SET: only usable tools travel.
    cmd += ["--tools", ",".join(_c.builtin_tool_names(tools))]
    # `read_dirs` → `--add-dir` (incident 2026-08-18): "besides your cwd, you may read here" for the CONFINED cwd
    # of `workers/workdir.py`. Defence in depth (the real CLI already reads absolute paths); no tools → no widening.
    if spec.read_dirs and not spec.deny_tools:
        cmd += ["--add-dir", *[str(d) for d in spec.read_dirs if d]]
    if spec.model:
        cmd += ["--model", spec.model]
    if spec.extra_args:
        cmd += list(spec.extra_args)

    env = _c._without_host_routing(dict(os.environ))
    env["PATH"] = os.path.dirname(claude) + os.pathsep + env.get("PATH", "")
    env.update(spec.env or {})
    # EXTERNAL reasoning endpoint (2026-07-31): a §code_agent.base_url Anthropic-compatible provider (Z.AI GLM) is
    # used via ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN, sparing the licence. Off by default; spec.env wins. One
    # helper, `v2.external_worker_env()`, shared with the widget generator. Fail-open. Since 2026-08-02 a CHAIN
    # (`workers/providers/`): each spawn picks the first HEALTHY tier.
    _unrouted = False
    if "ANTHROPIC_BASE_URL" not in env:
        try:
            from nucleo.workers import providers as _prov
            _ext = _prov.env_for_worker()
            self._tier = _prov.pick()
            if _ext:
                env.update(_ext)
                env.pop("ANTHROPIC_API_KEY", None)   # evita ambigüedad key-vs-base_url en el CLI
            else:
                # V2-778 F5-40 — `{}` is «the local licence» on a desktop but «nothing left» in a container,
                # where the CLI would run with no endpoint or login and die naming nothing.
                _unrouted = _prov._is_container()
        except Exception:
            pass
    else:
        # ATTRIBUTION for an endpoint PRE-SET in `spec.env` (incident 2026-08-18): `self._tier` stayed None here,
        # so events showed an empty `base_url` and a failure could not name who served it. Choosing the endpoint
        # and KNOWING which one is in play are two jobs.
        try:
            from nucleo.workers import providers as _prov
            _url = (env.get("ANTHROPIC_BASE_URL") or "").strip()
            self._tier = next((t for t in _prov.chain() if (t.get("base_url") or "") == _url), None) or {
                "name": _url.split("//")[-1].split("/")[0] or "preconfigurado", "base_url": _url}
        except Exception:
            pass
    if _unrouted:
        from nucleo.workers import providers as _prov
        return await self._fail_fast(_prov.unrouted_refusal(self._task_id))
    # V2-289 — if this tier cannot read images, the browser bridge stops offering screenshots. After BOTH
    # branches on purpose (both resolve `self._tier`); a caller's `spec.env` still wins.
    try:
        from nucleo.workers import providers as _prov
        for _k, _v in _prov.vision_env(self._tier).items():
            env.setdefault(_k, _v)
    except Exception:
        pass
    _c._mark_the_worker_env(env, spec.task_id or "")
    if spec.token:
        env["ZAELAR_TASK_TOKEN"] = spec.token
    cwd = spec.cwd or _c._ZAELAR

    # A DEV worker never inherits the operator's full env (V2-601 T-09, audit 2026-09-05: `sandbox._clean_env`
    # was never wired here). Allowlist: what is not named does not travel — ZAELAR_*, the process basics and
    # the ONE credential its tier resolved.
    if spec.kind == "dev":
        env = _c._dev_env_allowlist(env)
    env["SHELL"] = _c.worker_shell(env.get("SHELL", ""))

    logger.info(f"worker[{self._task_id}]: ClaudeCodeSession start (model={spec.model or 'default'}, "
                f"tools={len(tools)}, deny={spec.deny_tools}, cwd={cwd})")
    preexec = None
    if spec.kind == "dev" and os.name != "nt":
        # topes de recursos (memoria/nproc/fsize, SIN límite de CPU/pared) — auditoría 2026-07-26, defensa en
        # profundidad además del guard de confinamiento de rutas (--settings, ver spec.extra_args).
        try:
            from nucleo.cli import sandbox as _sandbox
            preexec = _sandbox.dev_worker_rlimits()
        except Exception:
            preexec = None
    try:
        self._proc = await _c._spawned.spawn(
            *cmd, cwd=cwd, env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,           # grupo propio → killpg (§v2·D)
            limit=_c._STREAM_LIMIT,
            preexec_fn=preexec,
        )
    except Exception as e:  # noqa: BLE001
        await self._q.put(self._ev("error", message=f"no se pudo arrancar el worker: {e}", fatal=True))
        await self._q.put(self._ev("done"))
        self._done = True
        return

    # turno inicial por stdin (la sesión queda VIVA para inyecciones posteriores).
    try:
        self._proc.stdin.write(_c._user_msg(prompt))
        await self._proc.stdin.drain()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker[{self._task_id}]: no pude escribir el prompt inicial: {e}")
    self._reader_task = asyncio.create_task(self._pump(), name=f"worker-pump-{self._task_id}")


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
