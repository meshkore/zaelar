"""nucleo/flash/wall_lane.py — an order to OPEN a tab of the wall that the name resolver names with certainty (V2-761).

Neutral ground for both channels, like `presence.py`: the voice lane (`voice/engine/llm/providers/fast_lane.py`)
and the probe mirror (`probe_actionmap.try_fast_lanes`) read the SAME verdict, so they cannot drift.

Why a lane and not the model. Measured on the live engine with the operator's own six phrases for the widget
catalogue («enséñame el catálogo de aplicaciones», «o los widgets, ábreme esa lista»…), three rounds each, with a
clean window per phrase: the model called `show_panel` 10-13 times out of 18. The rest it refused («no tengo un
catálogo como tal»), promised with no tool, or — worst — spent a background worker «listing his custom widgets»,
which the tab he named already shows. The same phrase, a different decision each time.

What decides here is not a phrase table. It is the NAME: `widgets.runtime.identify`, the resolver that opens every
card by its name or alias, says the utterance names a system surface that is a tab of the wall — with no widget
matched and no tie — and the utterance is an order to open/show (`looks_like_show_strict`, the grammar the show
backstop already reads, which excludes create and close). The aliases are data (`system_surfaces`), so a new tab,
or a new word for this one, is a data edit. A question («¿qué apps tengo customizadas?») carries no order and
stays with the model, which can answer it from its own catalogue — the rows now say which widgets are his.
"""
from __future__ import annotations


def named_wall_tab(text: str) -> str:
    """The wall tab (`apps`, `apps-custom`, `chat`) this utterance orders open, or "" — fail-closed."""
    try:
        from nucleo.flash import router_guards as _rg
        from nucleo.flash.negation import unnegated_match
        # «No me abras las apps» carries the verb and names the tab; the clause arithmetic both promise gates
        # already share says the verb is negated.
        if not _rg.looks_like_show_strict(text) or not unnegated_match(_rg._SHOW_STRICT_RE, _rg._norm_txt(text)):
            return ""
        from widgets import runtime as _rt
        res = _rt.identify(text) or {}
        if res.get("match") or res.get("ambiguous"):
            return ""
        from nucleo.flash.panel_canon import wall_tab_for
        return wall_tab_for(res.get("system"), text)
    except Exception:  # noqa: BLE001 — a lane that cannot decide leaves the turn to the model
        return ""
