"""How the Grok Build worker STARTS: the CLI found and probed, its config and tool aliases written, the process
spawned. Part of providers.grok; module names are read through _g."""
from __future__ import annotations

from loguru import logger
import glob
import os
import shutil
import subprocess
import tempfile

from nucleo.workers.providers import grok as _g


def find_grok() -> str:
    """Localiza el CLI de Grok Build. Mismo caso que `claude` y `codex`: se instala con npm bajo un nvm que NO está
    en el PATH del server (aquí quedó en `node/v24.18.0`, mientras el proceso corre con v24.1.0)."""
    cand = os.getenv("GROK_BIN")
    if cand and os.path.exists(os.path.expanduser(cand)):
        return os.path.expanduser(cand)
    found = shutil.which("grok")
    if found:
        return found
    for pat in ("~/.nvm/versions/node/*/bin/grok", "/opt/homebrew/bin/grok",
                "/usr/local/bin/grok", "~/.local/bin/grok", "~/.bun/bin/grok"):
        hits = glob.glob(os.path.expanduser(pat))
        if hits:
            return sorted(hits)[-1]
    return ""


def detect() -> dict:
    """¿Está Grok Build aquí, con qué versión y con qué modelos? Lo consume el catálogo de la config para no ofrecer
    un proveedor que no existe en esta máquina. Nunca lanza."""
    path = _g.find_grok()
    out: dict = {"installed": bool(path), "path": path, "version": "", "default_model": ""}
    if not path:
        return out
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=8)
        out["version"] = ((r.stdout or r.stderr or "").strip().split() or [""])[1] \
            if len((r.stdout or r.stderr or "").split()) > 1 else ""
    except Exception:
        pass
    return out


async def start(self, prompt: str, *, spec: "WorkerSpec") -> None:
    import asyncio

    self._task_id = spec.task_id or ""
    self._model = spec.model or ""
    grok = _g.find_grok()
    if not grok:
        await self._q.put(self._ev("error", fatal=True, message=(
            "Grok Build CLI no encontrado (instálalo con `npm i -g @xai-official/grok` o define GROK_BIN)")))
        await self._q.put(self._ev("done"))
        self._done = True
        return

    cwd = spec.cwd or _g._ZAELAR
    # El prompt a un FICHERO (ver la nota de la cabecera): `-p -` no lee stdin, y por argv un prompt con el
    # dossier de memoria + el método revienta el límite de la línea de comandos.
    fd, self._prompt_path = tempfile.mkstemp(prefix=f"zaelar-grok-{self._task_id or 'x'}-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        # La nota del backend va DELANTE: explica la reja antes de que el modelo se choque con ella (ver
        # `_BACKEND_NOTE`). Con `deny_tools` no hay puentes ni terminal, así que la nota no aplica y no se pone.
        fh.write(prompt if spec.deny_tools else _g._BACKEND_NOTE + "\n" + prompt)
    cmd = [grok, "--prompt-file", self._prompt_path, "--output-format", "streaming-messages-json",
           "--permission-mode", "acceptEdits", "--cwd", cwd,
           # No subagents (OUR `max_parallel` pool), no plan mode (our prompt sets the method), no
           # cross-session memory (`memory/` has a single writer; a parallel one would split it).
           "--no-subagents", "--no-plan", "--no-memory"]
    if spec.resume_sid:
        cmd += ["--resume", spec.resume_sid]
        logger.info(f"worker[{self._task_id}]: grok REANUDA sesión {spec.resume_sid[:12]}…")

    # CONTENCIÓN — el mismo invariante que Claude Code, con su misma sintaxis (probado que la aplica).
    if spec.deny_tools:
        # Entrada NO confiable (V2-010): sin tools y sin puentes. `--tools ''` deja el modelo sin ninguna.
        cmd += ["--tools", "", "--deny", "Bash"]
    else:
        tools = list(_g._GROK_TOOLS)
        cmd += ["--tools", ",".join(tools)]
        # Bash acotado a los PUENTES y a nada más: se reusa literalmente `_BRIDGE_TOOLS` de claude_session, que
        # es la fuente única de esa lista (y ya declara todas las formas del intérprete).
        rules = list(_g._BRIDGE_TOOLS)
        if (spec.env or {}).get("ZAELAR_NO_BRIDGE_TOOLS"):
            rules = []
        # With ONE `--allow` rule the allowlist turns STRICT: `acceptEdits` approves nothing unlisted, so EVERY
        # tool is declared (bench 2026-08-13: `write` died with «User cancelled» even once in `--tools`). Rules
        # use CLAUDE's names (`--allow Write` enables `write`), so `_TOOL_ALIAS` is reused — one list, not two.
        rules += sorted({_g._TOOL_ALIAS[t] for t in _g._GROK_TOOLS
                         if t in _g._TOOL_ALIAS and _g._TOOL_ALIAS[t] != "Bash"})
        for r in rules:
            cmd += ["--allow", r]
    if spec.model:
        cmd += ["-m", spec.model]
    if spec.extra_args:
        cmd += list(spec.extra_args)

    env = dict(os.environ)
    env["PATH"] = os.path.dirname(grok) + os.pathsep + env.get("PATH", "")
    env.update(spec.env or {})
    # Grok authenticates with XAI_API_KEY (or ~/.grok/auth.json). The Anthropic-compatible relay chain is Claude
    # Code's and is cleared here so the CLI never sees credentials that are not its own (same as Codex).
    for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        env.pop(k, None)
    env["ZAELAR_WORKER"] = "1"
    env["ZAELAR_TASK_ID"] = spec.task_id or ""
    if spec.token:
        env["ZAELAR_TASK_TOKEN"] = spec.token

    logger.info(f"worker[{self._task_id}]: GrokSession start (model={spec.model or 'default'}, "
                f"deny={spec.deny_tools}, cwd={cwd})")
    try:
        self._proc = await _g._spawned.spawn(
            *cmd, cwd=cwd, env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,          # grupo propio → killpg mata al grok y a sus hijos
            limit=_g._STREAM_LIMIT,
        )
    except Exception as e:  # noqa: BLE001
        await self._q.put(self._ev("error", message=f"no se pudo arrancar el worker: {e}", fatal=True))
        await self._q.put(self._ev("done"))
        self._done = True
        return

    # El prompt ya está en `--prompt-file`; stdin se cierra para que el CLI no espere entrada que no va a llegar.
    try:
        self._proc.stdin.close()
        self._stdin_closed = True
    except Exception:
        pass
    self._reader_task = asyncio.create_task(self._pump(), name=f"worker-pump-{self._task_id}")
