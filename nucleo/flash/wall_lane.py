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
or a new word for this one, is a data edit. For the catalogue the name alone is enough (see the function); the chat
still needs an order.
"""
from __future__ import annotations


import re as _re

# The catalogue's own nouns, to ask the negation arithmetic whether THEY sit in a negated clause.
_APPS_NOUN_RE = _re.compile(r"\b(apps?|widgets?|aplicacion\w*)\b")


def named_wall_tab(text: str) -> str:
    """The wall tab (`apps`, `apps-custom`, `chat`) this utterance asks for, or "" — fail-closed.

    Two strengths of evidence, one per kind of tab:
      · the CATALOGUE is named only to look at it — his own list of phrases that must open it includes «dime qué
        widgets tengo disponibles», a question with no open verb — so for `apps` the NAME is enough, unless the
        clause naming it is negated or the order is to close or create;
      · the CHAT is named in passing («te lo pongo en el chat»), so it still needs an unnegated open/show order.
        (Conservative, not measured: an unwanted chat panel is the cost it avoids.)"""
    try:
        from nucleo.flash import router_guards as _rg
        from nucleo.flash.negation import unnegated_match
        if _rg.looks_like_create_widget(text) or _rg.looks_like_close(text):
            return ""
        from widgets import runtime as _rt
        res = _rt.identify(text) or {}
        if res.get("match") or res.get("ambiguous"):
            return ""
        from nucleo.flash.panel_canon import wall_tab_for
        tab = wall_tab_for(res.get("system"), text)
        norm = _rg._norm_txt(text)
        if tab.startswith("apps"):
            return tab if unnegated_match(_APPS_NOUN_RE, norm) else ""
        # «No me abras el chat» carries the verb and names the tab; the clause arithmetic both promise gates
        # already share says the verb is negated.
        ordered = _rg.looks_like_show_strict(text) and unnegated_match(_rg._SHOW_STRICT_RE, norm)
        return tab if (tab and ordered) else ""
    except Exception:  # noqa: BLE001 — a lane that cannot decide leaves the turn to the model
        return ""
