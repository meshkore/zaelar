"""A capability no card declares is answered «not yet», never a worker (V2-807 T-16).

Live run: he asked the mail card to mirror his provider in real time. No card and no connector declares that; the
model promised it, a backstop escalated, and a Brain Worker spent seven minutes switching the mail card's folders and
reading another card's files. Three mechanisms, one test each, and the variants here are other domains on purpose
(a calendar sync, a music crossfade) so nothing is tailored to the mail card:

  · the errand PORTAL refuses a turn-born errand whose turn's verdict says the capability is missing;
  · a widget DECLARES which actions are the operator's own controls, and a worker is refused them;
  · the end-state deriver never takes the assistant's name (how he addressed us) as the thing to look for.
"""
from __future__ import annotations

import json
import os
import threading

import pytest

from nucleo.flash import capability_gap as G
from nucleo.acts import errand as E


def _brief(choice: str, conf: float) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {G.KEY: {"choice": choice, "confidence": conf}}}


@pytest.fixture
def portal(monkeypatch):
    """The portal with its bus and its refusal captured; nothing reaches a dispatcher or a speaker."""
    bus, refused = [], []
    monkeypatch.setattr(E, "_emit_bus", lambda topic, payload: bus.append(topic))
    monkeypatch.setattr(G, "refuse", lambda req: refused.append(req))
    G._BY_TRACE.clear()
    yield bus, refused
    G._BY_TRACE.clear()


REQ = "Make my calendar sync with my work Outlook calendar from now on, both ways."


def test_a_sure_missing_verdict_refuses_the_turn_born_errand(portal):
    bus, refused = portal
    G.remember(_brief(G.MISSING, 0.95), "T7·ab")
    for src in G.TURN_SOURCES:
        tid = E.escalate_to_slowbrain(REQ, context={"src": src, "trace": "T7·ab"})
        assert tid == 0, f"an errand for a capability no card declares was started from {src}"
    assert "escalate.requested" not in bus
    assert refused == [REQ, REQ], "the refusal must be SAID, not swallowed"


@pytest.mark.parametrize("choice,conf", [(G.WORK, 0.95), (G.DECLARED, 0.9), (G.MISSING, 0.55)])
def test_work_a_declared_act_or_an_unsure_verdict_keep_todays_path(portal, choice, conf):
    bus, refused = portal
    G.remember(_brief(choice, conf), "T8·cd")
    assert E.escalate_to_slowbrain(REQ, context={"src": "voice", "trace": "T8·cd"}) > 0
    assert "escalate.requested" in bus and not refused


def test_only_this_turns_verdict_and_only_turn_born_errands_are_judged(portal):
    bus, refused = portal
    G.remember(_brief(G.MISSING, 0.99), "T9·ef")
    # another turn's errand, and errands that continue work which already passed the door
    assert E.escalate_to_slowbrain(REQ, context={"src": "voice", "trace": "T10·gh"}) > 0
    assert E.escalate_to_slowbrain(REQ, context={"src": "context_handoff", "trace": "T9·ef"}) > 0
    assert E.escalate_to_slowbrain(REQ, context={"src": "voice", "trace": "T9·ef", "confirmed": True}) > 0
    assert not refused


def test_the_question_is_asked_over_what_the_cards_declare():
    from nucleo.flash import frontend as fe
    from nucleo.flash import turn_brief as tb
    q = G.question(["agenda"])
    assert q and set(q["criteria"]) == {G.MISSING, G.DECLARED, G.WORK}
    declared = list(fe.declared_actions("agenda"))
    assert declared and all(name in q["instructions"] for name in declared[:5]), \
        "the verdict must be over the card's DECLARED actions, not over words"
    assert G.KEY in tb.build("Can the music player crossfade between songs from now on?", open_ids=["musica"])


def test_the_not_yet_line_exists_in_both_shipped_languages():
    root = os.path.join(os.path.dirname(E.__file__), "..", "..", "i18n", "genesis")
    for lang in ("en", "es"):
        data = json.load(open(os.path.join(root, lang, "voice.json"), encoding="utf-8"))
        assert data.get("capability_not_yet") and data.get("capability_not_yet_noted"), lang


# ── a worker never runs the operator's own controls of a card ───────────────────────────────────────────────────

def test_a_declared_operator_control_is_refused_to_a_worker():
    from nucleo.cli import worker_policy as WP
    from widgets import runtime
    flagged = [(w["id"], a) for w in runtime.catalog() for a, s in (w.get("actions") or {}).items()
               if isinstance(s, dict) and s.get("worker") is False]
    assert flagged, "no widget declares an operator-only action: the guard below would test nothing"
    for wid, act in flagged:
        p = {"widget_id": wid, "action": act, "payload": {}}
        assert WP.classify_act("widget_data", p) == WP.DENY, f"{wid}:{act}"
        assert "operator's own controls" in WP.deny_reason("widget_data", p)


def test_an_undeclared_flag_keeps_todays_path():
    from nucleo.cli import worker_policy as WP
    from nucleo.flash import frontend as fe
    acts = fe.declared_actions("agenda")
    name = next(a for a, s in acts.items() if isinstance(s, dict) and "worker" not in s)
    assert not WP.operator_only({"widget_id": "agenda", "action": name})


# ── the assistant's name is never the goal ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def named(monkeypatch):
    from nucleo.flash import presence
    monkeypatch.setattr(presence, "assistant_names", lambda: ("marlowe",))


def test_a_term_that_is_only_the_assistants_name_leaves_the_spec(named):
    from nucleo.circuit import spec as S
    only_name = {"all": [{"widget": "musica", "collection": "tracks", "where": {"title~": "Marlowe"},
                          "expect": "present"}]}
    assert S._without_the_assistants_name(only_name) is None
    assert S.parse(json.dumps(only_name)) is None, "the inferred spec must not ask for a row named after us"
    mixed = {"all": [{"widget": "musica", "collection": "tracks", "where": {"title~": "Marlowe", "artist": "Nina"}},
                     {"widget": "musica", "field": "now", "has": "MARLOWE"}]}
    got = S._without_the_assistants_name(mixed)
    assert got == {"all": [{"widget": "musica", "collection": "tracks", "where": {"artist": "Nina"}}]}
    assert "marlowe" in S._infer_messages("Marlowe, put on some jazz")[0]["content"], \
        "the deriver is told the assistant's name, so it can leave the vocative out"
