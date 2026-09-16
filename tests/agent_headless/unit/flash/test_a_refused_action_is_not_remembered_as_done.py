"""V2-707 F0 · A mutation the door REFUSED is never remembered as executed, so its corrected retry runs.

## The measured incident

2026-09-16, session `cb0ac5da`. «I want you to delete that meeting. And cancel that appointment. And notify
the other person.»

| i | what happened |
|---|---|
| 7908 | `agenda.cancel_meeting` with `payload: {}`, mode `fast` |
| 7911 | REFUSED by the V2-705 contract — `selector_missing`, and the menu read «¡Feliz cumpleaños! (cita 2027-08-19)…» |
| 7917 | the same sentence tripped `danger.is_dangerous` → the worker was PARKED before starting |
| 8021 | the model, asked again, answered correctly: «The meeting at 5:00 PM today is Dentist. But I can see a meeting tomorrow too — Meeting with Cryptonite» |
| 8064 | «Not today. Tomorrow.» → `cancel_meeting` re-emitted → **discarded as context-bleed** |
| 8065 | the turn went mute and composed a closing |
| 8067 | «Got it — cancelling Meeting with Cryptonite tomorrow at 5:00 PM. I'll notify the other person as well.» |

The meeting is still in the agenda. Five minutes for one row and one message.

## Why the guard could not be right

`brain._last_dataop` was stamped one line BEFORE dispatch and never looked at the result, so a refusal
entered the ledger of things that happened. And for this class it was not a coincidence but an identity: the
guard's escape hatch is `_word_overlap(payload values, what he said) > 0`, and an EMPTY payload joins no
values — so the overlap is 0 against every sentence in every language, and the hatch can never open. A
refusal that says «call me again naming one» and a guard that eats the second call leave no legal move.

The fix is subtraction: the seal follows the RESULT (`dispatch_and_report(..., seal=...)`), which is the only
place that can know. The guard keeps its original job untouched — the V2-038 case it was built for («borra el
reloj» dragging the dentist's `add_meeting`) is a mutation that SUCCEEDED, so it is still sealed and still
caught.

Run: .venv/bin/pytest tests/agent_headless/unit/flash/test_a_refused_action_is_not_remembered_as_done.py
"""
from __future__ import annotations

import asyncio
import pathlib

import pytest

from nucleo.flash import data_ops

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PROVIDER = ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py"

REFUSAL = {"ok": False, "error": "selector_missing", "field": "title",
           "message": "I couldn't tell which one to remove, so I left everything as it is. Which of these?"}


@pytest.fixture
def mute(monkeypatch):
    """`report_failure` speaks and pushes notes; here we only care about the seal."""
    monkeypatch.setattr(data_ops, "report_failure", _noop)
    return None


async def _noop(*_a, **_k):
    return False


def _run(res, *, seal):
    """Drive one dispatch whose funnel answers `res`, and return what the seal was told."""
    import widgets
    seen: list = []

    async def _fake_dispatch_tag(_tag, _payload):
        return res

    orig = widgets.dispatch_tag
    widgets.dispatch_tag = _fake_dispatch_tag
    try:
        asyncio.run(data_ops.dispatch_and_report("agenda", "cancel_meeting", {}, seal=seal))
    finally:
        widgets.dispatch_tag = orig
    return seen


# ── the mechanism: the seal follows the result ──────────────────────────────────────────────────────────

def test_a_refused_op_is_never_sealed_as_done(mute):
    told: list = []
    _run(REFUSAL, seal=told.append)
    assert told == [False], "a refusal must be reported to the seal as «it did not happen»"


def test_an_op_that_ran_IS_sealed(mute):
    told: list = []
    _run({"ok": True, "meetings": []}, seal=told.append)
    assert told == [True], "the anti-drag guard still needs to remember real mutations"


def test_a_widget_that_answers_without_an_ok_key_counts_as_done(mute):
    """Most `apply_action`s answer with the view, not with `ok`. Only an explicit `ok: False` is a refusal —
    reading a missing key as failure would silently retire the guard for almost every widget."""
    told: list = []
    _run({"meetings": [], "tasks": []}, seal=told.append)
    assert told == [True]


def test_the_seal_never_breaks_the_dispatch(mute):
    """It runs in a detached task: a seal that raises must not take the op's reporting down with it."""
    def _boom(_ok):
        raise RuntimeError("boom")
    _run(REFUSAL, seal=_boom)          # must not raise


def test_no_seal_is_a_valid_call(mute):
    """The worker bridge dispatches through its own path and passes none."""
    _run(REFUSAL, seal=None)


# ── the retry instruction and the retry guard must agree ────────────────────────────────────────────────

def test_the_refusal_tells_the_model_the_corrected_call_will_RUN(monkeypatch):
    """`contract.guard` hands back a menu precisely so the next turn can name one. Until F0 nothing said
    that re-calling was the expected move, while the anti-drag guard was eating it."""
    notes: list = []
    from voice import brain_notes
    monkeypatch.setattr(brain_notes, "push", notes.append)

    async def _no_voice(*_a, **_k):
        return None
    from voice import proactive
    monkeypatch.setattr(proactive, "notify", _no_voice)
    monkeypatch.setattr(data_ops, "_dedup", lambda *_a, **_k: False)

    asyncio.run(data_ops.report_failure("agenda", "cancel_meeting", REFUSAL))
    assert notes, "a refusal must reach the model"
    note = notes[0]
    assert "vuelve a llamar" in note.lower(), note
    assert "no es una repeticion" in _fold(note), (
        "the note must say the corrected call is not a repetition — otherwise it contradicts the guard")


def _fold(s: str) -> str:
    import unicodedata
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


# ── structural: nothing may stamp the seal before the result ────────────────────────────────────────────

def _fast_branch() -> str:
    src = PROVIDER.read_text(encoding="utf-8")
    start = src.index("if mode == _wactions.FAST:")
    return src[start:src.index("elif mode == _wactions.CONFIRM:", start)]


def test_the_seal_is_written_only_inside_the_result_callback():
    """THE DISARM TARGET. Moving `brain._last_dataop = …` back above the dispatch is exactly the defect of
    2026-09-16, and it is one line, so it has to be pinned where it can be seen."""
    branch = _fast_branch()
    writes = [ln.strip() for ln in branch.splitlines() if "brain._last_dataop =" in ln]
    assert len(writes) == 1, f"expected ONE write of the seal in the FAST branch, found {writes}"
    assert branch.index("def _seal(") < branch.index("brain._last_dataop ="), (
        "the seal must be written inside the callback that sees the result, never before dispatching")
    assert "seal=_seal" in branch, "and the callback has to actually reach `dispatch_and_report`"


def test_the_guard_says_what_it_threw_away():
    """The sibling guards in `_handle_widget_data_tool` carry the discarded payload in the event; this one
    logged only «agenda:cancel_meeting», so the live incident could not be diagnosed from the timeline."""
    branch = _fast_branch()
    head = branch.index("data-op del turno anterior re-emitida")
    tail = branch.index("deduped[\"v\"] = True", head)
    emitted = branch[head:tail]
    assert "\"payload\"" in emitted and "\"action\"" in emitted, (
        "a guard that discards an action must record WHICH action and with what payload")
