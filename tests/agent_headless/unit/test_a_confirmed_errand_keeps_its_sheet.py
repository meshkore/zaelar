#
# test_a_confirmed_errand_keeps_its_sheet.py — V2-508.
#
# The gate parks an irreversible errand and POPS its record, but `run_listener` had already opened its result
# sheet on the operator's screen — on purpose, so nobody stares at a blank canvas while the errand runs. The
# «sí» then relaunched the same request through the normal door with no sheet in its context, so it minted a
# SECOND box and left the first one empty for good.
#
# Measured 2026-08-30, `cheapest-monitor__us` round 20260830-114302: `results::101c0f-1` opened at 11:34:03
# and never written to; `results::101c0f-2` opened 19 s later and took all 200+ writes. The same defect also
# blinded the dedup — with the first record popped there was nothing LIVE to match against, so the relaunch
# read `live: 0` (V2-507's row) and could not be recognised as the same errand.
#
# The machinery to inherit already existed and is the SAME case: `sheets._sheet_open` inherits a predecessor's
# sheet for the provider relay (V2-238) and the context handoff (V2-117). A confirmed errand is the third
# continuation — same request, relaunched on purpose, with the operator already looking at its box.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/test_a_confirmed_errand_keeps_its_sheet.py
#
import pytest

from nucleo import dispatch, sheets


class _Task:
    def __init__(self, kind="web", trusted=True, context=None):
        self.kind, self.trusted, self.context = kind, trusted, dict(context or {})


@pytest.fixture(autouse=True)
def _clean():
    dispatch._PENDING_CONFIRM.clear()
    yield
    dispatch._PENDING_CONFIRM.clear()


_REQ = "Research the best value desktop monitors available for purchase in San Francisco"


def test_the_parked_errand_remembers_the_sheet_already_on_screen():
    dispatch.remember_confirm("1", _REQ, _Task(), sheet="boot99-1")
    assert dispatch.pending_confirm()["sheet"] == "boot99-1"


def test_the_yes_carries_that_sheet_back_through_the_normal_door(monkeypatch):
    """The «sí» relaunches by the SAME door as any escalation — the only thing that changes is what it
    carries. `sheet` has to be in there or `_sheet_open` mints a fresh box beside the abandoned one."""
    seen: list = []
    from nucleo.flash import escalate
    monkeypatch.setattr(escalate, "escalate_to_slowbrain",
                        lambda request, context=None, **k: seen.append((request, dict(context or {}))))
    dispatch.remember_confirm("1", _REQ, _Task(), sheet="boot99-1")
    dispatch.resolve_confirm(True)
    assert seen, "a yes must relaunch the errand"
    request, ctx = seen[0]
    assert request == _REQ
    assert ctx["confirmed"] is True
    assert ctx["sheet"] == "boot99-1", "the confirmed errand must come back to the box already on screen"


def test_a_no_relaunches_nothing(monkeypatch):
    """The other direction: dropping the errand must not resurrect it just because it now carries a sheet."""
    seen: list = []
    from nucleo.flash import escalate
    monkeypatch.setattr(escalate, "escalate_to_slowbrain",
                        lambda request, context=None, **k: seen.append(request))
    dispatch.remember_confirm("1", _REQ, _Task(), sheet="boot99-1")
    assert dispatch.resolve_confirm(False)["ok"] is False
    assert seen == []


def test_an_errand_with_no_sheet_carries_none(monkeypatch):
    """Not every errand opens a sheet (`surfaces` decides). An empty one must not travel as a real id, or the
    relaunch would inherit a box that does not exist and stop opening its own."""
    seen: list = []
    from nucleo.flash import escalate
    monkeypatch.setattr(escalate, "escalate_to_slowbrain",
                        lambda request, context=None, **k: seen.append(dict(context or {})))
    dispatch.remember_confirm("1", "cancela mi suscripción a Netflix", _Task())
    dispatch.resolve_confirm(True)
    assert "sheet" not in seen[0]


# ── and the half that makes the inheritance actually happen ──────────────────────────────────────────────

class _Rec:
    def __init__(self, task_id, sheet="", goal="g"):
        self.task_id, self.sheet, self.goal = task_id, sheet, goal


def test_the_inherited_sheet_is_not_started_fresh(monkeypatch):
    """`fresh=True` REPLACES the items, so starting an inherited sheet would wipe it. The parked sheet is
    empty today, but the rule is the predecessor's and must not be re-decided here."""
    calls: list = []
    import widgets.results.data as _sheet
    monkeypatch.setattr(_sheet, "begin_task", lambda goal, fresh=True, sheet="": calls.append((sheet, fresh)))
    monkeypatch.setattr(_sheet, "prune_sheets", lambda: None)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)

    sheets._sheet_open(_Rec("2", sheet="boot99-1"))          # arrives with its predecessor's sheet
    assert calls and calls[0][0] == "boot99-1", "must write into the box already on screen"
    assert calls[0][1] is False, "an inherited sheet must NOT be started fresh"


def test_its_own_sheet_is_still_started_fresh(monkeypatch):
    """The direction that keeps V2-259 alive: an errand arriving with ITS OWN sealed sheet is not a
    continuation, and reading «has a sheet ⇒ inherited» is the bug that turned a V2-259 test red once."""
    calls: list = []
    import widgets.results.data as _sheet
    monkeypatch.setattr(_sheet, "begin_task", lambda goal, fresh=True, sheet="": calls.append((sheet, fresh)))
    monkeypatch.setattr(_sheet, "prune_sheets", lambda: None)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)

    mine = sheets.sheet_id_for("7")
    sheets._sheet_open(_Rec("7", sheet=mine))
    assert calls and calls[0] == (mine, True)


def test_the_gate_hands_the_sheet_over(monkeypatch):
    """The wiring guard: every assertion above passes with `sheet=sheet_of(rec)` DELETED from the gate."""
    import inspect
    src = "\n".join(l for l in inspect.getsource(dispatch._run_session).splitlines()
                    if not l.strip().startswith("#"))
    assert "remember_confirm(key, req, task, sheet=" in src, (
        "the gate is the only place that still knows the sheet — the record is popped one line later")
