"""Observatory catalogue adapter for the ES/US real-world use-case backlog.

Every case here is backlog metadata, not yet wired to a runner (see
``cases_data.py`` module docstring). Deliberately omitting the ``execution``
key on each case is safe: ``tests.platform.catalog.normalize_case`` defaults
it to ``{}``, and the CLI's ``_resolve_case`` treats a case with no
``execution`` as "not part of the executable catalog" — a clean error instead
of silently falling back to collecting the whole repository's pytest suite.
"""
from __future__ import annotations

from typing import Any

from tests.use_cases import plan, themes
from tests.use_cases.cases_data import CASES, UseCase



def _case_dict(case: UseCase, ordinal: int) -> dict[str, Any]:
    note = ""
    if case.status == "blocked":
        note = "BLOCKED — depends on: " + "; ".join(case.depends_on)
    elif case.status == "promoted":
        note = "Dynamic, non-deterministic scenario — see tests/use_cases/e2e/agent/scenarios.py"
    entry: dict[str, Any] = {
        "id": f"use_cases::{case.locale}::{case.id}",
        "ordinal": ordinal,
        "title": case.title,
        # No "type" label: every case in this suite is a use-case, so a static
        # per-row "USE-CASE" tag adds no information — only the tier does.
        "type": "",
        "dimension": f"Tier {case.tier}",
        # The PRIMARY index of the Observatory. It was already here inside `raw`, where the UI could
        # not index on it — which is why ES and US cases shared one list and one «7/24 verdes» that
        # was a number about two different products (tests/platform/families.py).
        "locale": case.locale,
        # WHAT the person is trying to do (tests/use_cases/themes.py). The tier says how hard, the
        # locale says which market; without this the rail lists twenty `search-buy-*` rows one by one
        # and buries the fact that «vídeo» has four cases and «documentos» three.
        "theme": themes.theme_of(case.id),
        "input": {"locale": case.locale, "tier": case.tier, "utterance": case.utterance},
        "expected": {"outcome": case.expected},
        "verification": "backlog entry — no runner wired yet, see tests/use_cases/CASES.md",
        "execution_path": [],
        "source": "tests/use_cases/cases_data.py",
        "note": note,
        "raw": {"tier": case.tier, "locale": case.locale, "status": case.status,
                "depends_on": list(case.depends_on)},
        # No "execution" key by default: a backlog/blocked case is not runnable yet.
    }
    if case.status == "promoted":
        entry["verification"] = ("dynamic LLM-driven scenario: driver negotiates the goal over the "
                                 "probe channel, a watchdog detects drift, verify.py confirms the real "
                                 "worker/browser mechanism fired, a judge scores the outcome")
        # The DECLARED plan — the same ids the runner ticks live (tests/use_cases/plan.py). It used to
        # list the internal path the stimulus takes (FlashBrain → slowbrain → worker), which reads
        # like an architecture diagram and never moves while the case runs. What the operator watches
        # is the round's own agenda.
        entry["execution_path"] = plan.labels()
        entry["plan"] = [{"id": step["id"], "label": step["label"], "optional": bool(step.get("optional"))}
                         for step in plan.STEPS]
        entry["execution"] = {
            "kind": "command",
            # `--sandbox` is NOT optional here. Without it, `python -m tests run use_cases` —the entry point
            # that the project's CLAUDE.md instructs ANY agent to use— runs the primary case against the
            # operator's LIVE engine: its memory, widgets, and tasks in progress, consuming its
            # providers. Confirmed by stumbling into it on 2026-08-21 (16 real turns against 43917, with the
            # verdict written to the shared scoreboard as if it were a measurement). It is the SAME pattern as the
            # `--lab` failure that was fixed hours earlier: isolation cannot depend on whoever launches it
            # remembering to request it.
            "argv": ["{python}", "-m", "tests.use_cases.e2e.agent.run", "--scenario", case.id, "--sandbox"],
            "nested_events": True,
            "requires_live": True,
        }
    return entry


def case_groups() -> list[dict[str, Any]]:
    """The catalog grouped by THEME, not by locale.

    It used to be one group per locale, which made sense while the locale was just another column. It
    is now the Observatory's primary index — the operator picks ES or US at the top and gets a different
    SET — so grouping by it again below would be the same split twice, and it left the real question
    («what KIND of thing is this hundred-row list testing?») unanswered.

    Every group carries both locales' cases; the UI filters them by the selected one. That is deliberate:
    a theme that exists in ES and not in US is a real gap in the American set, and it should be visible
    as an empty group rather than as a group that does not exist.
    """
    ordered = {theme["id"]: [] for theme in themes.THEMES}
    for case in sorted(CASES, key=lambda c: (c.tier, c.id, c.locale)):
        ordered.setdefault(themes.theme_of(case.id), []).append(case)
    groups = []
    for theme in themes.THEMES:
        rows = ordered.get(theme["id"]) or []
        if not rows and theme["id"] == "otros":
            continue          # no unclassified cases is the healthy state, and an empty group says nothing
        groups.append({
            "id": theme["id"],
            "label": theme["label"],
            "mode": theme["hint"],
            "count": len(rows),
            "cases": [_case_dict(case, index) for index, case in enumerate(rows, start=1)],
        })
    return groups
