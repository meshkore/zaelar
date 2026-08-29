"""Launch phases — the OPERATOR-OWNED boundary of what production v1 promises (INI-026, 2026-08-29).

«Tener algún sitio donde yo diga: esto es TODO lo que se puede hacer en la versión de producción» — this
module is that place. PHASE 1 is the delimited v1 scope: the feature set the product guarantees at launch,
each feature carried by its use case(s). Everything else promoted is PHASE 2: not yet proven, more complex,
or deliberately later (two-agent meetings, connectors, tier 4-7). The boundary is membership by BARE id
(locale twins inherit it: a red twin inside phase 1 is honest work-to-close, not a reason to move the line).

Editing rule: this list is the operator's launch decision. Agents may PROPOSE moving a case across the line
(with its measurement); the move itself is the operator's call. The Observatory renders the scoreboard split
by this module, and the supervisor accepts `--phase 1` to run exactly this battery.
"""
from __future__ import annotations

#: Bare ids (no __locale suffix) of the features production v1 promises.
PHASE1: frozenset[str] = frozenset({
    # media — play, watch, curate
    "play-music-and-build-playlist",
    "watch-a-video-not-listen-to-it",
    "find-videos-on-a-topic-no-ai-slop",
    "build-a-video-playlist-from-links",
    # images on screen
    "show-real-photo-of-a-new-car",
    # native widgets & creation
    "build-workout-tracker-widget",
    # facts in the turn
    "quick-fact-opening-hours",
    # agenda + reminders (the INI-026 A2 litmus)
    "remember-and-remind-deadline",
    "dentist-appointment-into-agenda",
    # several errands at once
    "three-tasks-at-once",
    # search/compare/buy — the family measured green
    "cheapest-monitor",
    "hotel-under-15-days",
    "find-best-hotel-city",
    "search-buy-camera",
    "search-buy-guitar",
    "search-buy-motorcycle",
    "search-secondhand-monitor",
})


def bare(scenario_id: str) -> str:
    sid = str(scenario_id or "")
    for suf in ("__es", "__us"):
        if sid.endswith(suf):
            return sid[: -len(suf)]
    return sid


def phase_of(scenario_id: str) -> int:
    """1 = inside the production v1 promise; 2 = later/unproven/complex."""
    return 1 if bare(scenario_id) in PHASE1 else 2


#: Locale twins parked for an ENVIRONMENTAL blocker, with the reason stated (operator rule, 2026-08-29).
#: A twin belongs here only when both hold: (a) its blocker comes from the outside world of that locale —
#: geo-fencing, IP-based pricing, a region wall — not from our code, and (b) the sibling twin is MEASURED
#: green, so the capability itself is proven. Rationale: a wall a real user standing in that country would
#: never hit must not hold the launch. Parking is not passing: the case stays visible with its 🌍 flag and
#: its reason, and it leaves the launch gauge's denominator instead of pretending to be green.
GEO_PARKED: dict[str, str] = {
    "cheapest-monitor__us": (
        "Amazon geolocaliza por IP: aun con un perfil en-US limpio sirve «Deliver to Spain» y precios de "
        "España. El gemelo ES está verde (4/5), así que la capacidad está probada; desde una IP de EEUU "
        "el muro no existe."
    ),
}


def parked_reason(scenario_id: str) -> str:
    """The environmental reason this twin is parked, or "" if it is measured normally."""
    return GEO_PARKED.get(str(scenario_id or ""), "")
