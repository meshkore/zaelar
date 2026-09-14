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
_BUILTINS = {"agenda", "clock", "timer", "search", "results", "navegador", "mensajeria", "musica", "youtube",
             "imagenes", "contactos", "documento", "archivos", "fotos", "torrent"}


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


def display_name(kind: str, wid: str, fallback: str) -> str:
    """The name the operator READS for this piece, in their own language (V2-694).

    A manifest's `name` is written once, by whoever built the widget, in whatever language they wrote it — ours
    are Castilian, and that is exactly what an English session was reading on every card header. The label is a
    UI string like any other, so it lives where every other UI string lives: `i18n/bundles/en.json` (the source
    of truth) + `es.json`, under `widgets.<id>.name` / `surfaces.<id>.name`, which means a language onboarded
    later gets it translated by the SAME generation pass as the rest of the interface, for free.

    The manifest keeps its `name`, and it is not dead weight: it is the FALLBACK (a widget the bundles have
    never heard of — a generated one, a fork — still has a name) and it stays in `aliases`, so the word the
    widget was born with never stops opening it.
    """
    try:
        from i18n import runtime as _i18n
        return _i18n.text(f"{kind}.{wid}.name", fallback) or fallback
    except Exception:  # noqa: BLE001 — an unreadable bundle names the widget as its manifest does, never crashes
        return fallback


def widget_identity(w: dict) -> dict:
    """Canonical identity for ONE catalog widget: {id, name, aliases, surface:"user"}.

    name = the operator's-language label (`widgets.<id>.name`), falling back to explicit `name` | `title` | id.
    aliases = manifest `aliases`, or legacy `keywords` as SEED (V2-082 D1: keyword ≡ alias).

    BOTH the translated name and the manifest one are implicit aliases, and that pair is the whole safety of
    V2-694: the resolver keeps answering to the word the widget shipped with («mensajería») while the screen and
    the prompt use the word the operator reads («Messaging»). Translating the name WITHOUT keeping the original
    would silently retire half the vocabulary of every install that ever spoke Castilian.
    """
    wid = str(w.get("id") or "")
    native = str(w.get("name") or w.get("title") or wid).strip() or wid
    name = display_name("widgets", wid, native)
    seed = w.get("aliases")
    if not seed:                                   # no new field → seed from keywords (lazy migration)
        seed = w.get("keywords") or []
    aliases = _norm_aliases([name, native, *seed])
    return {"id": wid, "name": name, "aliases": aliases, "surface": "user", "origin": origin_of(w),
            "forked": bool(w.get("forked_from"))}


def registry() -> list[dict]:
    """Unified registry: user widgets (catalog) + system surfaces. Each entry `{id, name, aliases, surface}`.
    Order: widgets first (like the catalog), then system."""
    out = [widget_identity(w) for w in runtime.catalog()]
    for s in system_surfaces.surfaces():
        native = s["name"]
        name = display_name("surfaces", s["id"], native)
        out.append({"id": s["id"], "name": name,
                    "aliases": _norm_aliases([name, native, *s["aliases"]]),
                    "surface": "system", "origin": "system"})
    return out


def project_state() -> list[dict]:
    """COMPACT version for projection to `memory/state.py` (`widget_registry`) — visibility, not source of truth.
    Only id/name/aliases/surface, already normalized. Written by the appropriate caller after catalog/alias changes."""
    return [{"id": r["id"], "name": r["name"], "aliases": r["aliases"], "surface": r["surface"],
             "origin": r.get("origin", "user"), "forked": bool(r.get("forked"))} for r in registry()]


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
