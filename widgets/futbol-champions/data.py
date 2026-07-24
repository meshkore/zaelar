#
# Champions League widget — backend. Shows the latest UEFA Champions League results: per match the home/away
# teams and the score. Read-only, foreground-only (computed on demand): there's no keyless live source here, so
# it returns a small set of STATIC example results. If a live source is ever wired, replace `_static_results()`
# with a stdlib fetch (urllib, 6s timeout, desktop UA) and keep the same shape — never raise, always fall back.
#

# Static example results (home, away, home_goals, away_goals). Kept small and clean.
_MATCHES = [
    ("Real Madrid", "Manchester City", 3, 3),
    ("Bayern München", "Arsenal", 2, 2),
    ("Barcelona", "Paris Saint-Germain", 3, 2),
    ("Inter", "Atlético de Madrid", 2, 1),
    ("Borussia Dortmund", "Atalanta", 1, 1),
    ("Liverpool", "Bayer Leverkusen", 4, 0),
]


def _static_results() -> dict:
    matches = []
    for home, away, hg, ag in _MATCHES:
        matches.append({
            "home": home,
            "away": away,
            "home_goals": hg,
            "away_goals": ag,
            "score": f"{hg}-{ag}",
        })
    return {
        "competition": "UEFA Champions League",
        "matchday": "Últimos resultados",
        "matches": matches,
        "live": False,
        "note": "Datos de ejemplo",
    }


def view_data(q: str = "") -> dict:
    try:
        return _static_results()
    except Exception as e:
        return {"competition": "UEFA Champions League", "matches": [], "error": str(e)[:120]}
