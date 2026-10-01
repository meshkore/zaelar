"""What a worker's tool call LOOKS like on the operator's timeline: where, what, target (V2-778 F1, 2026-10-01).

Moved out of `nucleo/workers/claude_session.py` (over its size ceiling): the readers that turn one `tool_use`
into a step row `{where, action, target}` and its phase (V2-048) — the bash command's head, a navigation's target,
a short path. Unchanged; `claude_session` imports every name back and its methods (which Grok's session
overrides) still call them.
"""
from __future__ import annotations

import re


def _tool_phase(tool: str, tin: dict | None = None) -> str:
    """Etiqueta de fase humana a partir de la tool que el worker acaba de invocar. Para Bash mira el COMANDO
    (demo 2026-07-14: un worker web emitía «ejecutando un paso…» perpetuo — la tarjeta/chip no contaban nada).
    Devuelve "" para NO emitir fase (hbnote: la fase legible la fija el propio reporte, no la pisamos).

    V2-227 ámbito B1 — la frase nombra AHORA el sitio concreto («entrando en booking.com», no «abriendo una
    página…»). El dato ya lo teníamos: `_tool_step` extrae `{where, action, target}` desde V2-048 y el host
    estaba ahí al lado sin llegar nunca al operador. Así que se compone desde ESA estructura, no desde una tabla
    nueva — y por tanto viaja por el mismo carril (`emit("task","phase")` → SSE → `store.tasks`), que es lo que
    pide B4. Si la composición no da nada, se cae a las etiquetas de siempre: una fase genérica es peor que una
    concreta, pero muchísimo mejor que ninguna.
    """
    try:
        from nucleo.workers import progress as _prog
        _st = _tool_step(tool, tin)
        if _st is None:
            return ""                                   # hbnote: su propia fase manda (no pisar)
        _said = _prog.phrase(_st)
        if _said:
            return _said + "…"
    except Exception:  # noqa: BLE001
        pass
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
