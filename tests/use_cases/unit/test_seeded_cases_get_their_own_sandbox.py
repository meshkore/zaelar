"""A memory-SEEDED case never shares a sandbox with another seeded one.

`hard_reset()` between cases kills work, tasks and canvas — deliberately not memory, which is durable by
design. So seeded preferences accumulate, and on 2026-08-20 that manufactured a contradiction no real user
would produce: `weekend-plan-barcelona__es` seeded "loves climbing, especially via ferratas" at 17:59,
`weekend-adventure-sports-bilbao__es` seeded "has a fear of heights" at 18:06, and the second case was graded
on a passive block that served both as equals — four pills alive at once, two of them the same fact in two
languages. That round measured the mechanism honestly and the product not at all, which is the worst kind:
it looks like a finding.
"""
from __future__ import annotations

import argparse

from tests.use_cases.e2e.agent import run as R, scenarios as SC


def _s(sid: str, *, seed=None):
    return SC.UseCaseScenario(id=sid, locale="es", tier=2, persona_brief="p", opening_line="o",
                              success_checks="s", memory_seed=seed)


def _groups(monkeypatch, chosen):
    seen: list[list[str]] = []
    monkeypatch.setattr(R, "_sandbox_batch", lambda g, a, **k: seen.append([s.id for s in g]) or 0)
    R._sandbox_groups(chosen, argparse.Namespace(locale="es", no_file=True, stop_after_failures=0))
    return seen


def test_two_seeded_cases_never_share(monkeypatch):
    got = _groups(monkeypatch, [_s("barcelona", seed=["le gusta escalar"]),
                                _s("bilbao", seed=["tiene vértigo"])])
    assert got == [["barcelona"], ["bilbao"]], got


def test_unseeded_cases_still_share_one_boot(monkeypatch):
    """Sensitivity, and it is what keeps a long walk affordable: boot+prewarm per case for nothing to
    contaminate would triple the wall clock of a 27-case segment."""
    got = _groups(monkeypatch, [_s("a"), _s("b"), _s("c")])
    assert got == [["a", "b", "c"]], got


def test_a_seeded_case_does_not_drag_the_unseeded_ones_with_it(monkeypatch):
    got = _groups(monkeypatch, [_s("a"), _s("seeded", seed=["x"]), _s("b"), _s("c")])
    assert got == [["a"], ["seeded"], ["b", "c"]], got


def test_one_case_is_still_one_boot(monkeypatch):
    assert _groups(monkeypatch, [_s("solo", seed=["x"])]) == [["solo"]]
