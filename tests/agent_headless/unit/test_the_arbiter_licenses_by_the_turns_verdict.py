"""The canvas arbiter reads the turn's PAID verdict first; the word leaves only decide where it is silent (refactor2710-04).

Replayed over the operator's archive, the word leaves vetoed six mutations the brief had ordered — four closes
(`canvas=close`, two of them «close everything») and two data ops whose `screen_action` named exactly that card and
action. A word gate above a paid verdict is what CRIT-K1 forbids. The canvas reporting what it already did (`client`)
and a task's wall opening its own card (`wall:<tid>`) are declared provenances, never judged by words.
"""
from __future__ import annotations

import pytest

from nucleo import canvas_arbiter as arb

MUTE = "mm, vale"           # words no leaf licenses: only the verdict can


def test_the_verdict_licenses_what_the_words_did_not():
    assert arb.decide("close", "musica", "flash", text=MUTE, verdict={"canvas": ("close", 0.99)}).rule == "verdict-close"
    assert arb.decide("close", "", "flash", text=MUTE, verdict={"canvas": ("close", 0.66)}).allow
    v = arb.decide("data", "youtube", "flash", action="pause", text=MUTE,
                   verdict={"screen_action": ("youtube:pause", 0.98)})
    assert v.allow and v.rule == "verdict-action"
    assert arb.decide("show", "navegador", "flash", text=MUTE,
                      verdict={"canvas": ("neither", 0.98), "catalog_widget": ("navegador", 0.88)}).rule == "verdict-catalog"


def test_a_sure_contrary_verdict_vetoes_and_a_close_order_licenses_no_show():
    assert arb.decide("close", "agenda", "flash", text="cierra la agenda",
                      verdict={"canvas": ("neither", 0.95)}).rule == "verdict-against"
    assert arb.decide("show", "agenda", "flash", text="la agenda",
                      verdict={"canvas": ("close", 0.9)}).rule == "verdict-close-not-show"


def test_an_unsure_or_absent_verdict_leaves_the_words_to_decide():
    assert arb.decide("close", "youtube", "flash", text="cierra el widget de youtube").rule == "close-grammar"
    assert arb.decide("close", "youtube", "flash", text=MUTE, verdict={"canvas": ("close", 0.46)}).rule == "close-drag"


def test_a_report_and_a_wall_are_declared_provenances():
    assert arb.decide("close", "results", "client", text=MUTE).rule == "report"
    v = arb.decide("show", "results::1", "wall:t1", text=MUTE)
    assert v.allow and v.rule == "task-owned" and v.evidence.get("via") == "wall"


@pytest.fixture
def verdicts(monkeypatch):
    import voice.observer as obs
    out = []
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        out.append({"kind": kind, "label": label, **(extra or {})}))
    arb._last_turn.update(text="", ts=0.0, credit=True)
    arb._reads.clear()
    return out


def test_the_tap_reads_the_brief_off_its_events_and_the_verdict_event_carries_it(verdicts):
    arb.shadow_tap("brain", "jev read canvas", "", "system",
                   {"question": "canvas", "choice": "close", "confidence": 0.87, "trace": "T19·5b76"})
    arb.shadow_tap("transcript", "🗣", MUTE, "user", None)
    arb.shadow_tap("widget", "close", "", "", {"id": "musica", "src": "flash", "trace": "T19·5b76"})
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v["kind"] == "arbiter" and v["label"] == "✅ permitiría · verdict-close", "kind and label keep their shape"
    assert v["verdict"] == {"canvas": {"choice": "close", "confidence": 0.87}} and v["source"] == "flash"


def test_the_real_observer_hands_the_briefs_reads_to_the_arbiter(monkeypatch):
    """Through `voice.observer.emit` itself: the brief's `jev read` events must reach the arbiter, or every live
    verdict is judged on an empty brief — what happened until this was wired."""
    import voice.observer as obs
    seen = []
    monkeypatch.setattr(arb, "_emit_verdict", lambda op, wid, src, action, v, **kw: seen.append((v.rule, kw.get("brief"))))
    arb._reads.clear()
    obs.emit("brain", "jev read canvas", role="system",
             extra={"question": "canvas", "choice": "close", "confidence": 0.9, "trace": "T7·beef"})
    obs.emit("widget", "close", extra={"id": "musica", "src": "flash", "trace": "T7·beef"})
    assert seen and seen[-1][0] == "verdict-close" and seen[-1][1] == {"canvas": ("close", 0.9)}


def test_disarm_without_the_verdict_licence_the_words_veto_the_ordered_close(monkeypatch):
    monkeypatch.setattr(arb, "_verdict_licence", lambda *a, **k: None)
    assert arb.decide("close", "musica", "flash", text=MUTE, verdict={"canvas": ("close", 0.99)}).rule == "close-drag"
