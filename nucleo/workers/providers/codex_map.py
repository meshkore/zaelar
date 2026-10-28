"""How the Codex stream is READ: one JSONL event to the normalised WorkerEvent vocabulary, an item to its step
and its result text. Part of providers.codex; module names are read through _x."""
from __future__ import annotations

import re

from nucleo.workers.providers import codex as _x


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

    step = _x._item_step(kind, it)
    if not step:
        return
    if started:
        yield self._ev("phase", label=step.pop("_phase", "trabajando…"), quiet=True)
        yield self._ev("step", tool=step.get("_tool", kind), model=self._model,
                       **{k: v for k, v in step.items() if not k.startswith("_")})
        return
    # completado → la EVIDENCIA (qué le contestó ese paso), para poder auditar al worker.
    body = _x._item_result_text(kind, it)
    if body or it.get("exit_code") not in (None, 0):
        yield self._ev("step_result", text=body, tool=step.get("_tool", kind),
                       where=step.get("where", ""),
                       is_error=bool(it.get("exit_code") not in (None, 0)))


# ── traducción de items a la fila del panel (mismo vocabulario `where/action/target` que claude_session) ───────
_URL_RE = re.compile(r"https?://[^\s'\"]+")


def _item_step(kind: str, it: dict):
    """`{where, action, target}` + `_phase`/`_tool` internos. None = no emitir fila."""
    if kind == "command_execution":
        cmd = str(it.get("command") or "")
        # Un comando que ES un puente se atribuye a SU lugar (memoria/navegador/widget/zaelar), igual que el Bash
        # acotado de Claude Code: si no, todo el trabajo de un worker de Codex se ve como «sistema».
        low = cmd.lower()
        from nucleo.workers.progress import say as _say
        for needle, where, phase in (("cli.nav", "navegador", _say("nav_drive", "driving the browser") + "…"),
                                     ("cli.mem", "memoria", _say("mem_recall", "checking memory") + "…"),
                                     ("cli.widget", "widget", _say("widget_update", "updating a widget") + "…"),
                                     ("cli.bridge", "zaelar", _say("zaelar_consult", "checking with zaelar") + "…"),
                                     ("cli.report", "", "")):
            if needle in low:
                if not where:
                    return None                       # hbnote fija su propia fase — no duplicar
                return {"where": where, "action": "puente", "target": _x._cmd_head(cmd),
                        "_phase": phase, "_tool": "Bash"}
        return {"where": "sistema", "action": "ejecuta", "target": _x._cmd_head(cmd),
                "_phase": _say("system_step", "running a step") + "…", "_tool": "Bash"}
    if kind in ("file_change", "patch_apply", "apply_patch"):
        changes = it.get("changes") or it.get("files") or []
        first = ""
        if isinstance(changes, list) and changes:
            c0 = changes[0]
            first = _x._short_path(c0.get("path") if isinstance(c0, dict) else c0)
        elif isinstance(changes, dict) and changes:
            first = _x._short_path(next(iter(changes)))
        return {"where": "codigo", "action": "escribe", "target": first,
                "_phase": "escribiendo cambios…", "_tool": "Edit"}
    if kind == "file_read":
        return {"where": "archivo", "action": "lee", "target": _x._short_path(it.get("path")),
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
