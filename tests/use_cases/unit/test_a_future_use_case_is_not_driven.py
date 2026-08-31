"""A future case is WRITTEN today and not DRIVEN until its roadmap tasks are complete.

Operator rule (2026-08-21): “all the behaviors I expect should be part of a use case that is as
complete as possible […] you can link the use case to the roadmap tasks, which, once resolved, will
allow that use case to be tested. And so you would never run it right now, because you would know those
tasks are pending […] use cases are the highest point of the pyramid.”

Both halves matter and are tested separately: **writing it** (the request is not lost, and whoever closes
the task has the case that tests it in front of them) and **not driving it** (an entire conversation to
produce a failure that is already written in its initiative, plus a duplicate round archived under the umbrella).

And a third point that is not obvious: **skipping it must NOT be silent**. A case that disappears from the
selection without explanation reads as though it does not exist, which is exactly the opposite of what the rule requires.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tests.use_cases.e2e.agent import run as R, scenarios as SC, segments as G

INITIATIVES = Path(__file__).resolve().parents[3] / ".meshkore" / "roadmap" / "initiatives"


def _args(**kw):
    base = dict(scenario="all", verify=False, tier=None, locale="es", segment=None, limit=None,
                start_at=None, include_blocked=False, sandbox=False, lab="", no_file=True,
                stop_after_failures=0, rounds=1, allow_dirty=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _selected(monkeypatch, **kw) -> list[str]:
    got: list[str] = []
    monkeypatch.setattr(R, "_sandbox_groups", lambda chosen, a, **k: got.extend(s.id for s in chosen) or 0)
    monkeypatch.setattr(R, "_run_batch", lambda chosen, **k: got.extend(s.id for s in chosen) or 0)
    R.run(_args(sandbox=True, **kw))
    return got


def test_a_blocked_case_is_not_in_the_batch(monkeypatch):
    got = _selected(monkeypatch)
    assert "repeat-a-finished-search" not in got
    assert "candidates-already-known" not in got
    assert "change-the-criteria-not-the-search" not in got


def test_a_gate_LIFTS_when_its_mechanism_lands(monkeypatch):
    """The other side of the ratchet, and the one people forget. `two-searches-two-sheets` was gated by
    V2-259 and stopped being gated on 2026-08-21 when the complete initiative landed (`b8a1415` + `f3052f9`).
    A gate that nobody removes turns a built case into one that is NEVER measured, and the scoreboard
    does not say so: the row simply does not appear, as if it did not exist."""
    got = _selected(monkeypatch)
    assert "two-searches-two-sheets" in got
    assert not G.blocked_by("two-searches-two-sheets")


def test_the_rest_of_the_catalog_is_untouched(monkeypatch):
    """SENSITIVITY, and this is the costly side: over-gating silently shrinks the run and invalidates measures that are already
    on the scoreboard. The gate is per case that DECLARES it, never for the entire `capability` group."""
    got = _selected(monkeypatch)
    assert "three-tasks-at-once" in got
    assert "restaurant-tonight-madrid" in got
    blocked = {s.id for s in SC.all_scenarios() if G.blocked_by(s.id)}
    assert len(got) == len([s for s in SC.all_scenarios() if s.locale == "es"]) - len(
        [b for b in blocked if SC.registry()[b].locale == "es"])


def test_skipping_is_announced_with_the_tasks_that_gate_it(monkeypatch, capsys):
    _selected(monkeypatch)
    out = capsys.readouterr().out
    assert "caso(s) de FUTURO" in out
    assert "repeat-a-finished-search" in out
    assert "V2-260" in out


def test_include_blocked_forces_them_in(monkeypatch):
    """The hatch exists because the case IS drivable—it is only known that it will fail. Forcing it is how
    the evidence that goes into the initiative is produced."""
    got = _selected(monkeypatch, include_blocked=True)
    assert "repeat-a-finished-search" in got


def test_every_gate_points_at_an_initiative_that_EXISTS():
    """Without this, renaming an initiative leaves the gate citing something that is not there—and a case blocked by a
    nonexistent task is NEVER driven, and nobody knows what needs to be done to unblock it.

    The PREFIX (`V2-259`) is checked, not the phase, because the phase lives inside the document; what has
    to exist is the document.
    """
    for scn in SC.all_scenarios():
        for ref in G.blocked_by(scn.id):
            num = ref.split()[0]
            hits = list(INITIATIVES.glob(f"{num}-*.md"))
            assert hits, f"{scn.id} bloqueado por {ref} y no existe ninguna iniciativa {num}-*.md"


def test_a_future_case_still_says_what_it_expects():
    """The WRITING half: a gated case without criteria is a note, not a use case—and when it is
    unblocked, the bar would have to be invented, which is when it gets invented in favor of what it already does."""
    for scn in SC.all_scenarios():
        if not G.blocked_by(scn.id):
            continue
        assert len(scn.success_checks) > 400, scn.id
        assert len(scn.persona_brief) > 400, scn.id
        assert scn.opening_line.strip(), scn.id
