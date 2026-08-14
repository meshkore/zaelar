#
# Widget registry — unified READ MODEL for NAMES + ALIASES (V2-082).
#
# One namespace for everything the operator can open by voice/text:
#   • USER WIDGETS — `widgets/<id>/` catalog (manifest). name = manifest.name|title; aliases = manifest.aliases
#                    (or legacy keywords). EDITABLE by the user (tool manage_widget_alias, F3).
#   • SYSTEM SURFACES — `widgets/system_surfaces.py` (front mirror). FIXED aliases, NOT editable.
#
# This is a PROJECTION, not a second source of truth: a widget's identity lives in its manifest, a surface's identity
# in `system-surfaces.js`. This module only JOINS and normalizes them for the resolver (`runtime.identify`), endpoint
# `GET /widgets/registry`, and visibility projection to `memory/state.py` (`widget_registry`).
#
# HARD concept (do not mix): this lists WIDGETS and SYSTEM SURFACES. It does NOT list tools (router.TOOLS), actions
# /data-ops (manifest.actions — the capability of ONE widget, the closest thing to a "skill"), or embeddings (memory only).
#
from __future__ import annotations

from . import runtime, system_surfaces

# Widgets shipped BY DEFAULT with the agent (OSS distribution) — the rest are considered user-created (V2-083).
# Curated, manually editable list (generator's `_STDLIB_EXEMPT` pattern: a hardcoded id, never a manifest field a
# generated widget could grant itself). An explicit manifest `origin` overrides this list (the generator stamps
# `origin:"user"` on what it creates). Anything not here and without origin = "user".
# V2-086: `cluster-registro` left this list when the widget was retired — the NETWORK is a NATIVE surface ("Clusters"
# tab in ChatWall), not a user widget: it is system infrastructure, not something the operator creates.
_BUILTINS = {"agenda", "clock", "timer", "search", "results", "navegador", "mensajeria", "musica", "youtube"}


def origin_of(w: dict) -> str:
    """`builtin` (shipped) | `user` (created by the user). Explicit manifest `origin` wins; otherwise the curated
    `_BUILTINS` list; default `user`."""
    o = str(w.get("origin") or "").strip().lower()
    if o in ("builtin", "user"):
        return o
    return "builtin" if str(w.get("id") or "") in _BUILTINS else "user"


def _norm_aliases(seq) -> list[str]:
    """Dedup preserving order, without empties, defensive cap."""
    out, seen = [], set()
    for a in (seq or []):
        a = str(a or "").strip()
        k = a.lower()
        if a and k not in seen:
            seen.add(k)
            out.append(a)
    return out[:64]


def widget_identity(w: dict) -> dict:
    """Canonical identity for ONE catalog widget: {id, name, aliases, surface:"user"}.
    name = explicit `name` | `title` | id. aliases = manifest `aliases`, or legacy `keywords` as SEED
    (V2-082 D1: keyword ≡ alias). `name` is added as an implicit alias so saying the name always opens it."""
    wid = str(w.get("id") or "")
    name = str(w.get("name") or w.get("title") or wid).strip() or wid
    seed = w.get("aliases")
    if not seed:                                   # no new field → seed from keywords (lazy migration)
        seed = w.get("keywords") or []
    aliases = _norm_aliases([name, *seed])
    return {"id": wid, "name": name, "aliases": aliases, "surface": "user", "origin": origin_of(w)}


def registry() -> list[dict]:
    """Unified registry: user widgets (catalog) + system surfaces. Each entry `{id, name, aliases, surface}`.
    Order: widgets first (like the catalog), then system."""
    out = [widget_identity(w) for w in runtime.catalog()]
    for s in system_surfaces.surfaces():
        out.append({"id": s["id"], "name": s["name"],
                    "aliases": _norm_aliases([s["name"], *s["aliases"]]), "surface": "system", "origin": "system"})
    return out


def project_state() -> list[dict]:
    """COMPACT version for projection to `memory/state.py` (`widget_registry`) — visibility, not source of truth.
    Only id/name/aliases/surface, already normalized. Written by the appropriate caller after catalog/alias changes."""
    return [{"id": r["id"], "name": r["name"], "aliases": r["aliases"], "surface": r["surface"],
             "origin": r.get("origin", "user")} for r in registry()]


def refresh_state() -> list[dict]:
    """Regenerate the registry VISIBILITY projection in `memory/state.py` (`widget_registry`). Called on startup and
    after any catalog (create/delete) or alias (F3) change. Lazy memory import to avoid coupling the widget domain to
    core; best-effort (a projection failure never breaks the resolver)."""
    rows = project_state()
    try:
        from memory import state as _state
        _state.set_widget_registry(rows)
    except Exception:
        pass
    return rows
