"""V2-711 T1.4 · A shadow mode has a reader, or it is a function that runs and is thrown away.

## What was measured (2026-09-16)

Three mechanisms in this engine run in SHADOW — they decide, they log a verdict, and they change nothing:

  · `nucleo/canvas_arbiter.py` (V2-653 F0, `kind="arbiter"`), whose promotion gate is declared in writing as
    *«CERO vetos falsos sobre sus sesiones reales, auditado desde los veredictos en sombra»*;
  · `nucleo/errands/wake.py`, where errands ship shadow-by-default because autonomy that writes to real
    people in the operator's name is handed over after he has read a few of those rows;
  · and, from T1.3, the browser's consequence-side click signal (`kind="gate_shadow"`).

**None of them had a reader.** No `/api/observability` route, no report, no counter. So the condition that
arms the first one could not be evaluated, and two initiatives sat waiting on a number nobody could produce.

The shape is what matters: a shadow phase is a deliberate, cheap way to earn an armed rail — and without a
reader it is indistinguishable from dead code that costs CPU. This is the reader.

⚠️ It reports `measured` separately from the count, because a window with no verdicts and a mechanism that
never ran look identical from a zero and mean opposite things — the same rule the errand shadow gate already
states: «a log with no decisions says so instead of printing a reassuring zero over nothing».
"""
from __future__ import annotations

import json
import time

import pytest

from observability import flows


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """An ISOLATED events table — this must never read the operator's real database."""
    from bus import log as blog
    # ⚠️ The path comes from `ZAELAR_DB` through `db_path()`, and `_conn` is a module-level CACHE — patching
    # a name that does not exist (`_DB`) left the fixture a silent no-op reading the operator's REAL
    # database, which is how the first run of this file reported seven rows it had not written. The env var
    # AND the cached connection both have to move, and the connection has to be restored afterwards.
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "t.db"))
    real_conn = blog._conn
    blog._conn = None
    yield_now = time.time() * 1000.0
    now = yield_now

    def _ev(kind, rule, allow=None, text="", ago_ms=0.0):
        payload = {"kind": kind, "text": text, "extra": {"rule": rule}}
        if allow is not None:
            payload["extra"]["allow"] = allow
        with blog._lock:
            conn = blog._connect()
            names = ", ".join(c[0] for c in blog._COLUMNS)
            marks = ", ".join("?" for _ in blog._COLUMNS)
            cols = blog._columns_from(payload)
            conn.execute(
                f"INSERT INTO events (ts_ms, topic, payload, {names}) VALUES (?, ?, ?, {marks})",
                (now - ago_ms, "observer", json.dumps(payload), *cols))
            conn.commit()
    try:
        yield _ev
    finally:
        try:
            if blog._conn is not None:
                blog._conn.close()
        except Exception:
            pass
        blog._conn = real_conn


def test_a_shadow_verdict_is_readable_and_broken_out_by_its_RULE(seeded):
    seeded("arbiter", "data-drag", allow=False, text="data agenda:clear_range")
    seeded("arbiter", "data-drag", allow=False, text="data agenda:cancel_meeting")
    seeded("arbiter", "operator-hands", allow=True, text="show agenda")
    out = flows.shadow(days=1)
    assert out["measured"] is True and out["n"] == 3
    assert out["would_have_stopped"] == 2, "the number the promotion gate is about"
    rules = {r["rule"]: r for r in out["by_rule"]}
    assert rules["data-drag"]["would_have_stopped"] == 2
    assert rules["operator-hands"]["would_have_stopped"] == 0, "an ALLOW is not a veto"


def test_a_window_with_nothing_in_it_SAYS_SO_instead_of_printing_a_reassuring_zero(seeded):
    """«The gate never fired» and «the gate never ran» look identical from a count and mean the opposite."""
    out = flows.shadow(days=1)
    assert out["n"] == 0 and out["would_have_stopped"] == 0
    assert out["measured"] is False, "a zero over nothing must not read as a clean bill of health"


def test_a_gate_shadow_row_counts_as_a_would_have_stopped_by_construction(seeded):
    """`gate_shadow` is only emitted when the click would have been held, so it carries no `allow` field."""
    seeded("gate_shadow", "post-form", text="un formulario que envía por POST")
    out = flows.shadow(kind="gate_shadow", days=1)
    assert out["n"] == 1 and out["would_have_stopped"] == 1


def test_the_kinds_can_be_narrowed_to_ONE_mechanism(seeded):
    seeded("arbiter", "data-drag", allow=False)
    seeded("gate_shadow", "post-form")
    assert flows.shadow(kind="arbiter", days=1)["n"] == 1
    assert flows.shadow(kind="gate_shadow", days=1)["n"] == 1
    assert flows.shadow(days=1)["n"] == 2, "with no kind it reads all three mechanisms"


def test_an_old_verdict_is_outside_the_window(seeded):
    seeded("arbiter", "data-drag", allow=False, ago_ms=9 * 86400 * 1000.0)
    assert flows.shadow(days=7)["n"] == 0
    assert flows.shadow(days=30)["n"] == 1


def test_an_unreadable_payload_is_counted_rather_than_crashing_the_report(seeded):
    """The reader is read-only over rows other people wrote: one broken row must not hide the other 199."""
    from bus import log as blog
    with blog._lock:
        conn = blog._connect()
        names = ", ".join(c[0] for c in blog._COLUMNS)
        marks = ", ".join("?" for _ in blog._COLUMNS)
        conn.execute(f"INSERT INTO events (ts_ms, topic, payload, {names}) VALUES (?, ?, ?, {marks})",
                     (time.time() * 1000.0, "observer", "{not json",
                      *blog._columns_from({"kind": "arbiter"})))
        conn.commit()
    out = flows.shadow(days=1)
    assert out["n"] == 1 and out["by_rule"][0]["rule"] == "—"


def test_the_route_is_mounted_and_behind_the_same_admission_as_its_neighbours():
    from observability import api
    paths = [r.path for r in api.router.routes]
    assert "/api/observability/shadow" in paths
    src = (__import__("pathlib").Path(api.__file__)).read_text(encoding="utf-8")
    body = src[src.index('@router.get("/api/observability/shadow")'):src.index('@router.get("/api/observability/stats")')]
    assert "_allowed(request)" in body, "an observability route without the admission check is a leak"
