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

from tests.use_cases.cases_data import CASES, UseCase

_LOCALE_LABELS = {"es": "Spain", "us": "United States"}


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
        entry["execution_path"] = ["DRIVE model (probe channel, execute=true)", "FlashBrain",
                                   "escalate_to_slowbrain", "Brain Worker + browser", "observability flow",
                                   "watchdog", "judge"]
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
            "nested_events": False,
            "requires_live": True,
        }
    return entry


def case_groups() -> list[dict[str, Any]]:
    groups = []
    for locale in ("es", "us"):
        locale_cases = sorted(
            (case for case in CASES if case.locale == locale),
            key=lambda case: (case.tier, case.id),
        )
        cases = [_case_dict(case, index) for index, case in enumerate(locale_cases, start=1)]
        groups.append({
            "id": locale,
            "label": _LOCALE_LABELS[locale],
            "mode": "backlog · ordered by difficulty tier (1=easiest .. 7=hardest)",
            "count": len(cases),
            "cases": cases,
        })
    return groups
