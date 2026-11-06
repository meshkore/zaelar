"""rules/vocabulary.py — the scopes and keys a rule may name, READ from declared data (V2-806).

Nothing here is a taxonomy of its own. A scope exists because something declares it:

  · a consent class (genesis `consent.classes`, a manifest action's `consent_class`) → `<domain>/*/<act>`;
  · a channel (a BUILT connector of the catalog that declares a `consent_class`) → `<domain>/<channel>` and, for its
    class, `<domain>/<channel>/<act>`;
  · an installed widget → `widget:<id>`, and each action its manifest declares → `widget:<id>/<action>`;
  · `global`, and `voice` — the agent's own mouth, whose knobs genesis `style` declares;
  · `search` — what a results sheet may show him, whatever was searched (V2-838).

The keys are just as declared: `consent` (allow · ask · never) and `ask_at` (a sensitivity level) for a gate, each
genesis `style` knob for the voice, `excluded` (the names he never wants offered, read by the results sheet's door)
for a search, and `note` for a sentence no code applies.
"""
from __future__ import annotations

from . import defaults as _defaults
from . import scope as _scope


def _widgets() -> list[dict]:
    try:
        from widgets import runtime
        return [w for w in runtime.catalog() if isinstance(w, dict) and w.get("id")]
    except Exception as e:  # noqa: BLE001 — an unreadable catalog leaves the widget scopes out, nothing else
        import logging
        logging.getLogger("zaelar.rules").warning(f"rules: widget catalog unreadable ({e})")
        return []


def _channels() -> list[dict]:
    try:
        from connectors import catalog
        return [m for m in catalog.load_manifests() if m.get("state") == "built" and m.get("consent_class")]
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("zaelar.rules").warning(f"rules: connector catalog unreadable ({e})")
        return []


def classes() -> list[str]:
    """Every consent class a rule may govern: the leaving EVENT TYPES declared once (`nucleo/events/vocabulary`,
    V2-857 phase 1 — before it a class with no genesis default, `errand.mesh_serve`, had no scope and a rule about
    it fell to `global`), plus what genesis, the widget manifests and the built connectors name."""
    from nucleo.events import vocabulary as _evoc
    out = set(_evoc.names(_evoc.OUT))
    out |= {r["origin"].partition(":")[2] for r in _defaults.rows() if r["key"] == "consent"}
    for w in _widgets():
        for spec in (w.get("actions") or {}).values():
            if isinstance(spec, dict) and spec.get("consent_class"):
                out.add(str(spec["consent_class"]))
    out |= {str(m["consent_class"]) for m in _channels()}
    return sorted(c for c in out if "." in c)


def _what(cls: str) -> str:
    """What a class means, as its event type declares it — the model reads this, not the identifier."""
    from nucleo.events import vocabulary as _evoc
    t = _evoc.of(cls)
    return t.what if t else cls


def scopes() -> dict[str, str]:
    """{scope: what it is} for every declared scope a rule may name."""
    out = {_scope.GLOBAL: "everything", _scope.VOICE: "how the agent speaks (voice and chat replies)",
           _scope.SEARCH: "what he is shown when the assistant finds things for him (every results sheet)"}
    chans = _channels()
    for cls in classes():
        domain = cls.partition(".")[0]
        out.setdefault(domain, f"every {domain} act")
        out[_scope.class_scope(cls)] = f"{_what(cls)} ({cls}, on any channel)"
        for m in chans:
            if str(m["consent_class"]).partition(".")[0] == domain:
                cid = str(m["id"]).lower()
                out.setdefault(f"{domain}/{cid}", f"every {domain} act on {m.get('label') or cid}")
                out[_scope.class_scope(cls, cid)] = f"{_what(cls)} ({cls}, on {m.get('label') or cid})"
    for w in _widgets():
        wid = str(w["id"]).lower()
        out[f"widget:{wid}"] = str(w.get("title") or wid)
    return out


def actions_of(widget_id: str) -> set[str]:
    w = next((x for x in _widgets() if str(x["id"]).lower() == widget_id), None)
    return {str(a).lower() for a in ((w or {}).get("actions") or {})}


def declared(sc: str) -> bool:
    """Is this scope (or a `*` pattern over declared segments) something a rule may name?"""
    sc = _scope.norm(sc)
    if sc in scopes():
        return True
    if sc.startswith("widget:") and "/" in sc:
        wid, _, act = sc[len("widget:"):].partition("/")
        return f"widget:{wid}" in scopes() and act in actions_of(wid)
    return sc.startswith("item:") and len(sc) > len("item:")


def nearest(sc: str) -> str:
    """The narrowest declared scope at or above `sc` — what a scope nobody declared becomes."""
    s = _scope.norm(sc)
    segs = s.split("/")
    if len(segs) == 3 and ":" not in s and not declared(s) and declared(f"{segs[0]}/*/{segs[2]}"):
        return f"{segs[0]}/*/{segs[2]}"          # an undeclared channel: the act on any channel
    while s and not declared(s):
        if "/" in s:
            s = s.rsplit("/", 1)[0]
        else:
            return _scope.GLOBAL
    return s or _scope.GLOBAL


def knobs() -> dict[str, object]:
    """{voice knob: genesis value} — the style keys a `pref` row at `voice` may set."""
    return {r["key"]: r["value"] for r in _defaults.rows() if r["scope"] == _scope.VOICE}
