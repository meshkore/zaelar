"""nucleo/workers/providers/grok.py — backend `GrokSession` (Grok Build headless). V2-038, 2026-08-13.

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

from ..base import WorkerSpec
from . import spawned as _spawned  # a worker's session id marks every request it sends
from .claude import _BRIDGE_TOOLS, ClaudeCodeSession, _STREAM_LIMIT, _ZAELAR

# Grok's NATIVE tools a trusted worker may use. `run_terminal_command` is its Bash, ALWAYS bounded by the `Bash(...)`
# rules below. `write`/`search_replace` are here because their absence killed runs (bench 2026-08-13: the worker
# detoured through the terminal and the allowlist denied it). Not added: `spawn_subagent`, `scheduler_*`,
# `ask_user_question` (we own pool, cron and `hbask`), image/video. ⚠️ Grok has NO `web_fetch` (only `web_search`):
# pages are opened via the bridges `nucleo.cli.bridge` / `nucleo.cli.nav`, told in the prompt (`_BACKEND_NOTE`).
_GROK_TOOLS = ("run_terminal_command", "read_file", "write", "search_replace", "list_dir", "grep",
               "web_search", "todo_write")

# When the allowlist denies a command Grok tells the model «User cancelled the execution for tool
# `run_terminal_command`», and the model STOPS (bench 2026-08-13: one denial ended a good session, ok=False). The CLI
# writes that text, so it is disarmed up front, from this backend only: whose fence it is and that it is not a stop.
_BACKEND_NOTE = """[ENTORNO — LÉELO ANTES DE EMPEZAR]
Tu terminal está acotada A PROPÓSITO: `run_terminal_command` solo puede ejecutar los PUENTES de Zaelar (los
`python -m nucleo.*` que se te indican más abajo). Cualquier otro comando será denegado.
Cuando eso pasa, el CLI te lo dirá con el texto «User cancelled the execution for tool `run_terminal_command`».
**Eso NO es el operador cancelando ni una orden de parar**: es la reja de permisos rechazando un comando que no
está en la lista. NO abandones la tarea — reformula usando los puentes y sigue.
Para abrir una URL concreta no tienes `web_fetch`: usa la `web_search` de Zaelar por `nucleo.cli.bridge` o el
navegador real por `nucleo.cli.nav`. Para dejar ficheros usa tu tool `write`, no la terminal.
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
    # `todo_write` must be HERE: this map also feeds the `--allow` rules, so a tool without an alias has no
    # permission and dies with the same «User cancelled» that cost two bench runs.
    "todo_write": "TodoWrite",
}
# The argument carrying each Grok tool's path/query → the name `_tool_step` expects. VERIFIED by probing the CLI:
# `read_file` uses `target_file`, not `path` (else the row showed `target=''`). Several candidates; first one wins.
_ARG_ALIAS = {
    "Read": (("target_file", "path", "file"), "file_path"),
    "Write": (("target_file", "path", "file"), "file_path"),
    "Edit": (("target_file", "path", "file"), "file_path"),
    "Glob": (("target_directory", "path", "directory", "pattern"), "pattern"),
    "Grep": (("pattern", "query"), "pattern"),
    "WebSearch": (("query", "q"), "query"),
    "WebFetch": (("url",), "url"),
}


from nucleo.workers.providers import grok_start as _gst  # noqa: E402


class GrokSession(ClaudeCodeSession):
    name = "grok_build"
    _prompt_path = ""   # fichero temporal del prompt (ver la nota de la cabecera); se borra al morir el proceso

    start = _gst.start

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


# Each Grok tool puts its result in a different field: a map by `type`, in preference order; the rest falls to the
# generic sweep, and anything unrecognised is returned RAW (ugly evidence beats lost evidence).
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

from nucleo.workers.providers.grok_start import (  # noqa: E402,F401
    find_grok, detect)
