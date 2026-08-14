"""widgets/actions.py — CANONICAL SEMANTICS for widget actions (V2-025).

A widget declares an `actions` vocabulary in its `manifest.json` (the widget's **DATA API**: which
mutations its `apply_action()` accepts, with `desc` and `payload`). This module is the ONLY place that
decides **HOW each action runs** from that declaration. The FlashBrain gate, the provider's forced boundary,
and the brain brief all read it. One source of truth, zero divergence.

## The bug it fixes (the `safe` flag was OVERLOADED)

Previously, `"safe": false` combined TWO independent questions:
  (a) "Can the fast layer execute this mutation?" and
  (b) "Is this an IRREVERSIBLE action that requires confirmation?"
`add_meeting` was marked `safe:false`, so it was auto-escalated to a CODE AGENT in the SlowBrain that had
nothing to program (it would only have called the same `apply_action`), took minutes, and once hung for more
than six minutes. A trivial data mutation is NOT code work.

## The new model — THREE modes, two SEPARATE axes

Every DECLARED action is a **data-op**: the FlashBrain executes it immediately by calling the widget's
`apply_action()` (or queues it to the owner for a `backed` widget). It is **NEVER** escalated to a code agent.
The SlowBrain is reserved ONLY for CREATING/MODIFYING a widget's CODE.

  - `FAST` — default: the FlashBrain executes it immediately, without friction.
  - `CONFIRM` — the action is IRREVERSIBLE (pay/send/publish/wipe): the FlashBrain still executes it, but
    asks for confirmation first. Mark it with `"confirm": true` (alias `"irreversible": true`) or infer it
    from a narrow name-and-description heuristic.
  - `ESCALATE` — an EXPLICIT escape hatch (`"escalate": true`) for the rare action that genuinely needs the
    SlowBrain. It is NOT for data mutations.

## Compatibility with existing manifests (legacy `safe` flag)

  - `"safe": true` → `FAST` (same as before: direct and immediate).
  - `"safe": false` → **no longer escalates**: it is `FAST` (or `CONFIRM` if the heuristic matches).
  - absent → `FAST` (or `CONFIRM` by heuristic).
An EXPLICIT `"confirm"`/`"irreversible"`/`"escalate"` always takes precedence over legacy behavior and the heuristic.
"""
from __future__ import annotations

import re

FAST = "fast"          # The FlashBrain executes it immediately.
CONFIRM = "confirm"    # The FlashBrain executes it, but asks for confirmation first.
ESCALATE = "escalate"  # Explicit escape hatch to the SlowBrain; rare and not for data.

# Narrow irreversibility heuristic — deliberately related to `nucleo/danger.py::_DANGER_RE`, but LOCAL to the
# widget module (it must not import from the voice core). Only verbs with real consequences are included:
# pay/purchase/send/publish/delete-account/wipe-all. Reversible actions and blind stems are excluded to avoid
# false positives. It applies to the action NAME and `desc`, both in the manifest language (es/en). An explicit
# `confirm`/`irreversible` flag makes this heuristic unnecessary.
_IRREVERSIBLE_RE = re.compile(
    r"\b(pagar|paga|pago|comprar|compra|publicar|publica|enviar|envia|env[íi]o|mandar|manda|"
    r"eliminar cuenta|borrar cuenta|vaciar|borrar todo|eliminar todo|"
    r"pay|purchase|buy|publish|post\b|send|checkout|delete account|wipe|clear all|empty)\b",
    re.I,
)


def _looks_irreversible(name: str, desc: str) -> bool:
    """Whether the action name/description looks irreversible.

    Deterministic backstop for a generated widget that forgot to mark `confirm:true` on a consequential action.
    """
    return bool(_IRREVERSIBLE_RE.search(f"{name or ''} {desc or ''}"))


def classify(spec: dict | None, name: str = "") -> str:
    """Return the execution mode (`FAST`/`CONFIRM`/`ESCALATE`) from one manifest action spec.

    Precedence: explicit `escalate` → explicit `confirm`/`irreversible` → legacy `safe` (never escalates) →
    irreversibility heuristic. Malformed input falls back to `FAST`; a declared data-op must never accidentally
    become code work.
    """
    spec = spec if isinstance(spec, dict) else {}
    if spec.get("escalate") is True:
        return ESCALATE
    conf = spec.get("confirm")
    if conf is None:
        conf = spec.get("irreversible")
    if conf is None:
        # No reliable new or legacy flag: infer it. (`safe:true` explicitly signals "trivial/reversible", so
        # preserve FAST even if the description contains a strong verb.)
        conf = False if spec.get("safe") is True else _looks_irreversible(name, str(spec.get("desc") or ""))
    return CONFIRM if conf else FAST


def label(mode: str) -> str:
    """Return the human-readable label shown beside each action in the brain brief."""
    return {FAST: "(directa)", CONFIRM: "(confirmar)", ESCALATE: "(escala)"}.get(mode, "(directa)")
