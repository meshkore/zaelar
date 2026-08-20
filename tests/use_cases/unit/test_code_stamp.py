"""A score with no subject is not a measurement: every row says WHICH code produced it.

On 2026-08-20 the fixing agent had to ask, over the cluster, whether their 15:54 commit had actually run in the
16:26 round — and answering it meant reading sandbox boot timestamps by hand. That question comes back with
every fix. Worse: this suite boots `python -m server` from the WORKING TREE, so a round measured while somebody
is mid-edit measures a half-applied change and is indistinguishable from a round measured on a coherent tree.

So the stamp is the engine's short HEAD sha plus the non-test files that were dirty. `tests/` is excluded on
purpose: the harness editing itself does not change the engine under test, and counting it would make every
round dirty and the flag meaningless.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import config, initiative as I


def test_the_stamp_carries_the_sha_and_the_dirty_count():
    config._CODE_STAMP = None
    st = config.code_stamp()
    assert st.get("sha"), "no sha: a round could not be attributed to any code"
    assert 7 <= len(st["sha"]) <= 12, st["sha"]
    assert isinstance(st.get("n_dirty"), int) and isinstance(st.get("dirty"), list)


def test_the_harness_editing_ITSELF_does_not_count_as_dirty():
    """The whole point of the exclusion. If `tests/` counted, this very repo state would flag every round."""
    config._CODE_STAMP = None
    st = config.code_stamp()
    assert not [p for p in st["dirty"] if p.startswith("tests/")], st["dirty"]


def test_the_path_is_not_truncated(monkeypatch):
    """Regression on the first version: slicing a fixed 3 characters off porcelain ate the first letter of
    every path ("ests/…"), which silently broke the `tests/` exclusion — every round would have read dirty."""
    import subprocess
    out = " M widgets/navegador/tasks.py\n?? tests/use_cases/unit/test_x.py\nM  nucleo/loop.py\n"

    class _P:
        stdout = out

    def _run(argv, **kw):
        return _P() if "status" in argv else type("R", (), {"stdout": "abc1234"})()

    monkeypatch.setattr(subprocess, "run", _run)
    config._CODE_STAMP = None
    st = config.code_stamp()
    assert st["dirty"] == ["nucleo/loop.py", "widgets/navegador/tasks.py"], st["dirty"]
    assert st["n_dirty"] == 2
    config._CODE_STAMP = None


def test_a_broken_git_never_costs_the_round(monkeypatch):
    """Fail-soft is not a nicety: the stamp is bookkeeping, and losing an eight-minute conversation because
    `git` was unavailable would be a harness bug of exactly the kind this suite files against others."""
    import subprocess

    def _boom(*a, **kw):
        raise OSError("no git here")

    monkeypatch.setattr(subprocess, "run", _boom)
    config._CODE_STAMP = None
    st = config.code_stamp()
    assert st["sha"] == "" and st["dirty"] == []
    config._CODE_STAMP = None


def test_the_ROUND_says_it_when_the_tree_was_dirty():
    """It has to reach the agent who READS the round, not just the ledger row."""
    txt = _round_text()
    assert "abc1234" in txt
    assert "SIN COMMITEAR" in txt and "widgets/navegador/tasks.py" in txt


def test_and_stays_QUIET_on_a_clean_tree():
    txt = _round_text(code={"sha": "abc1234", "n_dirty": 0, "dirty": []})
    assert "abc1234" in txt, "the sha is said always — that is what answers 'did my commit run?'"
    assert "SIN COMMITEAR" not in txt


def _scn():
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p", opening_line="o",
                              success_checks="s")


def _round_text(code: dict | None = None) -> str:
    result = {"scenario": "x", "tier": 1, "channel": "probe",
              "code": code if code is not None else {"sha": "abc1234", "n_dirty": 1,
                                                     "dirty": ["widgets/navegador/tasks.py"]},
              "run": {"transcript": [], "mechanism_report": {}},
              "verdict": {"overall": 3, "veredicto": "x", "scores": {}}}
    return I._evidence(result, scenario=_scn(), sandboxed=True)


def test_the_stamp_is_taken_BEFORE_the_engine_boots(monkeypatch, tmp_path):
    """A lazy stamp lies, and it lied about itself.

    2026-08-20: the sandbox booted at 19:37:07, the fixing agent committed at 19:39:41, and the stamp — first
    taken when the round finished — named a commit the running server had never loaded. I was one message away
    from telling them their fix had been measured. The server reads the tree at `Popen`, so the stamp belongs on
    the same side of the boot as the server.
    """
    import argparse
    from tests.use_cases.e2e.agent import run as R

    order: list[str] = []
    config._CODE_STAMP = None
    config._MACHINE_STAMP = None
    monkeypatch.setattr(config, "code_stamp", lambda: order.append("stamp") or {"sha": "abc1234"})
    monkeypatch.setattr(config, "machine_stamp", lambda: {"n": 0})

    import contextlib

    @contextlib.contextmanager
    def _fake_engine(**kw):
        order.append("boot")
        yield type("E", (), {"base_url": "http://x", "workspace": tmp_path,
                             "new_widget_dirs": lambda self=None: [],
                             "log_tail": lambda self=None, n=0: ""})()

    import tests.platform.sandbox_engine as SE
    monkeypatch.setattr(SE, "sandbox_engine", _fake_engine)
    monkeypatch.setattr(SE, "preferred_port", lambda p: p)
    monkeypatch.setattr(R, "_run_batch", lambda *a, **k: order.append("run") or 0)

    R._sandbox_batch([_scn()], argparse.Namespace(no_file=True, stop_after_failures=0))
    assert order[0] == "stamp", f"el sello se tomó después de arrancar: {order}"
    assert order.index("stamp") < order.index("boot")
    config._CODE_STAMP = None
    config._MACHINE_STAMP = None
