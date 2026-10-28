"""Agent-side voice isolation is ONE setting, and it fails open (V2-812 T-08, node 3.138).

`ZAELAR_VOICE_ISOLATION` (off | nc | bvc) decides whether a noise-cancellation filter is attached to the room's audio
input. Off → nothing is passed and the session is what it was. On, where the transport cannot serve it (a
self-hosted livekit-server refuses the filter: «not authorized for this connection») or the plugin cannot load →
the session starts exactly as with off and ONE warning says why. On, on a LiveKit Cloud project → the filter rides
in `room_options.audio_input.noise_cancellation`.
"""
import pytest

from voice.engine.pipeline import voice_isolation as vi

CLOUD = "wss://example-project.livekit.cloud"
SELF_HOSTED = "ws://127.0.0.1:7880"


class _FakePlugin:
    @staticmethod
    def NC():
        return "NC-filter"

    @staticmethod
    def BVC():
        return "BVC-filter"


def _load_ok():
    return _FakePlugin


def _load_missing():
    raise ImportError("No module named 'livekit.plugins.noise_cancellation'")


def _load_broken():
    # what `rtc.AudioFilter` raises when the native library cannot load on this platform
    raise Exception("failed to initialize audio filter #1")


@pytest.fixture(autouse=True)
def _fresh_warnings():
    vi._warned.clear()
    yield
    vi._warned.clear()


@pytest.fixture
def warned(monkeypatch):
    """The module's warnings, captured at the logger call — a logging config left by another test cannot hide them."""
    seen: list[str] = []
    monkeypatch.setattr(vi.logger, "warning", lambda msg, *a: seen.append(msg % a if a else msg))
    return seen


def test_the_setting_is_declared_once_and_defaults_to_bvc():
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    hits = subprocess.run(["git", "grep", "-l", "ZAELAR_VOICE_ISOLATION\"", "--", "*.py", ":!tests"],
                          cwd=root, capture_output=True, text=True).stdout.split()
    assert hits == ["voice/engine/core/config.py"], hits
    assert 'env("ZAELAR_VOICE_ISOLATION", "bvc")' in (root / hits[0]).read_text(encoding="utf-8")


def test_off_attaches_nothing_and_says_nothing(warned):
    assert vi.room_options("off", CLOUD, load=_load_ok) == {}
    assert vi.room_options("", CLOUD, load=_load_ok) == {}
    assert warned == []


@pytest.mark.parametrize("url, load, reason", [
    (CLOUD, _load_missing, "unavailable"),
    (CLOUD, _load_broken, "unavailable"),
])
def test_on_but_unsupported_fails_open_with_one_warning(warned, url, load, reason):
    for _ in range(3):   # three sessions in one process → still one warning
        assert vi.room_options("bvc", url, load=load) == {}
    assert len(warned) == 1 and reason in warned[0], warned


def test_a_self_hosted_server_skips_it_quietly_once(warned, caplog):
    """The default is on, so a self-hosted livekit-server is the ordinary case: no warning, one info line."""
    import logging
    caplog.set_level(logging.INFO)
    for _ in range(3):
        assert vi.room_options("bvc", SELF_HOSTED, load=_load_ok) == {}
    assert warned == []
    assert sum("LiveKit Cloud" in r.getMessage() for r in caplog.records) == 1


def test_an_unknown_mode_fails_open(warned):
    assert vi.room_options("krisp-max", CLOUD, load=_load_ok) == {}
    assert len(warned) == 1


@pytest.mark.parametrize("mode, expected", [("bvc", "BVC-filter"), ("nc", "NC-filter"), ("BVC", "BVC-filter")])
def test_on_and_supported_passes_the_filter_to_the_audio_input(mode, expected):
    opts = vi.room_options(mode, CLOUD, load=_load_ok)
    assert opts["room_options"].audio_input.noise_cancellation == expected


def test_only_a_livekit_cloud_host_counts_as_cloud():
    assert vi.is_livekit_cloud(CLOUD)
    for url in (SELF_HOSTED, "wss://livekit.example.com", "wss://livekit.cloud.evil.example", ""):
        assert not vi.is_livekit_cloud(url), url


def test_the_session_start_carries_the_setting(monkeypatch):
    from voice.engine.pipeline import agent
    from nucleo.energy import egress as llm_egress
    monkeypatch.setattr(llm_egress, "mediated", lambda: False)
    seen = {}

    def fake(mode, url, **_):
        seen["args"] = (mode, url)
        return {"room_options": "R"}

    monkeypatch.setattr(vi, "room_options", fake)
    assert agent._session_start_opts() == {"room_options": "R"}
    assert seen["args"] == (agent.SETTINGS.voice_isolation, agent.SETTINGS.livekit_url)


def test_disarm_without_the_transport_check_the_self_hosted_case_goes_red(monkeypatch):
    """Mutate the guard the fail-open test claims to protect, and see that test fail."""
    monkeypatch.setattr(vi, "is_livekit_cloud", lambda url: True)
    assert vi.room_options("bvc", SELF_HOSTED, load=_load_ok) != {}, "disarm did not land"


class _Stop(Exception):
    pass


def _run_entrypoint_until_connect(monkeypatch):
    """Run the real entrypoint up to `ctx.connect()` and return the order in which preload and connect happened."""
    import asyncio
    from voice.engine.pipeline import agent
    order = []
    monkeypatch.setattr(agent, "setup_console_logging", lambda: None)
    monkeypatch.setattr(vi, "preload", lambda mode, url, **_: order.append("preload") or True)

    class Ctx:
        async def connect(self):
            order.append("connect")
            raise _Stop

    with pytest.raises(_Stop):
        asyncio.run(agent.entrypoint(Ctx()))
    return order


def test_the_plugin_is_registered_before_the_room_connects(monkeypatch):
    """The FFI initialises a filter for a room only at connect: registering it after is code 209, unfiltered."""
    assert _run_entrypoint_until_connect(monkeypatch) == ["preload", "connect"]


def test_preload_has_the_same_gates_as_the_filter():
    assert vi.preload("bvc", CLOUD, load=_load_ok) is True
    assert vi.preload("off", CLOUD, load=_load_ok) is False
    assert vi.preload("bvc", SELF_HOSTED, load=_load_ok) is False
    assert vi.preload("bvc", CLOUD, load=_load_missing) is False
