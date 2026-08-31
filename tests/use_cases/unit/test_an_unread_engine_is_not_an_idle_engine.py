"""A ground-truth read that FAILED must never be reported as an engine that did nothing (V2-396).

MEASURED, not deduced. With `config.ZAELAR_URL` pointed at a closed port — the engine as unreachable as it
can possibly be — the mechanism report came back:

    families_observed : []
    missing_signals   : ['Brain Workers', 'Widgets']
    n_events          : 0
    widget_ops        : {}
    widgets_producing : []

which is character for character the report of a product that ran and accomplished nothing. Every reader in
`probe_client` swallowed its own failure into an empty collection, so the harness had no way to tell "I
asked and the answer was nothing" from "I never got an answer". The judge is handed the first sentence and
scores 1/5 against the product.

This is the READ half of what `harness_report_error` (V2-381) fixed on the COMPOSE half: there, the block
that builds the report crashed and the field was named as if the worker had failed. Here nothing crashes at
all — which is worse, because the report looks healthy.

It also punches a hole straight through V2-395, shipped an hour earlier: that fix taught the judge that
`widgets_producing == []` means "nothing was playing" and `None` means "could not ask". With the engine
unreachable the reader returned `[]`, so the careful three-way distinction resolved to the one branch that
accuses the product.
"""
from pathlib import Path

from tests.use_cases.e2e.agent import config, judge as J, probe_client as P, verify as V

DEAD = "http://127.0.0.1:1"          # nothing listens here: every read fails, none raises


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


class _Dead:
    """Point the client at a closed port for the duration of one test."""

    def __enter__(self):
        self._prev = config.ZAELAR_URL
        config.ZAELAR_URL = DEAD
        P.clear_read_failures()
        return self

    def __exit__(self, *a):
        config.ZAELAR_URL = self._prev
        P.clear_read_failures()
        return False


# ── the ledger: a failed read leaves a trace ───────────────────────────────────────────────────────────────

def test_a_failed_read_is_recorded_instead_of_vanishing():
    with _Dead():
        P.current_session_id()
        fails = P.read_failures()
    assert fails, "the read failed and left nothing behind — that is the whole defect"
    assert any("/api/observability/identity" in f.get("path", "") for f in fails)
    assert fails[0].get("reason"), "a failure with no reason cannot be diagnosed"


def test_a_healthy_read_records_nothing():
    """Sensitivity: a ledger that fills up on success stops being a signal."""
    P.clear_read_failures()
    assert P.read_failures() == []


# ── the three-way distinction survives an unreachable engine ───────────────────────────────────────────────

def test_widgets_producing_says_I_COULD_NOT_ASK():
    """V2-395 gave the judge three states. This is the one that was unreachable in practice."""
    with _Dead():
        assert P.widgets_producing() is None, "an unreadable engine must not answer «nothing was playing»"


def test_the_session_id_is_None_when_nobody_answered():
    """`""` is a legitimate answer (the engine has no live session); "I could not ask" is not."""
    with _Dead():
        assert P.current_session_id() is None


def test_events_are_None_when_nobody_answered():
    with _Dead():
        assert P.session_events("s-1") is None


# ── the report says so ─────────────────────────────────────────────────────────────────────────────────────

def test_the_report_names_what_it_could_not_read():
    with _Dead():
        mech = V.mechanism_report([], ["Brain Workers", "Widgets"])
    assert mech.get("ground_truth_unreadable"), "the report claims 0 events without saying it never asked"
    paths = " ".join(f.get("path", "") for f in mech["ground_truth_unreadable"])
    assert "/widgets/producing" in paths


def test_a_healthy_report_carries_no_such_field(monkeypatch):
    """Sensitivity: if the field appeared ALWAYS, it would cease to mean anything.

    The reads are replaced with one that ANSWERS. Previously this reached the real network against
    `config.ZAELAR_URL`, so its verdict depended on an engine being available — and in the full map run there
    is none: it failed with `URLError: nodename nor servname provided`, while passing in isolation.
    A unit test that needs a live artifact does not measure what it claims to measure; it measures the
    environment."""
    monkeypatch.setattr(P, "_get", lambda path, timeout=15.0: {})
    P.clear_read_failures()
    mech = V.mechanism_report([], [])
    assert not mech.get("ground_truth_unreadable")


# ── the round does not get a score ─────────────────────────────────────────────────────────────────────────
# The sentence is asserted, never the presence of the call: the first version of the no-quota rule survived
# being mutated to `if False and ...` because its guard only grepped for a substring (2026-08-24).

def test_an_unreadable_trunk_is_INFRA():
    frase = V.unreadable_infra({"ground_truth_unreadable": [{"path": "/api/observability/events",
                                                             "reason": "ConnectionRefusedError"}]})
    assert frase and "no mide al producto" in frase
    assert "/api/observability/events" in frase


def test_a_read_that_worked_is_not_INFRA():
    assert V.unreadable_infra({}) == ""
    assert V.unreadable_infra({"ground_truth_unreadable": []}) == ""


def test_only_the_GROUND_TRUTH_reads_void_the_round():
    """A widget box nobody asked about failing is a hole in one field, not a round that measured nothing.
    Voiding every round on any failed read would turn INFRA into noise and hide real defects behind it."""
    assert V.unreadable_infra({"ground_truth_unreadable": [{"path": "/widgets/agenda/data",
                                                            "reason": "timeout"}]}) == ""


def test_run_py_actually_voids_the_round():
    """The rule has to be WIRED, not merely available — `no_quota_infra` earned that lesson.

    Read with the AST and not with `in src`: the first draft of this guard passed while the round was
    mutated to `crashed = ""`, because the words `unreadable_infra` survived in the comment right above it.
    That is the same failure the rule it mirrors was written to avoid, committed by the guard against it.
    """
    import ast
    tree = ast.parse(Path("tests/use_cases/e2e/agent/run.py").read_text())
    asignada = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "crashed" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "attr", getattr(n.value.func, "id", "")) == "unreadable_infra"
    ]
    assert asignada, "nobody assigns the round's INFRA sentence from `unreadable_infra`"


# ── the judge is told in words ─────────────────────────────────────────────────────────────────────────────

def test_the_judge_reads_it_as_the_instrument_breaking():
    txt = _texto(J.mechanism_facts({"ground_truth_unreadable": [
        {"path": "/api/observability/events", "reason": "ConnectionRefusedError"}]}))
    assert "NO se pudo LEER" in txt
    assert "NO se puntúa" in txt
    assert "/api/observability/events" in txt


def test_the_judge_says_nothing_about_a_healthy_report():
    assert "NO se pudo LEER" not in _texto(J.mechanism_facts({"results_sheet": {"n_named": 3}}))
