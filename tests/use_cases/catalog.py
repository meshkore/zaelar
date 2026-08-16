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
    return {
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
        # No "execution" key: this case is not runnable yet.
    }


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
