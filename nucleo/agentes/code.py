"""nucleo/agentes/code.py — agente de trabajo de CÓDIGO del SlowBrain (V2-007 · T85).

Trabajo que produce/edita código. **Absorbe** dos proveedores del cerebro viejo como agentes de código más:

  - **Widgets** (`widgets/generator.py`): crear un widget nuevo (`generate_widget`) o modificar uno existente
    (`modify_widget`) con el Claude Code atómico del generador. Se conserva su gate de validación/rollback; solo
    cambia quién lo invoca (antes Hermes por tag `[[create]]`/`[[modify]]`, ahora el SlowBrain al escalar).
  - **Architect** (`connectors/architect/service.py`): un encargo (`ask`) al architect-master de un proyecto,
    cuando la petición nombra un proyecto explícito. Operator-only (igual que las tags `[[architect.*]]`).

El resto de código general (arreglar un bug, un script) NO pasa por aquí: el dispatcher lo manda al ramal
genérico (`otros.py`) con la política de tools de código (Read/Write/Edit/Bash). Este módulo es SOLO el
enrutado a los dos proveedores que absorbe.

Las funciones del generador son BLOQUEANTES (subprocess + lock de "un agente a la vez") → se corren en un hilo
(`asyncio.to_thread`) para no bloquear el loop del server.
"""
from __future__ import annotations

import os
import re

from loguru import logger

from .base import WorkResult

# ¿la petición pide un widget? (crear/modificar una tarjeta del canvas)
_WIDGET_RE = re.compile(r"\b(widget|tarjeta|panel|cuadro)\b", re.I)
# intención de MODIFICAR algo existente vs crear (stems con frontera SOLO por delante — deben pillar conjugaciones:
# "modifica", "cambia", "añade", "actualízalo"…).
_MODIFY_RE = re.compile(r"\b(modif|cambi|edit|añad|anad|agreg|actualiz|quit|elimin|update|change|add)", re.I)
# intención de BORRAR el widget entero (NO "quita una columna", que es modificar). El borrado normal lo hace el
# FlashBrain con confirmación (V2-017); esto es la RED del SlowBrain para que una petición de borrado que llegue
# aquí NUNCA acabe creando un widget basura (era el bug: "borra el widget de Meteo" → generó uno nuevo).
_DELETE_RE = re.compile(r"\b(borra|borrar|borre|borrad|delete|remove)\b", re.I)
# intención EXPLÍCITA de CREAR uno nuevo. Solo con un verbo de crear se genera código; sin él, una petición que
# referencia un widget existente se MUESTRA, nunca se crea (V2-023: el bug de "muéstrame el de mensajería" →
# escalaba → generaba un widget basura con el texto de la petición como id).
_CREATE_RE = re.compile(r"\b(crea|crear|cree|cread|haz|hacer|genera|generar|nuev|construy|dise|monta|make|create|build|new)", re.I)
# ¿encargo a un proyecto del Architect? "en el proyecto X" / "al architect de X" / "proyecto X:"
_ARCHITECT_RE = re.compile(r"\barchitect\b|\bproyecto\s+([a-z0-9_-]{2,})", re.I)


def is_widget_request(request: str) -> bool:
    """True si la petición trata de un widget del canvas (crear o modificar)."""
    return bool(_WIDGET_RE.search(request or ""))


def is_architect_request(request: str) -> bool:
    return bool(_ARCHITECT_RE.search(request or ""))


def _catalog_ids() -> list[str]:
    try:
        from widgets import runtime
        return [str(w.get("id") or "").strip() for w in runtime.catalog() if w.get("id")]
    except Exception:
        return []


def _open_widget_ids() -> list:
    """Widgets abiertos ahora en el canvas (contexto de UI del ESTADO) — para desempatar a favor de lo que el
    operador tiene DELANTE. Lectura directa del estado (µs); fail-open a [] si la memoria no está disponible."""
    try:
        from memory import api as memory
        return list(memory.state().get("open_widgets") or [])
    except Exception:
        return []


