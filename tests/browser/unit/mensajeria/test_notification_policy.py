"""Per-connector notification policy (V2-532, defaults reversed and split in two by V2-607).

The operator's direction (2026-09-01): whether a channel may INTERRUPT him must be configurable per connector.
His direction of 2026-09-07 changed the answer the configuration STARTS at, and split the one knob into two:

  · notify    — who may interrupt him. DEFAULT: nobody. He is often reading the very messages that arrive, and
                since V2-606 a thousand-message backlog can reach the widget; being told is a thing he ASKS for.
  · highlight — what the summary tab puts in front of him. DEFAULT: what is addressed to him. Every other
                message is still there, unread, in its own channel's section.

The load-bearing properties: the historical predicate is still exactly reachable (`notify: important`), a broken
store degrades to the default — which is now silence, deliberately, because the setting a broken config must not
resurrect is the one that talks — and the widget action that sets the policy rejects garbage loudly instead of
saving something that later reads as DEFAULT.
"""
import pytest

from widgets.mensajeria import policy


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch, tmp_path):
    """A FRESH store per test.

    This used to set ZAELAR_HOME and then repoint `wstore._DATA_DIR` — an attribute that does not exist, so the
    guard `if hasattr(...)` made the whole thing a silent no-op. What actually isolated the module was an
    accident of import order: `widgets.store` computes `DATA_DIR` at import time, and the first test to import it
    froze it to that test's temp home for the entire module. So the tests shared one store and leaked policy into
    each other, and the leak was invisible because the value that leaked (`important`) happened to equal the
    default they asserted. Inverting the default in V2-607 is what made it show. Patched the way the owner suite
    next door already does it — on the constant the code actually reads."""
    from widgets import store as wstore
    monkeypatch.setenv("ZAELAR_HOME", str(tmp_path))
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    wstore._last_hash.clear()
    yield


def _verdict(**kw):
    base = {"platform": "telegram", "messageId": "m1",
            "importante": False, "dirigido_a_mi": False, "urgencia": "baja"}
    base.update(kw)
    return base


def test_by_default_nothing_interrupts_him():
    """V2-607, his direction. Not «less noise» — none, until he asks for it."""
    pol = policy.normalize(None)
    assert pol == {"notify": "never", "speak": True, "highlight": "direct"}
    assert not policy.wants_notice(pol, _verdict(importante=True, urgencia="alta"))
    assert not policy.wants_notice(pol, _verdict(importante=True, dirigido_a_mi=True))


def test_the_historical_predicate_is_still_exactly_reachable():
    """important AND (addressed-to-me OR high urgency) — byte-for-byte what surface() always did. It stopped
    being the DEFAULT; it must not have stopped being available, or «avísame como antes» has no answer."""
    pol = policy.normalize({"notify": "important"})
    assert policy.wants_notice(pol, _verdict(importante=True, urgencia="alta"))
    assert policy.wants_notice(pol, _verdict(importante=True, dirigido_a_mi=True))
    assert not policy.wants_notice(pol, _verdict(importante=True))            # important but neither
    assert not policy.wants_notice(pol, _verdict(urgencia="alta"))            # urgent but not important


def test_the_summary_shows_what_is_addressed_to_him_and_the_rest_still_exists():
    """`highlight` is a different question from `notify`: what to put in FRONT of him when he looks, not what to
    interrupt him with. Default `direct`. A message that misses it is not hidden — it is in its channel."""
    pol = policy.normalize(None)
    assert policy.wants_highlight(pol, _verdict(dirigido_a_mi=True))
    assert not policy.wants_highlight(pol, _verdict(importante=True, urgencia="alta"))
    assert policy.wants_highlight(policy.normalize({"highlight": "all"}), _verdict())
    # And it has no "never": an empty main tab is a broken screen, not a policy.
    assert "never" not in policy.HIGHLIGHT_LEVELS
    assert policy.normalize({"highlight": "never"})["highlight"] == "direct"


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


def test_a_broken_shape_degrades_to_the_default():
    """Which is silence for `notify` since V2-607 — on purpose. The old name of this test said «never to
    silence»; that was right while the default TALKED, and inverting the default inverts the hazard: a
    half-written store must not be able to switch the loudspeaker back on."""
    for garbage in (42, "loud", ["x"], {"notify": "shout", "speak": "yes", "highlight": "nope"}):
        assert policy.normalize(garbage) == policy.DEFAULT
    assert policy.DEFAULT["notify"] == "never"


def test_the_notice_consults_the_stored_policy_per_platform():
    """The wiring, not just the rule: a stored 'direct' policy for telegram must drop the urgent-but-unaddressed
    message THROUGH notify.deserving, while whatsapp keeps its own.

    `notify.surface` — which did this AND the de-duplication AND gated the storing — is gone as of V2-607. It was
    left with no callers once the four ingest paths split the two questions, and a dead function carrying the old
    coupling is how the coupling comes back."""
    from widgets.mensajeria import data
    r = data.apply_action("set_notify", {"platform": "telegram", "notify": "direct"})
    assert r["ok"], r
    # whatsapp is set EXPLICITLY since V2-607: with nothing stored it would be silent like every channel, and
    # this test would then pass for the wrong reason — it is here to prove the lookup is per platform.
    assert data.apply_action("set_notify", {"platform": "whatsapp", "notify": "important"})["ok"]
    from connectors.messaging import notify
    verdicts = [
        _verdict(messageId="t1", importante=True, urgencia="alta"),                      # telegram, dropped
        _verdict(messageId="t2", dirigido_a_mi=True),                                    # telegram, kept
        _verdict(platform="whatsapp", messageId="w1", importante=True, urgencia="alta"),  # important, kept
    ]
    out = [v["messageId"] for v in notify.deserving(verdicts)]
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
    assert pols["email"] == {"notify": "never", "speak": False, "highlight": "direct"}
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
