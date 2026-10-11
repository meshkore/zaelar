"""A removal the model called over a SURE verdict naming another, non-destructive action on the same card never runs.

Use case `la-cola-de-video-con-palabras-imprecisas` (ES, 2026-10-11): «el último… no, el penúltimo, ponlo justo
después del de skills». The verdict read `screen_action = youtube:move` at 1.00; the fast model called
`remove {item: 4}` on the same card. CRIT-K2 lets a valid model call beat a disagreeing verdict because a wrong
verdict usually costs a reversible view — but here the MODEL's reading was the irreversible one: the video was
deleted from his queue and the reply said «Hecho.» over something he never asked to remove.

The arbiter's rule stays the one `direct_action.complete` spends: the verdict completes the model, it never
contradicts it. A removal is the one call where the model contradicting a sure verdict is the costly reading, so:
  · the model's call REMOVES something (`widgets.contract.is_destructive`, or a `clear` action);
  · the verdict names ANOTHER action of the SAME card, that one not a removal, at ≥ `SURE`;
  · and his own words name no removal (`contract.names_a_removal`) — when he did say «quita», the model's call
    may be half of a two-order sentence and keeps today's rule.
Then the verdict's action runs instead, with the payload his words fill (`direct_action.resolve`: the move's two
rows, via `payload_fill.reorder_fill` / `move_fill`), or with none — and the card's own refusal asks for the
missing half («¿Cuál de los vídeos muevo?»), which `parked_refusal` lets his answer complete. Never the removal.

Both channels ask `instead`: the voice rail through `verdict_card.takes_the_view`, the text channel through
`verdict_card.retarget`. Never raises: an unreadable rule keeps the model's call, as every arbiter here does.
"""
from __future__ import annotations

import re

SURE = 0.9
_CLEAR = re.compile(r"\bclear\b")


def removes(widget_id: str, action: str) -> bool:
    """Does this declared action REMOVE something from the card?"""
    from nucleo.flash import direct_action as _da
    from widgets import contract as _ct
    spec = _ct._spec(_da._base_of(widget_id), action)
    return _ct.is_destructive(spec, action) or bool(_CLEAR.search(str(action or "").replace("_", " ")))


def contradicted(brief, widget_id: str, action: str, said: str = "") -> tuple[str, str]:
    """`(card, verdict action)` when the model's removal contradicts a sure verdict on the same card, else `("", "")`."""
    try:
        from nucleo.flash import direct_action as _da
        from widgets import contract as _ct
        if not action or not removes(widget_id, action):
            return "", ""
        vwid, vact = _da.from_brief(brief)              # re-validated against what is still open
        if not vwid or not vact or vact == action or _da._base_of(vwid) != _da._base_of(widget_id):
            return "", ""
        if removes(vwid, vact) or not _da._action_sure(brief, floor=SURE):
            return "", ""
        if _ct.names_a_removal(said):
            return "", ""
        return vwid, vact
    except Exception:  # noqa: BLE001 — a doubt keeps the model's call
        __import__("logging").getLogger("zaelar.flash").debug("destructive_veto.contradicted failed", exc_info=True)
        return "", ""


def instead(brief, widget_id: str, action: str, said: str = "") -> "tuple[str, str, dict] | None":
    """`(card, verdict action, payload)` to run in place of the model's removal, or None to keep the model's call."""
    vwid, vact = contradicted(brief, widget_id, action, said)
    if not vwid:
        return None
    payload: dict = {}
    try:
        from nucleo.flash import direct_action as _da
        rung = _da.resolve(said, brief=brief, operator_text=said)
        if rung and rung.get("action") == vact and isinstance(rung.get("payload"), dict):
            payload = dict(rung["payload"])
    except Exception:  # noqa: BLE001 — no payload: the card's own refusal asks for it
        __import__("logging").getLogger("zaelar.flash").debug("destructive_veto.instead: no fill", exc_info=True)
    return widget_id, vact, payload


def run(swap: tuple, model_action: str, *, emit, apply_widget_data) -> str:
    """The voice rail: dispatch the verdict's action in place of the removal. Returns the action run."""
    wid, vact, payload = swap
    apply_widget_data(wid, vact, payload)
    emit("brain", "🛡 el modelo quería BORRAR y el veredicto seguro pide otra cosa — corre el veredicto",
         text=f"{wid}: modelo={model_action} · veredicto={vact} {payload}", role="system",
         extra={"cat": "flash", "id": wid, "model": model_action, "verdict": vact, "payload": payload})
    return vact
