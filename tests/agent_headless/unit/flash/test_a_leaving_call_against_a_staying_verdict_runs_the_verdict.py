"""A call that LEAVES, against a sure verdict for an act on the same card that STAYS, runs the verdict (node 2.1622).

Demo pass 2026-09-28, full12 E3: «draft a short reply…» read `mensajeria:draft` at 1.00, the model called `reply`, and
a real email went out. Since V2-852 M2 an act that leaves is a task the turn routes — and the routing ran BEFORE the
two readers were compared, so the same disagreement sent the `reply` to a worker: what he asked only to be drafted
was commissioned as a send. The arbitration now runs first: the verdict's act stays on the machine and takes the
model's content. Two leaving readers (verdict `send_to`, model `reply`) are still a task — the worker decides at its
exit door.
"""
from __future__ import annotations

import pytest

from tests import widget_data_rig as rig

TURNS = {"es": "redacta una respuesta corta diciendo que mandaré el enlace de la reunión",
         "en": "draft a short reply saying I'll send the meet link"}


@pytest.fixture()
def scene(tmp_path, monkeypatch):
    from nucleo import his_words, untrusted
    rig.scene(tmp_path, monkeypatch)
    yield
    untrusted.reset()
    his_words.reset()


def _routed(out) -> bool:
    return any("an act that leaves is a task" in label for _k, label in out.events)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_reply_against_a_sure_draft_verdict_drafts_and_routes_nothing(scene, monkeypatch, lang):
    out = rig.run("mensajeria", "reply", {"n": 1, "text": "I'll send the meet link"}, said=TURNS[lang],
                  turn_brief=rig.brief("mensajeria:draft", 1.0), monkeypatch=monkeypatch)
    assert [a for _w, a, _p in out.ran] == ["draft"] and out.ran[0][2].get("text"), out
    assert not _routed(out), "the staying verdict ran: nothing is commissioned to leave"


def test_two_leaving_readers_stay_a_task(scene, monkeypatch):
    out = rig.run("mensajeria", "reply", {"n": 1, "text": "I'll send the meet link"},
                  said="reply to Quinn that I'll send the meet link",
                  turn_brief=rig.brief("mensajeria:send_to", 1.0), monkeypatch=monkeypatch)
    assert _routed(out) and not out.ran, out


def test_no_verdict_leaves_the_call_a_task(scene, monkeypatch):
    out = rig.run("mensajeria", "reply", {"n": 1, "text": "ok"}, said="reply ok to the first one",
                  turn_brief=rig.brief("", 1.0), monkeypatch=monkeypatch)
    assert _routed(out) and not out.ran, out


def test_disarmed_the_reply_is_commissioned_as_a_send(scene, monkeypatch):
    from nucleo.flash import tool_executor_widget_calls as calls
    monkeypatch.setattr(calls, "_verdict_instead", lambda *a, **k: None)
    out = rig.run("mensajeria", "reply", {"n": 1, "text": "I'll send the meet link"}, said=TURNS["en"],
                  turn_brief=rig.brief("mensajeria:draft", 1.0), monkeypatch=monkeypatch)
    assert _routed(out) and not out.ran, "without the arbitration the draft he asked for is routed as a send"
