"""V2-705 · a payload key spelled with a SYNONYM must not look like a missing field.

Measured 2026-09-15 20:32, driving the Thursday meeting workflow by hand. The order was clear and the
routing was right; the model called `mensajeria.send_to` with

    {"contact": "Kryptonite", "message": "Let's start fresh… could we meet Thursday at 5pm?", "objective": …}

and the manifest declares `text`, not `message`. The door refused «no me ha llegado el mensaje», the turn
ended, and a message the operator had just dictated never left — over a payload that was carrying it.

`resolve_target` already tolerated two of these by hand (`to` for `contact`, `platform` for `channel`), and
that is the tell: the tolerance was being written one door at a time, so every door that had not yet paid
for its own incident still lost the call. `contract.fold_aliases` moves it to the SINGLE funnel
(`server_api._dispatch`), before the destructive guard, for every widget and every caller at once.

These cases pin the four refusals that keep it from guessing: it never invents a field, never overwrites the
model's own word, never folds onto an action that gives the synonym its own meaning, and never raises.
"""
from __future__ import annotations

import pytest

from widgets import contract


# ── the measured failure ────────────────────────────────────────────────────────────────────────────────

def test_the_message_spelled_message_reaches_the_field_called_text():
    out = contract.fold_aliases("mensajeria", "send_to",
                                {"contact": "Kryptonite", "message": "hola", "objective": "quedar"})
    assert out["text"] == "hola"
    assert out["contact"] == "Kryptonite" and out["objective"] == "quedar"


@pytest.mark.parametrize("alt", ["message", "msg", "body", "content", "mensaje", "texto"])
def test_every_spelling_of_the_message_lands_on_text(alt):
    assert contract.fold_aliases("mensajeria", "send_to", {"contact": "X", alt: "hola"})["text"] == "hola"


def test_the_fold_runs_BEFORE_the_destructive_guard():
    """A cancellation that names its target as `name` instead of `title` is a NAMED cancellation, not an
    empty selector — the guard must judge the call the operator actually made."""
    payload = contract.fold_aliases("agenda", "cancel_meeting", {"name": "Dentista"})
    assert payload["title"] == "Dentista"
    assert contract.guard("agenda", "cancel_meeting", payload) is None


def test_an_empty_cancellation_is_still_refused():
    """The fold widens nothing: with no target under ANY spelling, the V2-705 refusal stands."""
    payload = contract.fold_aliases("agenda", "cancel_meeting", {})
    assert contract.guard("agenda", "cancel_meeting", payload)["error"] == contract.SELECTOR_MISSING


# ── the four refusals to guess ──────────────────────────────────────────────────────────────────────────

def test_the_models_own_word_wins_over_any_synonym():
    out = contract.fold_aliases("mensajeria", "send_to",
                                {"contact": "X", "text": "el bueno", "message": "el otro"})
    assert out["text"] == "el bueno"


def test_a_field_the_manifest_does_not_declare_is_never_invented():
    """`send_to` declares no `title`, so a stray `name` stays a stray key — the manifest is the contract."""
    out = contract.fold_aliases("mensajeria", "send_to", {"contact": "X", "text": "hi", "name": "Ana"})
    assert "title" not in out


def test_an_action_that_declares_BOTH_keys_folds_nothing(monkeypatch):
    """When an action gives the synonym its own meaning, the two words are two fields and nothing moves."""
    monkeypatch.setattr(contract, "_spec",
                        lambda w, a: {"payload": {"text": "string", "message": "string"}})
    out = contract.fold_aliases("w", "a", {"message": "hola"})
    assert "text" not in out and out["message"] == "hola"


def test_an_empty_or_blank_synonym_is_not_a_value():
    assert "text" not in contract.fold_aliases("mensajeria", "send_to", {"contact": "X", "message": "   "})
    assert "text" not in contract.fold_aliases("mensajeria", "send_to", {"contact": "X", "message": None})


def test_a_call_with_nothing_to_fold_is_returned_UNTOUCHED():
    """The overwhelming majority of calls: the door must not pay a rebuild for them."""
    pl = {"contact": "X", "text": "hi"}
    assert contract.fold_aliases("mensajeria", "send_to", pl) is pl
    unknown = {"whatever": 1}
    assert contract.fold_aliases("nosuchwidget", "nosuchaction", unknown) is unknown


@pytest.mark.parametrize("bad", [None, "not a dict", 42, []])
def test_garbage_never_raises(bad):
    assert isinstance(contract.fold_aliases("mensajeria", "send_to", bad), dict)
    assert isinstance(contract.fold_aliases(None, None, {"a": 1}), dict)


# ── the wiring: the single funnel, not one door at a time ───────────────────────────────────────────────

def test_the_single_funnel_folds_before_it_judges():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets/server_api.py").read_text(encoding="utf-8")
    body = src[src.index("async def _dispatch("):src.index("@router.post(\"/widgets/{wid}/action\")")]
    # The CALL, never the prose: the comment above it also says «fold_aliases», and matching that is how
    # the first disarm of this file came back green while the fold ran AFTER the guard.
    assert "contract.fold_aliases(" in body, "the fold must live at the funnel every caller passes through"
    assert body.index("contract.fold_aliases(") < body.index("contract.guard("), (
        "a synonym must not be judged as a missing field")
