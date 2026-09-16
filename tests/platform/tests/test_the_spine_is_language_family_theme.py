"""The Observatory's spine — language above family above theme — and the three ways it can rot.

These are ratchets, not descriptions. Each one exists because the corresponding mistake is cheap to
make and invisible once made: a case with no theme silently disappears from a grouped rail, a case
with no locale silently appears in BOTH markets' scoreboards, and a plan whose ids drift from the
runner's turns the checklist into six boxes that never tick.
"""
from __future__ import annotations

import pytest

from tests.platform import families as fam
from tests.use_cases import plan as planmod
from tests.use_cases import themes
from tests.use_cases.cases_data import CASES
from tests.use_cases.catalog import case_groups


def test_every_use_case_declares_a_locale_the_spine_knows() -> None:
    """A case with an unknown locale is worse than one with none: `belongs_to` shows a case with no
    locale under every language on purpose, so a typo'd one would vanish from both sets instead."""
    unknown = sorted({case.id for case in CASES if case.locale not in fam.LOCALE_IDS})
    assert not unknown, f"casos con un idioma que la espina no conoce: {unknown}"


def test_every_use_case_has_a_theme() -> None:
    """`otros` is the visible parking space for an unclassified case, and this is what keeps it empty.

    Add cases and this test tells you the ids you forgot; it does not tell you which theme they belong
    to, because that is a decision, not a lookup (see `themes.py` on why the table is explicit)."""
    orphans = themes.unclassified(case.id for case in CASES)
    assert not orphans, ("casos de uso sin tema — añádelos a tests/use_cases/themes.py: "
                         f"{orphans}")


def test_the_catalog_groups_by_theme_and_keeps_every_case() -> None:
    """Grouping must not be a filter. A theme table that quietly drops rows would show a shorter,
    tidier and completely wrong board."""
    groups = case_groups()
    assert {g["id"] for g in groups} <= set(themes.THEME_IDS)
    seen = [case["id"] for group in groups for case in group["cases"]]
    assert len(seen) == len(CASES), f"el catálogo agrupado pierde casos: {len(seen)} de {len(CASES)}"
    assert len(set(seen)) == len(seen), "un caso aparece en dos temas"


def test_a_case_carries_its_locale_and_theme_to_the_ui() -> None:
    """The two fields the Observatory indexes on have to survive the catalog adapter — they used to
    live only inside `raw`, where the UI could not reach them, which is why ES and US shared one list."""
    case = next(c for group in case_groups() for c in group["cases"])
    assert case["locale"] in fam.LOCALE_IDS
    assert case["theme"] in themes.THEME_IDS


@pytest.mark.parametrize("locale", fam.LOCALE_IDS)
def test_the_language_selects_a_set_and_never_mixes_them(locale: str) -> None:
    """`belongs_to` is the whole contract of the selector: a localized case belongs to ITS locale only,
    and an unlocalized one (a pytest node, a memory corpus) belongs to every one."""
    other = next(other for other in fam.LOCALE_IDS if other != locale)
    assert fam.belongs_to({"id": "x", "locale": locale}, locale)
    assert not fam.belongs_to({"id": "x", "locale": other}, locale)
    assert fam.belongs_to({"id": "tests/memory/unit/test_db.py::test_opens_in_wal"}, locale)


def test_the_locale_is_read_from_the_id_when_nothing_declares_it() -> None:
    """The scoreboard and the derived scenarios have used a `__es` / `__us` suffix since long before
    this axis existed; the spine reads it rather than asking that corpus to be rewritten."""
    assert fam.locale_of({"id": "book-hotel-night-known__us"}) == "us"
    assert fam.locale_of({"id": "use_cases::es::restaurant-tonight-madrid"}) == "es"
    assert fam.locale_of({"id": "hotel-under-15-days"}) == ""


def test_the_plan_the_catalog_SHOWS_is_the_plan_the_runner_TICKS() -> None:
    """The coupling that actually breaks: `run.py` names its steps with STRING LITERALS.

    Comparing the catalog's plan against `planmod.STEP_IDS` proves nothing — both read the same list,
    so renaming a step moves both and the test stays green while the product is broken (measured here
    on 2026-09-16: that was the first version of this test, and its disarm came back green). What can
    really drift is the runner: rename `judge` in `plan.py` and `run.py` keeps emitting `"judge"`, the
    checklist paints six boxes and one of them never ticks — with nothing red anywhere.

    So this reads the literals OUT of the runner and requires them to be exactly the plan's ids.
    """
    import ast
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[3] / "tests/use_cases/e2e/agent/run.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    emitted: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"step_started", "step_finished"}:
            continue
        assert len(node.args) >= 2 and isinstance(node.args[1], ast.Constant), (
            "un paso nombrado con algo que no es un literal: nadie puede comprobarlo estáticamente")
        emitted.add(node.args[1].value)

    unknown = sorted(emitted - set(planmod.STEP_IDS))
    assert not unknown, f"run.py marca pasos que el plan no declara: {unknown}"
    never = sorted(set(planmod.STEP_IDS) - emitted)
    assert not never, f"el plan declara pasos que nadie marca nunca: {never}"

    published = [step["id"] for step in next(
        c for group in case_groups() for c in group["cases"] if c.get("plan"))["plan"]]
    assert published == list(planmod.STEP_IDS)


def test_a_scenario_id_maps_to_the_catalog_row_it_is_measuring() -> None:
    """The bus's `case_id` is what joins a live round to the row the Observatory already painted. A
    mismatch does not error — it just lights up nothing, which is the hardest kind of bug to notice."""
    from tests.use_cases.e2e.agent import bus

    class _S:
        def __init__(self, sid, locale):
            self.id, self.locale = sid, locale

    assert bus.case_id(_S("hotel-under-15-days", "es")) == "use_cases::es::hotel-under-15-days"
    assert bus.case_id(_S("book-hotel-night-known__us", "us")) == "use_cases::us::book-hotel-night-known"
    # Only the scenario's OWN suffix is stripped — a `__` inside the id is part of the id.
    assert bus.case_id(_S("weird__name", "es")) == "use_cases::es::weird__name"


def test_the_bus_is_silent_without_a_run_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Launched straight from a terminal there is no Observatory, and the round must behave exactly as
    it did before this existed — telemetry is a mirror of the round, never part of it."""
    from tests.use_cases.e2e.agent import bus

    monkeypatch.delenv("ZAELAR_TEST_RUN_DIR", raising=False)
    monkeypatch.setattr(bus, "_writer", None)
    monkeypatch.setattr(bus, "_resolved", False)
    assert bus.enabled() is False
    bus.batch_discovered([])           # must not raise
