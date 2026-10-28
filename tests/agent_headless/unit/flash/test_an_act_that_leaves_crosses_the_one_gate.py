"""An act that LEAVES crosses the one data-op gate, measured on the gate itself (refactor2710-06 T-02).

Behaviour, through `tests/widget_data_rig.py` — the gate runs whole and stops where an op starts or is held:

  · with a stranger's words in the context and no sure verdict, a reply is ASKED; without them it runs (CRIT-E12);
  · two readers disagree on an act that leaves → the verdict's act runs instead (full12 E3, node 2.106);
  · a sure ordered forward the model only drafted → the forward runs, to the person he named (live bench E3, 2.729);
  · a send to someone his words never named is asked, never sent (the operator, 2026-10-15).
"""
from __future__ import annotations

import pytest

from nucleo import his_words, untrusted as U
from tests import widget_data_rig as rig


@pytest.fixture(autouse=True)
def _scene(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Quinn", "email": "quinn@example.com"})
    import server.voice_api as _va
    monkeypatch.setattr(_va, "open_instances", lambda: ["mensajeria"])
    U.reset()
    his_words.reset()          # his recent words are the conversation's: a test brings its own
    yield
    U.reset()
    his_words.reset()


def test_a_reply_runs_and_with_a_strangers_words_in_context_it_is_asked(monkeypatch):
    out = rig.run("mensajeria", "reply", {"n": 1, "text": "ok, thanks"}, said="reply ok thanks", monkeypatch=monkeypatch)
    assert [a for _w, a, _p in out.ran] == ["reply"] and not out.asked, out
    U.seen()
    out = rig.run("mensajeria", "reply", {"n": 1, "text": "ok, thanks"}, said="reply ok thanks", monkeypatch=monkeypatch)
    assert not out.ran and [a for _w, a, _p in out.asked] == ["reply"], out


def test_when_the_readers_disagree_on_an_act_that_leaves_the_verdict_runs(monkeypatch):
    out = rig.run("mensajeria", "reply", {"n": 1, "text": "I'll send the meet link"},
                  said="draft a short reply saying I'll send the meet link",
                  turn_brief=rig.brief("mensajeria:draft", 1.0), monkeypatch=monkeypatch)
    assert [a for _w, a, _p in out.ran] == ["draft"] and out.ran[0][2].get("text"), out


def test_a_sure_ordered_forward_the_model_only_drafted_runs_to_whom_he_named(monkeypatch):
    out = rig.run("mensajeria", "draft", {"text": "We're already trying Inworld — please book it."},
                  said="send the invoice to quinn, tell him we're already trying inworld and he should book it",
                  turn_brief=rig.brief("mensajeria:forward", 0.79), monkeypatch=monkeypatch)
    assert [a for _w, a, _p in out.ran] == ["forward"] and out.ran[0][2].get("contact"), out


def test_a_send_to_someone_his_words_never_named_is_asked(monkeypatch):
    out = rig.run("mensajeria", "send_to", {"contact": "Quinn", "text": "the numbers"},
                  said="send the numbers to the team", monkeypatch=monkeypatch)
    assert not out.ran and [a for _w, a, _p in out.asked] == ["send_to"], out
