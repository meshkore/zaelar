#
# Widget registry — READ-MODEL unificado de NOMBRES + ALIAS (V2-082).
#
# Un solo espacio de nombres para todo lo que el operador puede abrir por voz/texto:
#   • WIDGETS DE USUARIO  — catálogo `widgets/<id>/` (manifest). name = manifest.name|title; aliases = manifest.aliases
#                           (o, legacy, keywords). EDITABLES por el usuario (tool manage_widget_alias, F3).
#   • SUPERFICIES DE SISTEMA — `widgets/system_surfaces.py` (espejo del front). Alias FIJOS, NO editables.
#
# Es una PROYECCIÓN, no una segunda fuente de verdad: la identidad de un widget vive en su manifest, la de una
# superficie en `system-surfaces.js`. Este módulo solo las UNE y normaliza para el resolver (`runtime.identify`), el
# endpoint `GET /widgets/registry` y la proyección de visibilidad a `memory/state.py` (`widget_registry`).
#
# Concepto DURO (sin mezclar): esto lista WIDGETS y SUPERFICIES DE SISTEMA. NO lista tools (router.TOOLS), ni acciones
# /data-ops (manifest.actions — la capacidad de UN widget, lo más cercano a "skill"), ni embeddings (solo memoria).
#
from __future__ import annotations

from . import runtime, system_surfaces


def _norm_aliases(seq) -> list[str]:
    """Dedup preservando orden, sin vacíos, cap defensivo."""
    out, seen = [], set()
    for a in (seq or []):
        a = str(a or "").strip()
        k = a.lower()
        if a and k not in seen:
            seen.add(k)
            out.append(a)
    return out[:64]


def widget_identity(w: dict) -> dict:
    """Identidad canónica de UN widget del catálogo: {id, name, aliases, surface:"user"}.
    name = `name` explícito | `title` | id. aliases = `aliases` del manifest, o `keywords` legacy como SEMILLA
    (V2-082 D1: keyword ≡ alias). El `name` se añade como alias implícito para que decir el nombre siempre abra."""
    wid = str(w.get("id") or "")
    name = str(w.get("name") or w.get("title") or wid).strip() or wid
    seed = w.get("aliases")
    if not seed:                                   # sin campo nuevo → sembramos de keywords (migración perezosa)
        seed = w.get("keywords") or []
    aliases = _norm_aliases([name, *seed])
    return {"id": wid, "name": name, "aliases": aliases, "surface": "user"}


def registry() -> list[dict]:
    """Registro unificado: widgets de usuario (catálogo) + superficies de sistema. Cada entrada
    `{id, name, aliases, surface}`. Orden: widgets primero (como el catálogo), luego sistema."""
    out = [widget_identity(w) for w in runtime.catalog()]
    for s in system_surfaces.surfaces():
        out.append({"id": s["id"], "name": s["name"],
                    "aliases": _norm_aliases([s["name"], *s["aliases"]]), "surface": "system"})
    return out


def project_state() -> list[dict]:
    """Versión COMPACTA para proyectar a `memory/state.py` (`widget_registry`) — visibilidad, no fuente de verdad.
    Solo id/name/aliases/surface, ya normalizado. La escribe el que corresponda tras un cambio de catálogo/alias."""
    return [{"id": r["id"], "name": r["name"], "aliases": r["aliases"], "surface": r["surface"]}
            for r in registry()]


def refresh_state() -> list[dict]:
    """Regenera la proyección de VISIBILIDAD del registro en `memory/state.py` (`widget_registry`). Se llama al
    arrancar y tras cualquier cambio de catálogo (create/delete) o de alias (F3). Import perezoso de la memoria para
    no acoplar el dominio de widgets al core; best-effort (un fallo de proyección jamás rompe el resolver)."""
    rows = project_state()
    try:
        from memory import state as _state
        _state.set_widget_registry(rows)
    except Exception:
        pass
    return rows
