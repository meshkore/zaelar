"""A browser window for him can open HERE only where a graphical server answers (V2-835 T5).

`nucleo/browser_window.reach()` used to ask «is this a container?» (a Docker marker in `/.dockerenv` or the cgroup).
A virtual machine carries no such marker and has no screen, so it answered `here` and a login window was opened where nobody
could ever see it. The class is not «which host is this» but «does a graphical server answer this process»: on Linux an
X/Wayland socket it can connect to — the one its env names, else the one a desktop session leaves behind (a service
started on a desktop has no DISPLAY in its env yet can open a window) — and the launched browser is told how to reach it.

Disarm: the unix probe answering «a display» whatever the sockets say → red.
"""
import os
import shutil
import socket
import tempfile

import pytest

from nucleo import browser_window as bw


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    bw._probe.update(at=None, env=None)
    bw.daemon_gone()
    monkeypatch.setattr(bw.platform, "system", lambda: "Linux")
    for var in ("DISPLAY", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(var, raising=False)
    d = tempfile.mkdtemp(dir="/tmp")          # short path: a unix socket path is bounded (~104 bytes on macOS)
    monkeypatch.setenv("XDG_RUNTIME_DIR", d)
    socks: list = []
    yield d, socks
    for s in socks:
        s.close()
    shutil.rmtree(d, ignore_errors=True)
    bw._probe.update(at=None, env=None)


def _listen(path: str, socks: list) -> str:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(path)
    s.listen(16)
    socks.append(s)
    return path


def _x11_dir(monkeypatch, paths: list) -> None:
    real = bw.glob.glob
    monkeypatch.setattr(bw.glob, "glob", lambda pat: list(paths) if pat == "/tmp/.X11-unix/X*" else real(pat))


def test_a_headless_vm_has_no_window(monkeypatch):
    """No DISPLAY, no WAYLAND_DISPLAY, no socket of a desktop session — and no container marker either."""
    _x11_dir(monkeypatch, [])
    assert bw.display_env() is None
    assert bw.reach() == "", "no graphical server and no daemon: nowhere"


def test_a_stale_display_variable_is_not_a_display(monkeypatch, _fresh):
    d, _ = _fresh
    _x11_dir(monkeypatch, [])
    monkeypatch.setenv("DISPLAY", ":93")          # names a server that is not there
    monkeypatch.setenv("WAYLAND_DISPLAY", os.path.join(d, "wayland-gone"))
    assert bw.display_env() is None


def test_a_service_on_a_desktop_finds_its_x_server(monkeypatch, _fresh):
    """systemd starts the engine without DISPLAY; the desktop's X socket answers → a window CAN open, on that server."""
    d, socks = _fresh
    sock = _listen(os.path.join(d, "X7"), socks)
    _x11_dir(monkeypatch, [sock])
    assert bw.display_env() == {"DISPLAY": ":7"}
    assert bw.reach() == bw.HERE


def test_a_wayland_session_is_a_display(monkeypatch, _fresh):
    d, socks = _fresh
    _x11_dir(monkeypatch, [])
    sock = _listen(os.path.join(d, "wayland-0"), socks)
    assert bw.display_env() == {"WAYLAND_DISPLAY": sock, "XDG_RUNTIME_DIR": d}
    bw._probe.update(at=None, env=None)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")   # named by the env (relative to the runtime dir): nothing to add
    assert bw.display_env() == {}


def test_the_platform_decides_which_probe(monkeypatch):
    monkeypatch.setattr(bw, "_mac_display_env", lambda: None)
    monkeypatch.setattr(bw.platform, "system", lambda: "Darwin")
    assert bw.display_env() is None, "macOS with no window-server session (a launchd daemon, a bare ssh login)"
    bw._probe.update(at=None, env=None)
    monkeypatch.setattr(bw, "_windows_display_env", lambda: {})
    monkeypatch.setattr(bw.platform, "system", lambda: "Windows")
    assert bw.display_env() == {}


def test_the_answer_is_cached_and_a_failing_probe_means_nowhere(monkeypatch):
    calls = []

    def _boom():
        calls.append(1)
        raise OSError("probe")
    monkeypatch.setattr(bw, "_probe_display", _boom)
    assert bw.display_env() is None and bw.reach() == ""
    bw.display_env()
    assert len(calls) == 1, "read on every voice turn: one probe per TTL"

