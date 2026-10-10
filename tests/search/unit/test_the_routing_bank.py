"""The routing bank: which search module serves each request (V2-782 T4.2).

Every case fixes what the turn would KNOW — the model's tool proposal, the brief's verdicts, whether a site was
named — and asks the service one question: which module? Deterministic, no model: the model's and Jev's answers
are recorded in the case, which is what makes the precedence rules (CRIT-K2) measurable one by one. A case marked
`open` is a defect the bank has named and nobody fixed: strict xfail, so a silent fix fails until the mark goes.

The count only ratchets up (`_FLOOR`), and the bank is bilingual by contract.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from search import criteria, route

BANK = Path(__file__).resolve().parents[1] / "bank" / "routing.json"
CASES = json.loads(BANK.read_text(encoding="utf-8"))
_FLOOR = 70


def _verdicts(raw: dict) -> dict:
    return {k: tuple(v) if isinstance(v, list) else v for k, v in (raw or {}).items()}


def _param(case: dict):
    marks = [pytest.mark.xfail(strict=True, reason=case["open"])] if case.get("open") else []
    return pytest.param(case, id=case["id"], marks=marks)


@pytest.mark.parametrize("case", [_param(c) for c in CASES])
def test_the_service_routes_the_case_where_it_expects(case):
    proposal = case.get("proposal") or ""
    if case["expect"] == "not_a_search":
        assert not route.is_search_proposal(proposal), f"[{case['id']}] {proposal} must never consult the search service"
        return
    assert route.is_search_proposal(proposal), f"[{case['id']}] the case names a tool that is not a search"
    rt = route.search_route(case["phrase"], proposal=proposal, verdicts=_verdicts(case.get("verdicts")),
                            named_site=bool(case.get("named_site")))
    why = [f"[{case['id']}] «{case['phrase']}» → {rt.module} ({rt.why}, {rt.confidence:.2f}); expected {case['expect']}"]
    assert rt.module == case["expect"], why[0]
    if "n_final" in case:
        assert rt.breadth.get("n_final") == case["n_final"], f"{why[0]} · breadth {rt.breadth}"
    if "fields" in case:
        assert rt.fields == case["fields"], f"{why[0]} · fields {rt.fields}"


def test_the_bank_is_bilingual_and_only_grows():
    assert len(CASES) >= _FLOOR
    assert {c["lang"] for c in CASES} == {"es", "en"}
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    for c in CASES:
        assert c["expect"] in (*route.MODULES, "not_a_search"), c["id"]


def test_the_sure_verdict_decides_and_the_unsure_one_only_completes():
    """CRIT-K2 in two lines: a SURE verdict overrides the proposal, an unsure one does not."""
    sure = route.search_route("x", proposal="search_listings", verdicts={"search_module": ("brain_worker", 0.9)})
    unsure = route.search_route("x", proposal="search_listings", verdicts={"search_module": ("brain_worker", 0.6)})
    assert (sure.module, unsure.module) == ("brain_worker", "listing")


def test_a_judge_is_asked_once_and_only_when_nothing_else_settles_it():
    calls: list = []

    def judge(request, question):
        calls.append(request)
        assert set(question["criteria"]) == set(route.MODULES)
        return "local_service", 0.8

    rt = route.search_route("un dentista cerca", proposal="web_search", judge=judge)
    assert rt.module == "local_service" and len(calls) == 1
    route.search_route("un dentista cerca", proposal="search_listings", judge=judge)
    assert len(calls) == 1, "the proposal settled it; the judge is not paid for"


def test_the_question_names_every_module_once():
    q = route.question()
    assert set(q["criteria"]) == set(route.MODULES)
    assert q["instructions"]


def test_breadth_travels_with_the_route():
    rt = route.search_route("dame tres hoteles baratos en Soria", proposal="search_listings")
    assert rt.breadth["n_final"] == 3 and rt.fields == ["price"]
    assert criteria.breadth("find second-hand campers")["said"] == ""
