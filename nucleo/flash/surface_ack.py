"""The ack for a turn whose only act was opening a surface (V2-209).

Extracted from `router_guards.py` on the 2026-09-05 ratchet pass (the file had grown past its ceiling and the
ratchet asks for a module, never a taller ceiling). The pair is a closed seam: it reads the widget store and the
browser task registry LAZILY at call time and touches nothing that stayed behind — `router_guards` re-exports
both names so every caller and test keeps working unchanged.
"""
from __future__ import annotations

# ── OPENING A CARD IS NOT DELIVERING A RESULT (V2-209) ────────────────────────────────────────────────────────
def nothing_to_show(widget_id: str) -> bool:
    """Does the surface we just opened have NOTHING in it?

    `_surface_is_empty` (voice provider, 2026-08-17) already answered this for the saved state of a widget and
    only STAMPED it on the observability row — the ack itself kept saying «Aquí lo tienes» over a blank sheet, and
    that was the deliberate scope then. It has a measured cost now: on `book-hotel-night-known__es`
    (2026-08-20 13:49) turn 2 opened the browser card and said «Aquí lo tienes» with the task still working and
    nothing found, and the judge scored it «alucinación de éxito». The phrase is OURS, not the model's — same
    class as the «Hecho.» of V2-176 front 1, and the second time a canned ack has been the thing that lied.

    A BROWSER card is the case the generic check cannot answer: its saved state is not empty (it holds the task),
    so «is the state empty» says «there is something to show» while what it holds is work in progress. With a live
    task, a card is a window on something unfinished — never a delivery. Once nothing is live, the saved state IS
    the answer again.

    Fail-open to False: never claim a surface is empty when we cannot tell (an ack that under-promises on a real
    result is its own kind of wrong).
    """
    wid = (widget_id or "").strip().lower()
    if wid.startswith("navegador"):
        try:
            from widgets.navegador import tasks as _nt
            if _nt.active_progress(limit=6):
                return True
        except Exception:
            return False
    try:
        from widgets import store as _store
        data = _store.load(wid.split("::")[0]) or {}
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    return not any(isinstance(v, (list, tuple, dict)) and len(v) > 0 for v in data.values())


def show_ack(lang, widget_id: str = "", window=None) -> str:
    """The ack for a turn whose only act was opening a surface. Shared so the two channels cannot drift apart:
    this exact phrase failing is what V2-176 measured, and it failed in the channel nobody was looking at."""
    if widget_id and nothing_to_show(widget_id):
        return getattr(lang, "show_ack_empty", None) or lang.show_ack
    return lang.show_ack
