"""A row the order owes carries the data the order gave it, and a bare row does not attest (T-19 R2).

Demo sandbox at build 86, INIT: «Save <a> and <b>… <b>'s email is …» made ONE create, and a row only NAMED <b> read
«met». The class: a clause names the row (`where`) and carries what the order stated for it (`with`); the verifier
reads it. The write harness that re-ran the model after the turn to add the missing row (`compose.check`) went in
V2-851 F5 with every model re-run after the main stream; what stays is the verifier's reading of an end state.
"""
import pytest

from nucleo.circuit import spec as _spec
from nucleo.circuit import verify as _verify
from widgets import rows


def _contacts_goal():
    return {"all": [
        {"widget": "contactos", "collection": "contacts", "where": {"title~": "Quinn"}, "expect": "present"},
        {"widget": "contactos", "collection": "contacts", "where": {"title~": "Rowan"},
         "with": {"email": "rowan@example.com"}, "expect": "present"}]}


def test_a_row_that_only_carries_the_name_is_not_the_row_the_order_asked_for(monkeypatch):
    goal = _contacts_goal()
    monkeypatch.setattr(rows, "_rows", lambda w, c: [{"name": "Quinn"}, {"name": "Rowan", "kind": "person"}])
    assert _verify.check(goal) is False
    assert "rowan@example.com" in _verify.missing(goal)[0]
    # the card may file the address anywhere — a list of details, a channel row: the data is what is owed
    monkeypatch.setattr(rows, "_rows", lambda w, c: [
        {"name": "Quinn"}, {"name": "Rowan", "channels": [{"platform": "email", "handle": "Rowan@Example.com"}]}])
    assert _verify.check(goal) is True


def test_the_inferrer_is_shown_the_fields_each_collection_creates_with():
    assert "email" in _spec.create_fields("contactos", "contacts")
    assert "list" in _spec.create_fields("agenda", "tasks")
    assert _spec.create_fields("agenda", "occurrences") == []


def test_nothing_reruns_the_model_after_a_turn_that_wrote():
    """The disarm of V2-851 F5: the post-stream chain scheduled `compose.after_turn` → `spec.infer` → a repair model
    call after every turn that wrote."""
    from nucleo.circuit import compose
    src = open("nucleo/flash/post_stream.py", encoding="utf-8").read()
    assert "after_turn" not in src
    assert not any(hasattr(compose, n) for n in ("after_turn", "check", "_missing_calls", "grounded"))
