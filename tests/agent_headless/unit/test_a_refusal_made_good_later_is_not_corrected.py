"""A refused op that a later write of the SAME card action made good is not «corrected» out loud (refactor2710-99,
node 2.904).

Use case `remember-and-remind-deadline__us` (2026-10-28, 3/5): the first `add_reminder` attempts were refused («notice_at
is missing», «that day is already gone»), the next one landed — `scheduled_jobs` had it — and after his goodbye the
circuit still said «I couldn't set that Wednesday reminder». The refused op's end state was re-read after its grace and
judged unmet, with nothing asking whether a later write of the same card action had landed. Now one did → the entry is
settled with no spoken correction and no note; with no later landing the correction is said as before.

Disarm: make `circuit._made_good_later` return False and the first test goes red.
"""
from __future__ import annotations

import contextvars

import pytest

from memory import db as memdb
from nucleo import circuit
from nucleo.circuit import spec
from nucleo.flash import served_writes
from nucleo.request import model as rq

GONE = {"widget": "agenda", "collection": "meetings", "where": {"title~": "Nope"}}


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db(); memdb.get_db(); spec.reset(); served_writes.reset()
    yield
    spec.reset(); served_writes.reset(); memdb.reset_db()


def _tick(monkeypatch, *, landed_after: bool) -> list:
    from voice import brain_notes
    notes = []
    monkeypatch.setattr(brain_notes, "push", lambda *a, **k: notes.append(a))

    def run():
        rq.begin("remind me on Wednesday to renew the insurance")
        e = spec.open(GONE, text="x", source="flash", widget="agenda", action="add_reminder", now=1000.0)
        e["turn"] = rq.current()
        if landed_after:
            served_writes.note("agenda", "add_reminder", "remind me on Wednesday", {"ok": True}, now=1010.0)
        circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S)
    contextvars.copy_context().run(run)
    return notes


def test_a_refusal_a_later_write_made_good_is_not_corrected(monkeypatch):
    assert _tick(monkeypatch, landed_after=True) == []


def test_without_a_later_landing_the_correction_is_said(monkeypatch):
    assert len(_tick(monkeypatch, landed_after=False)) == 1
