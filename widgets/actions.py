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


def is_view(spec: dict | None, name: str = "") -> bool:
    """Whether the action only changes WHAT IS DISPLAYED inside the card (V2-545).

    A SECOND axis, orthogonal to the execution mode above. `classify` answers «how much friction does running
    this cost»; this one answers «is running it the same thing the operator asked for when they only asked to
    LOOK». A view action switches a lens, opens or closes an element, moves between the widget's own screens —
    it never writes anything the operator would have to undo and never reaches the outside world.

    ## Why it exists

    «Ábreme el Telegram» is a pure show order, and the correct answer to it is `show_view {platform:'telegram'}`
    — a data-op. But a pure show order is also exactly where a small model invents a mutation («abre la agenda»
    → `add_meeting` «Reunión con Axa Seguros», measured live 2026-07-16), so the voice rail refuses to run a
    data-op on one. Telling those two apart by reading the TEXT does not work: the first attempt (V2-544)
    compared the words against the widget's manifest aliases, and mensajeria's aliases ARE the names of its
    lenses («whatsapp», «telegram», «correo»), so «ábreme el Telegram» read as «show the card» and the card sat
    there — measured live 2026-09-01, three turns, while «muéstrame SOLO LOS MENSAJES de Telegram» worked only
    because the extra words failed the match. The distinction is not in the phrasing; it is in the ACTION, and
    the widget is the one that knows.

    ## The contract

    Opt-in and EXPLICIT: `"view": true` in the action's manifest spec. Nothing is inferred from the name — the
    same `open` is display-only in mensajeria (opens a chat) and a real-world side effect in navegador (loads a
    URL), so a name heuristic would be wrong in exactly the cases that matter. A widget that declares nothing
    keeps the old behavior (a pure show order only shows its card), which is what every widget did before this.

    An action that needs confirmation or escalates is NEVER a view, whatever the manifest says: `trash` («BORRA
    el correo en el buzón real») must not become runnable by a phrasing.
    """
    spec = spec if isinstance(spec, dict) else {}
    if spec.get("view") is not True:
        return False
    return classify(spec, name) == FAST
