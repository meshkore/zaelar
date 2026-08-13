"""nucleo/workers/grok_session.py — backend `GrokSession` (Grok Build headless). V2-038, 2026-08-13.

**Grok Build es el backend más cercano a Claude Code que tenemos**, y por eso HEREDA de `ClaudeCodeSession` en vez
de reimplementar la traducción. Verificado sondeando el CLI real (`grok` 1.0.3):

  · `--output-format streaming-messages-json` emite **el MISMO vocabulario** que el stream-json de Claude Code:
    `{"type":"system","subtype":"init",…}` con `session_id`/`model`/`tools` · `{"type":"assistant","message":
    {"content":[…]}}` con bloques `text`/`tool_use`/`thinking` · `{"type":"user",…}` con `tool_result` y su
    `tool_use_id` · `{"type":"result","subtype":"success","usage":{…},"total_cost_usd":…}`.
  · **Acepta NUESTRA allowlist tal cual**: `--allow 'Bash(cmd:*)'` (alias de compatibilidad `--allowedTools`) y
    `--deny`. PROBADO que la aplica de verdad: con `--deny 'Bash(whoami:*)'` el CLI devolvió «Tool
    `run_terminal_command` was not executed: Denied by permission policy: deny rule on bash matching "whoami"».
    Es la diferencia de FONDO con Codex, que solo tiene modos de sandbox: **Grok SÍ puede sostener el invariante del
    ESCRITOR ÚNICO** (Bash acotado a los puentes), así que no hace falta rechazar tareas por no poder contenerlas.
  · `--permission-mode acceptEdits`, `--cwd`, `-m/--model`, `-r/--resume <id>`: mismos ejes que Claude Code.

Lo que SÍ cambia y es lo único que se sobrescribe aquí:
  1. **Los nombres de sus tools** (`run_terminal_command`, `read_file`, `write`, `search_replace`, `list_dir`,
     `grep`, `web_search`, `spawn_subagent`, `ask_user_question`…) → se traducen a los de Claude Code y se reusa el
     mapeo de filas del panel, para que el operador vea el MISMO lenguaje sea quien sea el que trabaje.
  2. **La forma de su evidencia**: el `tool_result` de un comando llega como un JSON en un STRING con el resultado
     en `output_for_prompt`. Sin desenvolverlo, la fila de evidencia mostraría el JSON crudo (con rutas de log y
     bytes) en vez de lo que de verdad contestó el comando.
  3. **`thinking`**: Grok emite su razonamiento como bloque. NO se convierte en fila — es largo, es interno, y la
     regla de la casa es que la voz no razona y el panel muestra trabajo, no monólogo.
  4. **`send()` no inyecta en vivo**: `grok -p` es de un turno. Como en Codex, la inyección llega por el piggyback
     de los puentes (HTTP, agnóstico del backend). `grok agent stdio` existe y permitiría bidireccionalidad real —
     anotado como mejora, no necesario para el contrato de hoy.

⚠️ **El prompt va por `--prompt-file`, NO por stdin.** `grok -p -` NO lee de stdin (a diferencia de `codex exec -`):
toma el `-` como el prompt literal y el nuestro se pierde. Costó verlo porque el fallo NO da error — el CLI arranca
con un prompt sin sentido y el modelo se pone a hacer algo razonable por su cuenta: en el primer sondeo se dedicó a
explorar el repo entero y a redactar un informe del estado del proyecto, quemando **447.559 tokens de entrada y
$0,73**, cuando lo que se le había pedido era imprimir la versión de Python. Con el prompt bien entregado, la misma
clase de tarea costó **$0,005**. Un prompt que no llega es la avería más cara y más silenciosa de este backend.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import tempfile

from loguru import logger

from .base import WorkerSpec
from .claude_session import _BRIDGE_TOOLS, ClaudeCodeSession, _STREAM_LIMIT, _ZAELAR

# Tools NATIVAS de Grok que un worker confiable puede usar, en su propio vocabulario. `run_terminal_command` es su
# Bash y va SIEMPRE acotado por las reglas `Bash(...)` de abajo (nunca abierto), igual que en Claude Code.
#
# **`write` y `search_replace` están aquí porque su AUSENCIA mataba las corridas** (banco del 2026-08-13): la lista
# solo traía lectura, así que al llegar el momento de dejar su informe el worker no tenía con qué y **rodeó por
# `run_terminal_command`** — que la allowlist deniega, correctamente. Un worker sin escritura no es un worker más
# seguro: es uno que empuja su trabajo contra la reja. Son los equivalentes de `Write`/`Edit`, que Claude Code ya
# tiene de serie (`claude_session._DEFAULT_TOOLS`); la contención de verdad la da la reja del Bash, no negarle un
# fichero. **NO se añaden** las suyas que pisarían piezas nuestras: `spawn_subagent` (el paralelismo lo gobierna
# nuestro pool), `scheduler_*` (nuestro cron es `nucleo/scheduler.py`), `ask_user_question` (se pregunta por el
# puente `hbask`, que es quien sabe llegar al operador) ni las de imagen/vídeo.
#
# ⚠️ Grok **NO tiene `web_fetch`** (su catálogo declarado se sondeó entero: solo `web_search`). O sea que descubre
# páginas pero no puede ABRIRLAS por su cuenta — justo lo que hizo TODO el trabajo en la corrida de Claude Code,
# donde la búsqueda del relay estaba agotada y el `WebFetch` la sustituyó. En este backend esa pata la dan los
# PUENTES: `nucleo.worker_bridge` (la `web_search` propia de Zaelar) y `nucleo.nav_cli` (el navegador real). No es un
# hueco tapable con la lista de tools; se le dice en el prompt (ver `_BACKEND_NOTE`).
_GROK_TOOLS = ("run_terminal_command", "read_file", "write", "search_replace", "list_dir", "grep",
               "web_search", "todo_write")

# Lo que Grok le dice al modelo cuando la allowlist deniega un comando es, LITERALMENTE, «User cancelled the
# execution for tool `run_terminal_command`». Un modelo que lee eso concluye lo razonable —que el humano lo ha
# abortado— y **PARA**: en el banco del 2026-08-13 una sola denegación cerró la sesión con `ok=False` y entrega
# vacía, tras haber trabajado bien (plan, contrato del widget, búsqueda con resultados reales). No podemos cambiar
# ese texto (lo escribe el CLI dentro de su propio bucle, no pasa por nosotros), así que se DESARMA por delante:
# se le explica de quién es la reja, por dónde se rodea y que no es una orden de parar. Va pegado al prompt por el
# propio backend —no en `dispatch`— porque es una rareza de ESTE CLI y no tiene por qué ensuciar al resto.
_BACKEND_NOTE = """[ENTORNO — LÉELO ANTES DE EMPEZAR]
Tu terminal está acotada A PROPÓSITO: `run_terminal_command` solo puede ejecutar los PUENTES de Zaelar (los
`python -m nucleo.*` que se te indican más abajo). Cualquier otro comando será denegado.
Cuando eso pasa, el CLI te lo dirá con el texto «User cancelled the execution for tool `run_terminal_command`».
**Eso NO es el operador cancelando ni una orden de parar**: es la reja de permisos rechazando un comando que no
está en la lista. NO abandones la tarea — reformula usando los puentes y sigue.
Para abrir una URL concreta no tienes `web_fetch`: usa la `web_search` de Zaelar por `nucleo.worker_bridge` o el
navegador real por `nucleo.nav_cli`. Para dejar ficheros usa tu tool `write`, no la terminal.
"""

# Su vocabulario → el nuestro. Se traduce para que `_tool_step`/`_tool_phase` de `claude_session` (la fuente única
# de cómo se pinta una fila) funcionen sin tocarse, y para que el panel hable el mismo idioma con los 3 backends.
_TOOL_ALIAS = {
    "run_terminal_command": "Bash",
    "read_file": "Read",
    "write": "Write",
    "search_replace": "Edit",
    "list_dir": "Glob",
    "grep": "Grep",
    "web_search": "WebSearch",
    "web_fetch": "WebFetch",
    "spawn_subagent": "Task",
    "ask_user_question": "AskUser",
    # `todo_write` tiene que estar AQUÍ aunque el panel no pinte su fila distinta: este mapa es también la fuente de
    # las reglas `--allow` (ver `start`), así que una tool sin alias es una tool sin permiso — y se moriría con el
    # mismo «User cancelled» que costó dos corridas del banco.
    "todo_write": "TodoWrite",
}
# Argumento que lleva la ruta/consulta en cada tool de Grok → el nombre que espera `_tool_step` de claude_session.
# VERIFICADO sondeando el CLI (no adivinado): `read_file` usa **`target_file`**, no `path`. Con el nombre mal, la
# fila del panel salía con `target=''` — o sea el operador veía «lee» sin saber QUÉ lee, que es justo el dato.
# Se listan varios candidatos por tool porque no todas las tools de Grok están sondeadas: la primera que exista gana.
_ARG_ALIAS = {
    "Read": (("target_file", "path", "file"), "file_path"),
    "Write": (("target_file", "path", "file"), "file_path"),
    "Edit": (("target_file", "path", "file"), "file_path"),
    "Glob": (("target_directory", "path", "directory", "pattern"), "pattern"),
    "Grep": (("pattern", "query"), "pattern"),
    "WebSearch": (("query", "q"), "query"),
    "WebFetch": (("url",), "url"),
}


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
    path = find_grok()
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


class GrokSession(ClaudeCodeSession):
    name = "grok_build"
    _prompt_path = ""   # fichero temporal del prompt (ver la nota de la cabecera); se borra al morir el proceso

    async def start(self, prompt: str, *, spec: "WorkerSpec") -> None:
        import asyncio

        self._task_id = spec.task_id or ""
        self._model = spec.model or ""
        grok = find_grok()
        if not grok:
            await self._q.put(self._ev("error", fatal=True, message=(
                "Grok Build CLI no encontrado (instálalo con `npm i -g @xai-official/grok` o define GROK_BIN)")))
            await self._q.put(self._ev("done"))
            self._done = True
            return

        cwd = spec.cwd or _ZAELAR
        # El prompt a un FICHERO (ver la nota de la cabecera): `-p -` no lee stdin, y por argv un prompt con el
        # dossier de memoria + el método revienta el límite de la línea de comandos.
        fd, self._prompt_path = tempfile.mkstemp(prefix=f"zaelar-grok-{self._task_id or 'x'}-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            # La nota del backend va DELANTE: explica la reja antes de que el modelo se choque con ella (ver
            # `_BACKEND_NOTE`). Con `deny_tools` no hay puentes ni terminal, así que la nota no aplica y no se pone.
            fh.write(prompt if spec.deny_tools else _BACKEND_NOTE + "\n" + prompt)
        cmd = [grok, "--prompt-file", self._prompt_path, "--output-format", "streaming-messages-json",
               "--permission-mode", "acceptEdits", "--cwd", cwd,
               # Su TUI y sus extras no tienen sentido headless, y cada uno es superficie que no queremos:
               # sin subagentes (el paralelismo lo gobierna NUESTRO pool `max_parallel`, no el CLI), sin plan mode
               # (el método lo pone nuestro prompt) y sin memoria cruzada entre sesiones (la memoria del operador es
               # `memory/`, con su escritor único — una memoria paralela dentro del CLI la partiría en dos).
               "--no-subagents", "--no-plan", "--no-memory"]
        if spec.resume_sid:
            cmd += ["--resume", spec.resume_sid]
            logger.info(f"worker[{self._task_id}]: grok REANUDA sesión {spec.resume_sid[:12]}…")

        # CONTENCIÓN — el mismo invariante que Claude Code, con su misma sintaxis (probado que la aplica).
        if spec.deny_tools:
            # Entrada NO confiable (V2-010): sin tools y sin puentes. `--tools ''` deja el modelo sin ninguna.
            cmd += ["--tools", "", "--deny", "Bash"]
        else:
            tools = list(_GROK_TOOLS)
            cmd += ["--tools", ",".join(tools)]
            # Bash acotado a los PUENTES y a nada más: se reusa literalmente `_BRIDGE_TOOLS` de claude_session, que
            # es la fuente única de esa lista (y ya declara todas las formas del intérprete).
            rules = list(_BRIDGE_TOOLS)
            if (spec.env or {}).get("ZAELAR_NO_BRIDGE_TOOLS"):
                rules = []
            # **En cuanto hay UNA regla `--allow`, la allowlist pasa a ser ESTRICTA**: `--permission-mode
            # acceptEdits` deja de aprobar nada que no esté listado, así que hay que declarar CADA tool, no solo el
            # Bash. Lo descubrió el banco del 2026-08-13 en dos capas: primero faltaba `write` en `--tools` (y el
            # worker rodeaba por la terminal), y al añadirlo la escritura seguía muriendo — ahora con «User
            # cancelled the execution for tool `write`», porque nunca había tenido permiso. Las reglas van con los
            # nombres de CLAUDE (probado: `--allow Write` habilita su `write`, `--allow Read` su `read_file`), que
            # es justo el mapeo que ya tenemos en `_TOOL_ALIAS` — se reusa para no mantener dos listas que se
            # desincronizarían al añadir una tool.
            rules += sorted({_TOOL_ALIAS[t] for t in _GROK_TOOLS
                             if t in _TOOL_ALIAS and _TOOL_ALIAS[t] != "Bash"})
            for r in rules:
                cmd += ["--allow", r]
        if spec.model:
            cmd += ["-m", spec.model]
        if spec.extra_args:
            cmd += list(spec.extra_args)

        env = dict(os.environ)
        env["PATH"] = os.path.dirname(grok) + os.pathsep + env.get("PATH", "")
        env.update(spec.env or {})
        # Grok se autentica con XAI_API_KEY (o su OAuth en ~/.grok/auth.json). La cadena de relevo Anthropic-
        # compatible de `providers.py` es de Claude Code y aquí no significa nada: se limpia para no confundir al CLI
        # con credenciales que no son suyas (mismo criterio que en el backend de Codex).
        for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
            env.pop(k, None)
        env["ZAELAR_WORKER"] = "1"
        env["ZAELAR_TASK_ID"] = spec.task_id or ""
        if spec.token:
            env["ZAELAR_TASK_TOKEN"] = spec.token

        logger.info(f"worker[{self._task_id}]: GrokSession start (model={spec.model or 'default'}, "
                    f"deny={spec.deny_tools}, cwd={cwd})")
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=cwd, env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,          # grupo propio → killpg mata al grok y a sus hijos
                limit=_STREAM_LIMIT,
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

    async def _pump(self) -> None:
        """El bombeo es el heredado; solo se añade borrar el fichero de prompt cuando el proceso ya terminó (antes
        no: el CLI lo lee al arrancar, y borrarlo pronto sería una carrera)."""
        try:
            await super()._pump()
        finally:
            p = getattr(self, "_prompt_path", "")
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
                self._prompt_path = ""

    async def send(self, text: str) -> None:
        """No-op DELIBERADO: `grok -p` es de un turno (no lee turnos nuevos por stdin como el stream-json de Claude
        Code). La inyección llega por el piggyback de los puentes, que es HTTP y agnóstico del backend. Se registra
        para que un refinamiento no entregado no sea invisible."""
        logger.info(f"worker[{self._task_id}]: grok no admite inyección en vivo; «{text[:60]}» irá por piggyback")

    # ── el ÚNICO punto de variación: su vocabulario de tools y su evidencia ────────────────────────────────
    def _tool_step(self, tool: str, tin: dict | None = None):
        return super()._tool_step(*_translate(tool, tin))

    def _tool_phase(self, tool: str, tin: dict | None = None) -> str:
        return super()._tool_phase(*_translate(tool, tin))

    def _result_text(self, content) -> str:
        return super()._result_text(_unwrap_evidence(content))


def _translate(tool: str, tin: dict | None):
    """`(tool, input)` de Grok → `(tool, input)` en el vocabulario de Claude Code, para reusar el mapeo de filas."""
    tin = dict(tin or {})
    name = _TOOL_ALIAS.get(tool or "", tool or "")
    cands, dst = _ARG_ALIAS.get(name, ((), ""))
    if dst and dst not in tin:
        for src in cands:
            if tin.get(src):
                tin[dst] = tin[src]
                break
    return name, tin


def _bytes_to_text(v) -> str:
    """`stdout` de su GrepSearch llega como LISTA DE BYTES (no como texto). Pintarla tal cual llenaba la fila de
    evidencia de «[60,119,111,114,…]», que es ilegible y no permite auditar nada."""
    try:
        return bytes(int(x) & 0xFF for x in v).decode("utf-8", "replace")
    except Exception:
        return ""


# Cada tool de Grok mete su resultado en un campo distinto. Es un mapa por `type`, con orden de preferencia; lo que
# no esté aquí cae al barrido genérico de abajo, y lo que no se reconozca se devuelve CRUDO (mejor evidencia fea que
# evidencia perdida).
_EVIDENCE_FIELDS = {
    "Bash": ("output_for_prompt",),
    "ReadFile": ("content_concise", "content"),          # anidados bajo FileContent
    "ListDir": ("content",),                            # anidado bajo Content
    "GrepSearch": ("stdout",),                          # ¡lista de bytes!
    "Todo": ("summary_for_prompt",),
    # `write` y `search_replace` comparten forma: `{"type":"SearchReplace","EditsApplied":{…}}`. Sin esto la fila
    # de un fichero escrito enseñaba el JSON con el `old_string`/`new_string` enteros en vez de «se ha creado X».
    "SearchReplace": ("tool_output_for_prompt",),        # anidado bajo EditsApplied
}


def _dig(o: dict, keys) -> str:
    """Busca las claves en el dict y, si no están arriba, un nivel dentro de sus sub-dicts (Grok las anida bajo
    envoltorios con nombre: `FileContent`, `Content`, `TodosUpdated`…)."""
    for k in keys:
        if k in o:
            v = o[k]
            return _bytes_to_text(v) if isinstance(v, list) else str(v or "")
    for v in o.values():
        if isinstance(v, dict):
            for k in keys:
                if k in v:
                    iv = v[k]
                    return _bytes_to_text(iv) if isinstance(iv, list) else str(iv or "")
    return ""


def _unwrap_evidence(content):
    """La evidencia de Grok viene ENVUELTA, y de forma distinta por tool: `{"type":"Bash","output_for_prompt":…}`,
    `{"type":"ReadFile","FileContent":{"content":…}}`, `{"type":"GrepSearch","stdout":[bytes…]}`. Sin desenvolverla,
    la fila de evidencia enseña el sobre en vez de la carta — y auditar a un worker es justo poder leer la carta.

    Formas vistas en el sondeo real: (a) un string con ese JSON; (b) una lista de bloques
    `{"type":"content","content":{"type":"text","text":…}}` — el caso de una tool DENEGADA por el policy, que hay
    que conservar íntegro porque es la prueba de que la contención funcionó."""
    def _from_str(s: str):
        try:
            o = json.loads(s)
        except Exception:
            return s
        if not isinstance(o, dict):
            return s
        body = _dig(o, _EVIDENCE_FIELDS.get(str(o.get("type") or ""), ()))
        if not body:                                    # tool no sondeada → barrido genérico
            body = _dig(o, ("output_for_prompt", "content_concise", "content", "text", "stdout", "output"))
        return body or s

    if isinstance(content, str):
        return _from_str(content)
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, str):
                out.append(_from_str(b))
            elif isinstance(b, dict):
                inner = b.get("content")
                if isinstance(inner, dict) and inner.get("type") == "text":
                    out.append(str(inner.get("text") or ""))      # tool denegada / mensaje del policy
                elif b.get("type") == "text":
                    out.append(_from_str(str(b.get("text") or "")))
                else:
                    out.append(b)
        return out
    return content
