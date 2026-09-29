"""The SCOPE of a spoken rule — which prompts carry it (2026-09-29).

Rules are hierarchical: genesis per domain (`style`, `consent`, `library`, `errands`, `playbooks`, each with its
own override file) and, above it, the operator's spoken rules. One fixed classifier names the scope the moment a
rule is set — never a model, and the doubt always goes to `general`, which is what every rule got before:

  · `voice`        — a manner of speaking (the style flags, brevity, tone, address): the FlashBrain's own line;
                     the brain worker never carries it (`memory.rules_for("worker")`).
  · `widget:<id>`  — a rule that NAMES exactly one card («en la agenda, las reuniones siempre de 30 minutos»):
                     composed in that widget's own row of the resources block (`widgets/brief.py`), every turn —
                     an order about the agenda comes before the agenda is open — and carried by the worker too.
  · `general`      — everything else: every prompt that carries the memory context, exactly as before.

`memory` never classifies (it owes nucleo nothing): the directive handler asks here and stores the answer.
"""
from __future__ import annotations

from nucleo import style_policy as _style


def scope_of(text: str) -> str:
    """`voice` | `widget:<id>` | `general`. Deterministic; never raises."""
    t = (text or "").strip()
    if not t:
        return "general"
    try:
        if _style.scope_of(t) == "voice":
            return "voice"
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo.flash import direct_action as _da
        named = _da.named_cards(t)
        if len(named) == 1 and named[0]:
            return f"widget:{str(named[0]).split('::')[0].strip().lower()}"
    except Exception:  # noqa: BLE001
        pass
    return "general"
