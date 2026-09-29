"""The operator's spoken rules and their scope (2026-09-29) — the one home of the filter.

`state.rules` is a flat list of ≤8 sentences (its shape never changed: every old reader keeps working);
`state.rule_scopes` maps the normalised text of a rule to its scope when it is not the default. The scope is
decided by the CALLER (`nucleo.flash.rule_scope`, a fixed classifier) — memory owes nucleo nothing.

Surfaces and what they carry:
  · "voice"        → general + voice   (the FlashBrain's REGLAS line; widget rules ride in the widget's row)
  · "worker"       → general + widget:* (a manner of speaking means nothing to a browser errand)
  · "widget:<id>"  → that widget's rules
  · anything else  → everything (fail open, like before)
"""
from __future__ import annotations

import re
import unicodedata

DEFAULT_SCOPE = "general"


def norm(text: str) -> str:
    n = unicodedata.normalize("NFKD", (text or "").strip().lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", n).split())     # sin acentos ni puntuación, espacios colapsados


def _carries(surface: str, scope: str) -> bool:
    if surface == "voice":
        return scope in (DEFAULT_SCOPE, "voice")
    if surface == "worker":
        return scope == DEFAULT_SCOPE or scope.startswith("widget:")
    if surface.startswith("widget:"):
        return scope == surface
    return True


def for_surface(st: dict, surface: str) -> list:
    """The rules this SURFACE carries, in their stored order."""
    rules = [str(r).strip() for r in ((st or {}).get("rules") or []) if str(r).strip()]
    scopes = st.get("rule_scopes") if isinstance((st or {}).get("rule_scopes"), dict) else {}
    surface = str(surface or "")
    return [r for r in rules if _carries(surface, str(scopes.get(norm(r), DEFAULT_SCOPE)))]


def by_widget(st: dict) -> dict:
    """{widget id: [rules]} for every rule scoped to a widget."""
    out: dict = {}
    scopes = st.get("rule_scopes") if isinstance((st or {}).get("rule_scopes"), dict) else {}
    for r in ((st or {}).get("rules") or []):
        r = str(r).strip()
        sc = str(scopes.get(norm(r), DEFAULT_SCOPE))
        if r and sc.startswith("widget:"):
            out.setdefault(sc.split(":", 1)[1], []).append(r)
    return out