def _identify_widget(request: str) -> dict:
    """Resuelve la petición a un widget con `widgets.runtime.identify()` (el MISMO identificador que el FlashBrain:
    acento-insensible, keywords/título/descripción, fuzzy de voz), desempatando por el widget ABIERTO en pantalla.
    Devuelve {match, ambiguous, candidates}. Fail-open a un match por substring si el runtime no está disponible."""
    try:
        from widgets import runtime
        return runtime.identify(request, open_ids=_open_widget_ids()) or {"match": None, "ambiguous": False,
                                                                          "candidates": []}
    except Exception:
        n = (request or "").lower()
        for wid in _catalog_ids():
            if wid and wid.lower() in n:
                return {"match": wid, "ambiguous": False, "candidates": [{"id": wid, "title": wid, "score": 1}]}
        return {"match": None, "ambiguous": False, "candidates": []}


def _referenced_widget(request: str) -> str:
    """El widget EXISTENTE que referencia la petición ('' si ninguno claro)."""
    return _identify_widget(request).get("match") or ""


def widget_action(request: str) -> tuple[str, str]:
    """FUENTE ÚNICA de la decisión crear/modificar/borrar de un widget — compartida por el agente parkeado
    (`run`, más abajo) y el backend del generador (`nucleo/workers/generator_session`) para que NUNCA diverjan.

    Regresión que arregla (sesión 2026-07-15): el generador exigía un VERBO de modificar (`_MODIFY_RE`) y
    "Implementar en el widget youtube la capacidad de ampliarse…" NO trae ese verbo → caía a CREATE y generaba
    un widget BASURA con el texto de la orden como id (`implementar-en-el-widget-youtube-la-capa`) en vez de
    MODIFICAR `youtube`. Regla correcta (la que ya tenía `run`): un widget REFERENCIADO/existente + SIN verbo
    explícito de CREAR = MODIFY; un borrado explícito sobre un existente = DELETE; en cualquier otro caso = CREATE.

    Devuelve `(action, target_id)` con action ∈ {"delete","modify","create"} y target_id el widget existente
    (vacío en create). Determinista, acento-insensible vía `_identify_widget` (desempata por el widget ABIERTO)."""
    r = request or ""
    existing = _referenced_widget(r)
    if existing and _DELETE_RE.search(r):
        return ("delete", existing)
    if existing and not _CREATE_RE.search(r):
        return ("modify", existing)
    return ("create", "")


def _architect_project(request: str) -> str:
    m = re.search(r"\bproyecto\s+([a-z0-9_-]{2,})", request or "", re.I)
    return (m.group(1).lower() if m else "")


