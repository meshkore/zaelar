"""No case shares a sandbox with another — seeded or not (V2-779 F2: conversations write memory too).

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


def test_unseeded_cases_do_NOT_share_a_boot_either(monkeypatch):
    """V2-779 F2: the memory agent distils every CONVERSATION, so an unseeded case still leaves facts behind for
    the next one. One clean engine per case; the boot (~16 s) is small next to the conversation."""
    got = _groups(monkeypatch, [_s("a"), _s("b"), _s("c")])
    assert got == [["a"], ["b"], ["c"]], got


def test_a_seeded_case_does_not_drag_the_unseeded_ones_with_it(monkeypatch):
    got = _groups(monkeypatch, [_s("a"), _s("seeded", seed=["x"]), _s("b"), _s("c")])
    assert got == [["a"], ["seeded"], ["b"], ["c"]], got


def test_one_case_is_still_one_boot(monkeypatch):
    assert _groups(monkeypatch, [_s("solo", seed=["x"])]) == [["solo"]]


def test_a_two_locale_batch_goes_through_the_same_door(monkeypatch):
    """The per-locale branch called `_sandbox_batch` with the whole locale at once: one engine for every ES
    case, seeded or not, and `--rounds` ignored. It must split per case like a one-locale batch."""
    seen: list[list[str]] = []
    monkeypatch.setattr(R, "_sandbox_batch", lambda g, a, **k: seen.append([s.id for s in g]) or 0)
    us = SC.UseCaseScenario(id="u", locale="us", tier=2, persona_brief="p", opening_line="o", success_checks="s")
    R._sandbox_groups_by_locale([_s("a"), _s("b"), us],
                                argparse.Namespace(locale=None, no_file=True, stop_after_failures=0))
    assert sorted(seen) == [["a"], ["b"], ["u"]], seen
