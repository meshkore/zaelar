"""widgets/confirm.py: CONFIRMATION gate for IRREVERSIBLE widget actions (V2-017, V2-025).

Reusable seam for any action requiring explicit OK before execution. Before running it, a pending confirmation is
registered and a "Yes / No" overlay is painted on the canvas card itself. This is host-level, so it works for any
widget and does not touch its `widget.js`. The operator confirms in two ways, both resolving the same pending item:
  - **card button** -> `POST /widgets/{id}/confirm {ok}` -> `resolve()`;
  - **voice** -> deterministic yes/no detection in the provider (`classify_reply`), backed by a tool
    (`confirm_widget_delete`) called by the model.
Without a yes, or after TTL expiry, nothing is executed. Two pending classes exist today:
  - **`delete`**: delete the whole widget (V2-017); execution is handled by `lifecycle.delete_widget`.
  - **`data`**: an irreversible data-op marked `confirm:true` in the manifest (V2-025, sibling of
    `nucleo/danger.py`). On confirmation, the provider dispatches the mutation (`op` = {action, payload}) through
    the same `apply_action`, without escalating to code. That is the point: irreversible does not mean code work.

Process-memory registry, one confirmation per widget. The provider/endpoint execute on resolve in a loop-agnostic
way; `resolve()` is only bookkeeping plus SSE signal.
"""
from __future__ import annotations

import re
import time
import unicodedata

_PENDING: dict[str, dict] = {}     # widget_id -> {action, question, ts}
_TTL = 90.0                        # a confirmation expires after 90s; it must not hang forever


def _emit(action: str, wid: str, extra: dict | None = None) -> None:
    try:
        from voice.observer import emit
        emit("widget", action, extra={"id": wid, **(extra or {})})
    except Exception:
        pass


def _sweep() -> None:
    now = time.time()
    for k in [k for k, v in _PENDING.items() if now - v["ts"] > _TTL]:
        _PENDING.pop(k, None)


# Reserved id for a native surface that also asks for confirmation (V2-086). It is not a catalog widget: it is the
# ChatWall "Clusters" tab. This module's store has always been generic (a dict by key), so reusing it avoids a
# parallel confirmation mechanism. The only specifics are where the Yes/No UI is painted (tab, not card) and who
# resolves it (`/api/meshkore/confirm`, not `/widgets/{id}/confirm`).
NATIVE_CLUSTERS = "clusters"


def request(action: str, widget_id: str, question: str = "", op: dict | None = None,
            notify_ui: bool = True) -> str | None:
    """Register a pending confirmation for `widget_id` and (unless `notify_ui=False`) request the card overlay
    through SSE. Returns the normalized id, or None if the id is invalid.

    `action` is the confirmation class: `"delete"` (delete the widget) or `"data"` (an irreversible data-op).
    For `"data"`, `op` carries the real mutation ({"action": <name>, "payload": {...}}) that the resolver dispatches
    through `apply_action` on confirmation; it never escalates to code.

    `notify_ui=False` (2026-08-15, operator request): some widgets are voice-only by DESIGN — a visual Sí/No
    overlay pinned on the card is unwanted "chrome" for them. The confirmation itself is UNCHANGED (still
    registered, still expires, still resolved the exact same way): this only skips the SSE emit that paints the
    overlay, so voice ("sí"/"no") is the ONLY way to answer. The caller (`nucleo.py`) decides this per widget by
    reading its manifest's `confirm_ui` flag — this module stays widget-agnostic."""
    _sweep()
    wid = (widget_id or "").strip().lower()
    if not wid:
        return None
    # Observability (V2-090 addenda, 2026-08-15): the OPERATOR's yes/no reply lands in its OWN turn — a different
    # trace than the one that asked — and today those show up as two unrelated flows in the master. Capturing the
    # asking turn's trace here lets `resolve()` hand it back so the resolver can adopt it: the confirmation's
    # whole life (ask → answer → executed action) reads as ONE flow, not two.
    try:
        from voice import trace as _trace
        _trace_id = _trace.current()
    except Exception:
        _trace_id = ""
    _PENDING[wid] = {"action": (action or "delete").strip(), "question": (question or "").strip(),
                     "op": op if isinstance(op, dict) else None, "ts": time.time(), "trace_id": _trace_id}
    if notify_ui:
        _emit("confirm", wid, {"action": _PENDING[wid]["action"], "question": _PENDING[wid]["question"]})
    return wid