async def run(task) -> WorkResult:
    """Enruta una petición de código al proveedor que corresponde (widget o architect). Nunca lanza."""
    import asyncio

    req = (task.request or "").strip()
    if not req:
        return WorkResult(ok=True, summary="", deliver=False)

    # ── Architect: encargo a un proyecto nombrado ────────────────────────────────────────────────────────
    if is_architect_request(req) and not is_widget_request(req):
        project = _architect_project(req)
        if project:
            try:
                from connectors.architect import service as architect
                # ask() corre hasta el desenlace y ENTREGA su propio resultado por proactive+[SISTEMA].
                await architect.ask(project, req)
                return WorkResult(ok=True, summary=f"Encargo enviado al architect de «{project}».",
                                  deliver=False, meta={"architect_project": project})
            except Exception as e:  # noqa: BLE001
                logger.warning(f"code: architect ask falló ({project}): {e}")
                return WorkResult(ok=False, error=str(e), deliver=True,
                                  summary=f"No pude enviar el encargo al proyecto {project}.")

    # ── Widgets: BORRAR, modificar o crear ─────────────────────────────────────────────────────────────────
    from widgets import generator, lifecycle

    ident = _identify_widget(req)
    existing = ident.get("match") or ""

    # BORRAR primero (una petición de borrado NUNCA debe caer al ramal de crear). Determinista, sin agente.
    if _DELETE_RE.search(req):
        if not existing:
            return WorkResult(ok=False, deliver=True,
                              summary="No encuentro ese widget para borrarlo; ¿de cuál hablas?")
        logger.info(f"code: DELETE widget '{existing}' (determinista)")
        res = await lifecycle.delete_widget(existing, f"worker:{os.getenv('ZAELAR_TASK_ID', '') or 'code'}")
        if res.get("ok"):
            return WorkResult(ok=True, summary=f"He borrado el widget «{existing}».",
                              deliver=True, meta={"widget_id": existing, "deleted": True})
        return WorkResult(ok=False, error=res.get("error") or "borrado fallido", deliver=True,
                          summary=f"No pude borrar el widget «{existing}».")

    if existing and _MODIFY_RE.search(req):
        logger.info(f"code: MODIFY widget '{existing}'")
        res = await asyncio.to_thread(generator.modify_widget, existing, req)
        if res.get("ok"):
            _show(existing)
            return WorkResult(ok=True, summary=f"He actualizado el widget «{existing}».",
                              deliver=True, meta={"widget_id": existing, "modified": True})
        return WorkResult(ok=False, error=res.get("error") or "modificación fallida", deliver=True,
                          summary=f"No pude modificar el widget «{existing}».")

    # MODIFICAR uno de VARIOS candidatos que empatan y NINGUNO está abierto: sin saber cuál, NO se genera un widget
    # basura — se pide desambiguación (con un verbo de modificar/mostrar y sin verbo de crear explícito).
    if not existing and ident.get("ambiguous") and (_MODIFY_RE.search(req) or not _CREATE_RE.search(req)):
        cands = ident.get("candidates") or []
        names = ", ".join(str(c.get("title") or c.get("id")) for c in cands[:3])
        if names:
            return WorkResult(ok=False, deliver=True, summary=f"¿Cuál de estos quieres, {names}?",
                              meta={"disambiguate": [c.get("id") for c in cands[:3]]})

    # MOSTRAR un widget existente: la petición referencia uno que YA existe y NO hay verbo de crear ("muéstrame/abre/
    # pon el de mensajería"). Jamás genera un widget nuevo — lo abrimos y ya. (Con verbo de crear —"créame otro
    # reloj"— sí cae a CREATE.)
    if existing and not _CREATE_RE.search(req):
        logger.info(f"code: SHOW existing widget '{existing}' (escalada de show→crear evitada)")
        _show(existing)
        return WorkResult(ok=True, summary=f"Te muestro el widget «{existing}».",
                          deliver=True, meta={"widget_id": existing, "shown": True})

    logger.info("code: CREATE widget")
    res = await asyncio.to_thread(generator.generate_widget, req)
    wid = res.get("id") or ""
    if res.get("ok"):
        if wid:
            _show(wid)
        if res.get("existed"):
            return WorkResult(ok=True, summary=f"Ese widget («{wid}») ya existe, te lo muestro.",
                              deliver=True, meta={"widget_id": wid, "existed": True})
        lifecycle.record_created(wid, req)      # ALTA en memoria (creado el <fecha>, para recall futuro)
        return WorkResult(ok=True, summary=f"He creado el widget «{wid}».",
                          deliver=True, meta={"widget_id": wid})
    return WorkResult(ok=False, error=res.get("error") or "generación fallida", deliver=True,
                      summary="No pude crear el widget.")


def _show(wid: str) -> None:
    """Abre la tarjeta del widget en el canvas (best-effort). V2-039: procedencia worker (agente de código)."""
    try:
        from voice.observer import emit
        emit("widget", "show", extra={"id": wid, "src": f"worker:{os.getenv('ZAELAR_TASK_ID', '') or 'code'}"})
    except Exception:
        pass
