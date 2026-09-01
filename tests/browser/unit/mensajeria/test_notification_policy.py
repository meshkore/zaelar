"""Per-connector notification policy (V2-532).

The operator's direction (2026-09-01): whether a channel may INTERRUPT him must be configurable per connector —
which arriving messages surface proactively, and whether a surfaced batch may be spoken. Until this, the filter
was one frozen predicate inside notify.surface() and the only knob was muted_channels.

The load-bearing properties: an UNTOUCHED install behaves byte-for-byte as before (default = the historical
predicate), a broken store degrades to that default and never to silence, and the widget action that sets the
policy rejects garbage loudly instead of saving something that later reads as DEFAULT.
"""
import os
import tempfile

import pytest

from widgets.mensajeria import policy


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch):
    home = tempfile.mkdtemp()
    monkeypatch.setenv("ZAELAR_HOME", home)
    # widgets.store caches its data root per process; repoint it for this test.
    from widgets import store as wstore
    if hasattr(wstore, "_DATA_DIR"):
        monkeypatch.setattr(wstore, "_DATA_DIR", None, raising=False)
    yield


def _verdict(**kw):
    base = {"platform": "telegram", "messageId": "m1",
            "importante": False, "dirigido_a_mi": False, "urgencia": "baja"}
    base.update(kw)
    return base


def test_default_policy_is_the_historical_predicate():
    """important AND (addressed-to-me OR high urgency) — byte-for-byte what surface() always did."""
    pol = policy.normalize(None)
    assert pol == {"notify": "important", "speak": True}
    assert policy.wants_notice(pol, _verdict(importante=True, urgencia="alta"))
    assert policy.wants_notice(pol, _verdict(importante=True, dirigido_a_mi=True))
    assert not policy.wants_notice(pol, _verdict(importante=True))            # important but neither
    assert not policy.wants_notice(pol, _verdict(urgencia="alta"))            # urgent but not important


def test_each_level_means_what_it_says():
    assert not policy.wants_notice({"notify": "never"}, _verdict(importante=True, urgencia="alta"))
    assert policy.wants_notice({"notify": "all"}, _verdict())
    assert policy.wants_notice({"notify": "direct"}, _verdict(dirigido_a_mi=True))
    assert not policy.wants_notice({"notify": "direct"}, _verdict(importante=True, urgencia="alta"))


def test_speak_false_takes_the_voice_away_but_never_forces_it():
    urgent = [_verdict(urgencia="alta")]
    calm = [_verdict()]
    assert policy.wants_voice({"speak": True}, urgent)
    assert not policy.wants_voice({"speak": False}, urgent)   # policy can silence
    assert not policy.wants_voice({"speak": True}, calm)      # …but never forces speech on a calm batch


def test_a_broken_shape_degrades_to_default_never_to_silence():
    for garbage in (42, "loud", ["x"], {"notify": "shout", "speak": "yes"}):
        assert policy.normalize(garbage) == policy.DEFAULT


def test_surface_consults_the_stored_policy_per_platform():
    """The wiring, not just the rule: a stored 'direct' policy for telegram must drop the urgent-but-unaddressed
    message THROUGH notify.surface, while whatsapp keeps the default."""
    from widgets.mensajeria import data
    r = data.apply_action("set_notify", {"platform": "telegram", "notify": "direct"})
    assert r["ok"], r
    from connectors.messaging import notify
    verdicts = [
        _verdict(messageId="t1", importante=True, urgencia="alta"),                      # telegram, dropped
        _verdict(messageId="t2", dirigido_a_mi=True),                                    # telegram, kept
        _verdict(platform="whatsapp", messageId="w1", importante=True, urgencia="alta"),  # default, kept
    ]
    out = [v["messageId"] for v in notify.surface(verdicts, set())]
    assert out == ["t2", "w1"], out


def test_set_notify_rejects_garbage_loudly():
    """A voice-set policy must fail loudly, not save something that later reads as DEFAULT and makes the
    operator think his change took."""
    from widgets.mensajeria import data
    bad = data.apply_action("set_notify", {"platform": "telegram", "notify": "loud"})
    assert bad["ok"] is False and "notify" in bad["error"]
    worse = data.apply_action("set_notify", {"platform": "myspace", "notify": "all"})
    assert worse["ok"] is False and "platform" in worse["error"]


def test_view_data_always_exposes_the_full_effective_policy():
    """A reader must never have to guess what an absent entry means: all platforms, normalized values."""
    from widgets.mensajeria import data
    data.apply_action("set_notify", {"platform": "email", "speak": False})
    v = data.view_data()
    pols = v["notify_policy"]
    assert set(pols) == {"whatsapp", "telegram", "email"}
    assert pols["email"] == {"notify": "important", "speak": False}
    assert pols["whatsapp"] == policy.DEFAULT


def test_an_explicit_reminder_is_never_governed_by_this_policy():
    """The V2-522 principle: an order the operator gave is its own permission to interrupt. The scheduler's
    delivery path must not consult this module — a 'never' policy on every platform cannot mute an agenda
    reminder. Guarded at the source: nothing under nucleo/ imports the policy module."""
    import pathlib
    import re
    root = pathlib.Path(policy.__file__).resolve().parents[2]
    hits = []
    for f in (root / "nucleo").rglob("*.py"):
        if re.search(r"mensajeria\s*import\s+policy|mensajeria\.policy", f.read_text(errors="ignore")):
            hits.append(str(f))
    assert not hits, f"the scheduler/delivery side must not consult the messaging policy: {hits}"