def pending() -> dict[str, dict]:
    _sweep()
    return dict(_PENDING)


def pending_line() -> str:
    """Line for FlashBrain live state: a confirmation is in flight, so the model must interpret the operator's
    yes/no as the answer to that and call `confirm_widget_delete`, not treat it as conversation. Covers both widget
    deletion and a pending irreversible data-op."""
    _sweep()
    if not _PENDING:
        return ""
    def _what(v: dict) -> str:
        if v.get("action") == "data" and isinstance(v.get("op"), dict):
            return f"la acción «{v['op'].get('action')}»"
        return "el borrado"
    bits = "; ".join(f"«{wid}» — {_what(v)}" for wid, v in _PENDING.items())
    return ("CONFIRMACIÓN PENDIENTE — le pediste al operador que confirme " + bits + ". Si dice que SÍ, llama a "
            "`confirm_widget_delete(confirmed=true)`; si dice que NO, `confirm_widget_delete(confirmed=false)`. "
            "No lo trates como charla nueva.")


def resolve(widget_id: str = "", ok: bool = True) -> dict | None:
    """Resolve one pending confirmation: the one for `widget_id`, or, if no id is provided, the only/latest pending
    confirmation because voice does not always name the widget. Returns {'widget_id', 'action', ...} or None when
    none existed. Bookkeeping only: the caller performs execution in its own loop. If `ok` is False, notify the card
    to remove the overlay."""
    _sweep()
    wid = (widget_id or "").strip().lower()
    p = None
    if wid and wid in _PENDING:
        p = _PENDING.pop(wid)
    elif not wid and len(_PENDING) == 1:
        wid, p = _PENDING.popitem()
    elif not wid and _PENDING:                        # several pending, no id -> the most recent
        wid = max(_PENDING, key=lambda k: _PENDING[k]["ts"])
        p = _PENDING.pop(wid)
    if p is None:
        return None
    if not ok:
        _emit("confirm-cancel", wid)
    return {"widget_id": wid, **p}


# Deterministic yes/no detection (es/en); does not depend on the LLM, same spirit as attention.hard_interrupt.
_YES_RE = re.compile(r"\b(si|sip|claro|vale|venga|dale|adelante|hazlo|hazla|borralo|borrala|"
                     r"confirmo|confirmado|ok|okey|okay|perfecto|yes|yeah|yep|do it|go ahead|confirm)\b")
_NO_RE = re.compile(r"\b(no|nop|cancela|cancelar|cancelalo|dejalo|dejala|para|olvidalo|mejor no|"
                    r"nada|cancel|stop|nevermind|never mind|dont|do not)\b")


def _norm(text: str) -> str:
    n = unicodedata.normalize("NFKD", text or "")
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    return n.replace("'", "").replace("’", "")


def classify_reply(text: str) -> str | None:
    """'yes' | 'no' | None for a turn while a confirmation is pending. Neither side is blindly prioritized: if both
    appear, the last mentioned wins; if neither appears, None means it is not an answer."""
    n = _norm(text)
    y = _YES_RE.search(n)
    no = _NO_RE.search(n)
    if y and no:
        return "yes" if y.start() > no.start() else "no"
    if y:
        return "yes"
    if no:
        return "no"
    return None


def reset() -> None:
    """Clear the registry for tests."""
    _PENDING.clear()
