"""An errand that asks for what the resource cannot hold is said, not retried (V2-825 F6, refactor2710-09).

Measured: «mail before 2025-01-01» against a mailbox that starts on 2026-09-04 — the worker kept peeking 2026
threads, went silent twice and was buried with `reason: ""`. The worker's FIRST step now reads the declared window
against the resource's measured reach (`connectors.reach`): a gap ends the errand before any worker spawns, in his
language, with the reason on its row and the verdict `cannot` (which no relaunch path takes). Dates, not words:
the same test holds for a drive or a message archive, in any language.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors import reach as R
from nucleo.workers import reach_gap as G

MAILBOX = R.Reach(family="mail", earliest="2026-09-04T08:12:00Z", source="imap:INBOX:INTERNALDATE")


@pytest.fixture
def mailbox(monkeypatch):
    seen = []
    monkeypatch.setattr(R, "reach", lambda family, provider="": MAILBOX if family == "mail"
                        else R.Reach(family=family, known=False, detail="family_not_declared"))
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        seen.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    return seen


@pytest.mark.parametrize("before, is_gap", [("2025-01-01", True), ("2026-09-04", True), ("2026-10-01", False)])
def test_a_window_older_than_the_reach_is_a_gap(mailbox, before, is_gap):
    found = G.gap({"resource": "mail", "before": before})
    assert (found is not None) is is_gap, found
    if found:
        assert found == {"resource": "mail", "earliest": "2026-09-04", "asked_before": before}


def test_no_window_an_undeclared_family_or_an_unknown_reach_never_blocks(mailbox, monkeypatch):
    assert G.gap(G.window_of(None, {})) is None
    assert G.gap({"resource": "carrier_pigeon", "before": "2025-01-01"}) is None
    monkeypatch.setattr(R, "reach", lambda family, provider="": R.Reach(family="mail", detail="TimeoutError"))
    assert G.gap({"resource": "mail", "before": "2025-01-01"}) is None, "a reach it could not measure is fail-open"


def test_the_comparison_leaves_its_verdict_on_the_timeline(mailbox):
    G.gap({"resource": "mail", "before": "2025-01-01"})
    G.gap({"resource": "mail", "before": "2026-10-01"})
    verdicts = [e["verdict"] for e in mailbox if e["kind"] == "spec" and e["label"] == "reach vs spec"]
    assert verdicts == ["gap", "inside"], mailbox


def test_the_brief_carries_the_window_the_composer_declared():
    import json
    from nucleo.workers.brief_parse import parse
    raw = json.dumps({"research": True, "goal": "find his invoices from 2024", "window": {"resource": "mail", "before": "2025-01-01",
                                                                        "noise": "x"}})
    brief = parse(raw, "find my invoices from 2024")
    assert brief["window"] == {"resource": "mail", "before": "2025-01-01"}
    assert G.window_of(brief, {}) == {"resource": "mail", "before": "2025-01-01"}


def test_the_worker_door_ends_the_errand_on_the_gap_and_spawns_nothing(mailbox, monkeypatch):
    """The door itself: `_run_session` over an errand whose window the mailbox cannot reach says the gap in his
    language, writes the reason on its row, ends `cannot`, and never asks for a backend."""
    from i18n import langs as L
    from nucleo import dispatch
    from nucleo.dispatch import session as dsession, session_steps
    from nucleo.workers.session import SessionRecord
    said, rows = [], []

    async def _say_once(rec):
        said.append(rec.result_summary)

    async def _built(**kw):
        return {"brief": None}

    async def _ctx(req, kind):
        return ""

    monkeypatch.setattr(dispatch, "_SESSIONS", {"91": SessionRecord(task_id="91", goal="facturas de 2024")})
    monkeypatch.setattr(dispatch, "_sem", None)
    monkeypatch.setattr(dispatch, "_deliver_confirm", _say_once)
    monkeypatch.setattr(dispatch, "_task_row", lambda how, rec, **kw: rows.append((how, kw)))
    monkeypatch.setattr(dispatch, "_compose_context", _ctx)
    monkeypatch.setattr(session_steps, "build_what_it_runs_with", _built)
    monkeypatch.setattr(dispatch, "get_backend", lambda *a, **k: pytest.fail("a worker was asked for"))
    rec = dispatch._SESSIONS["91"]
    task = dispatch.Task(id="91", request="find my invoices from 2024", kind="research",
                         context={"window": {"resource": "mail", "before": "2025-01-01"}})
    monkeypatch.setattr(L, "current_language", lambda: L.LANGUAGES["en"])
    asyncio.run(dsession._run_session(task))
    assert said == [L.LANGUAGES["en"].worker_reach_gap.format(asked="2025-01-01", earliest="2026-09-04")], said
    assert rec.verdict == "cannot" and rec.ok is False
    assert rows and rows[-1][0] == "ended_early" and "reaches back to 2026-09-04" in rows[-1][1]["outcome"], rows
    assert "91" not in dispatch._SESSIONS
