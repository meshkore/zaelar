# ============================================================================
# provenance.py — WHO ordered a widget change (V2-039 · frontend observability).
#
# Each observer canvas event (`kind="widget"`) carries a `src` field that says where the command came from:
#   "flash"        → el FlashBrain, en un turno de voz/chat (tag [[show/close/move/widget.data]] o tool)
#   "worker:<id>"  → a Brain Worker (nucleo/workers/) through bridges (hbweb/hbact/nav_cli / /api/worker/act)
#   "user"         → the operator touching the UI (open/close/move/resize/widget button)
#   "system"       → lifecycle / background / reset / unknown origin
#
# Most emits pass EXPLICIT `src` (direct emit() calls). The ONLY blind spot is the data choke point
# `widgets/store.py::save()` — it receives a mutation without knowing who requested it (widget code, UI click,
# FlashBrain [[widget.data]], a worker...). To attribute it without changing the signature of save() or apply_action
# (widget code), the ORIGIN "notes" its intent just before firing the data-op and save() reads it. Global registry
# (GIL-safe, cross-loop/thread — does not rely on contextvars that do not propagate to widget execution pools), with a
# short TTL: if nobody noted anything in the window, it is "system".
# ============================================================================
from __future__ import annotations

import time

_TTL_S = 15.0                          # an intent expires quickly: attribute the immediate mutation, not the next one
_intent: dict[str, tuple[str, float]] = {}   # widget_id (base) → (src, ts)


def _base(widget_id: str) -> str:
    # normalize the instance id (navegador::t3 → navegador) so note and read match
    return str(widget_id or "").split("::", 1)[0].strip().lower()


def note(widget_id: str, src: str) -> None:
    """The ORIGIN notes that IT is about to change this widget's data NOW. Best-effort, never raises."""
    try:
        _intent[_base(widget_id)] = (str(src or "system"), time.time())
    except Exception:
        pass


def who(widget_id: str) -> str:
    """Who requested the last change for this widget within the TTL; `system` if nobody noted it (or it expired)."""
    try:
        src, ts = _intent.get(_base(widget_id), ("", 0.0))
        if src and (time.time() - ts) <= _TTL_S:
            return src
    except Exception:
        pass
    return "system"
