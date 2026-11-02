"""nucleo/browser_window.py — can this engine put a browser window in front of him? (V2-822)

Some steps of an errand need HIM in a real browser: a site that asks him to sign in, a challenge only a person
passes. The process then waits for him and watches the window it opened. Whether there CAN be such a window is one
question with one answer, and it is answered here — never by a caller re-reading the environment on its own:

  · `here`   — the engine runs where he is, on a machine with a GRAPHICAL SERVER: the window opens directly (the
               in-process browser relaunches headed, its profile keeps the session) and the process watches it.
  · `daemon` — the engine runs where no window exists (a container, a VM, a headless server), and the local daemon on
               his computer is
               CONNECTED and declares it can open a browser for him (`BROWSER_CAPABILITY`). The window opens there.
  · ``       — neither. No window can reach him, so a process that needs him to authenticate is BLOCKED, with that
               state on its entry in the processes panel, and the agent tells him why it cannot continue.

THE DAEMON LINK. Whatever transport carries a daemon's connection to this engine registers what the daemon declared
with `daemon_connected(capabilities, opener)` and clears it with `daemon_gone()`; `opener(url, task_id)` is how a
window is opened through it. The engine never guesses a daemon's abilities: a capability the engine believes in is
a promise to him (`daemon/http/routes.py` holds the same rule on the daemon's side). Until a transport registers a
daemon that declares the browser capability, an engine without a display answers `` — honestly blocked.

WHAT «A DISPLAY» MEANS. Not «is this a container» and not «is DISPLAY set»: a virtual machine carries no container
marker and no DISPLAY yet has no screen, and a service started by systemd on a Linux desktop has no DISPLAY in its env
yet can open a window on the desktop's X server. The question is whether a graphical server ANSWERS: on Linux an X or
Wayland socket this process can connect to (the one the env names, else the ones a desktop session leaves in
`/tmp/.X11-unix` and the runtime dir); on macOS a window-server session for this process; on Windows a session other
than the services' session 0. `display_env()` returns what a launched browser needs to reach that server (a DISPLAY
the env did not carry), and the answer is cached for `_DISPLAY_TTL` seconds — it is read on every voice turn.

Never raises: a question that cannot be answered answers ``, which blocks with a clear state rather than opening a
window that will never appear.
"""
from __future__ import annotations

import glob
import logging
import os
import platform
import socket
import threading
import time

HERE = "here"
DAEMON = "daemon"
#: What a connected daemon declares when it can open a browser window on his computer for him.
BROWSER_CAPABILITY = "browser.auth"

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_link: dict = {}          # {"caps": frozenset, "opener": callable} while a daemon is connected


_DISPLAY_TTL = 30.0
_probe: dict = {"at": None, "env": None}   # the last answer of `_probe_display()` and when it was taken


def _answers(path: str = "", host: str = "", port: int = 0) -> bool:
    """Does a graphical server accept a connection here (a unix socket path, or a TCP host:port)? Connecting proves
    the server is alive and reachable by this process; a stale socket file or a dead forward refuses."""
    try:
        if path:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            target = path
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target = (host, port)
        s.settimeout(0.3)
        try:
            s.connect(target)
            return True
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001 — refused, absent, no permission: no server for us
        _log.debug("browser_window: no graphical server at %s: %s", path or f"{host}:{port}", e)
        return False


def _x_answers(display: str) -> bool:
    """`:0`, `unix:0.0` → the local socket; `host:10.0` (an ssh -X forward) → TCP 6000+n."""
    host, _, rest = (display or "").rpartition(":")
    num = rest.split(".", 1)[0]
    if not num.isdigit():
        return False
    if host in ("", "unix"):
        return _answers(path=f"/tmp/.X11-unix/X{num}")
    return _answers(host=host, port=6000 + int(num))


def _runtime_dir() -> str:
    return os.environ.get("XDG_RUNTIME_DIR") or (f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else "")


def _unix_display_env() -> dict | None:
    """Linux and the other unixes: the X or Wayland server this process can reach, or None."""
    disp = os.environ.get("DISPLAY", "").strip()
    if disp and _x_answers(disp):
        return {}
    way = os.environ.get("WAYLAND_DISPLAY", "").strip()
    if way and _answers(path=way if way.startswith("/") else os.path.join(_runtime_dir(), way)):
        return {}
    # No usable env (a service on a desktop): the sockets a running desktop session leaves behind.
    for sock in sorted(glob.glob("/tmp/.X11-unix/X*")):
        num = sock.rsplit("X", 1)[-1]
        if num.isdigit() and _answers(path=sock):
            return {"DISPLAY": f":{num}"}
    rd = _runtime_dir()
    for sock in sorted(glob.glob(os.path.join(rd, "wayland-*"))) if rd else ():
        if not sock.endswith(".lock") and _answers(path=sock):
            return {"WAYLAND_DISPLAY": sock, "XDG_RUNTIME_DIR": rd}
    return None


def _mac_display_env() -> dict | None:
    """macOS: a window-server session for this process (none for a launchd daemon or an ssh login without one)."""
    try:
        import ctypes
        import ctypes.util
        cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
        cg.CGSessionCopyCurrentDictionary.restype = ctypes.c_void_p
        return {} if cg.CGSessionCopyCurrentDictionary() else None
    except Exception as e:  # noqa: BLE001 — the API is unreachable: a Mac is a desktop
        _log.debug("browser_window: CGSession unreadable (%s); assuming a desktop", e)
        return {}


def _windows_display_env() -> dict | None:
    """Windows: services run in session 0, which has no desktop a person sees."""
    try:
        import ctypes
        sid = ctypes.c_ulong()
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if not k32.ProcessIdToSessionId(k32.GetCurrentProcessId(), ctypes.byref(sid)):
            return {}
        return {} if sid.value != 0 else None
    except Exception as e:  # noqa: BLE001 — the API is unreachable: assume a desktop session
        _log.debug("browser_window: session id unreadable (%s); assuming a desktop", e)
        return {}


def _probe_display() -> dict | None:
    system = platform.system()
    if system == "Darwin":
        return _mac_display_env()
    if system == "Windows":
        return _windows_display_env()
    return _unix_display_env()


def display_env() -> dict | None:
    """The graphical server a window can open on, as the env vars a launched browser must add to reach it (`{}` when
    its own env already does); None when there is no graphical server here."""
    now = time.monotonic()
    with _lock:
        if _probe["at"] is not None and now - _probe["at"] < _DISPLAY_TTL:
            return _probe["env"]
    try:
        env = _probe_display()
    except Exception as e:  # noqa: BLE001 — a probe that cannot answer: no window, blocked honestly
        _log.warning("browser_window: display probe failed: %s", e)
        env = None
    with _lock:
        _probe.update(at=now, env=env)
    return env


def _has_display() -> bool:
    """Does this engine run where a real window can open — is there a graphical server it can reach?"""
    return display_env() is not None


def daemon_connected(capabilities, opener=None) -> None:
    """A daemon on his computer is connected and declared these capabilities (called by its transport)."""
    with _lock:
        _link.clear()
        _link.update({"caps": frozenset(str(c) for c in (capabilities or ())), "opener": opener})


def daemon_gone() -> None:
    """The daemon's connection dropped (called by its transport)."""
    with _lock:
        _link.clear()


def reach() -> str:
    """Where a browser window for him can open: `here`, `daemon`, or `` (nowhere)."""
    if _has_display():
        return HERE
    with _lock:
        if BROWSER_CAPABILITY in (_link.get("caps") or ()) and callable(_link.get("opener")):
            return DAEMON
    return ""


async def open_on_daemon(url: str, task_id: str) -> bool:
    """Open `url` in a window on his computer through the connected daemon. False when no daemon can."""
    with _lock:
        opener = _link.get("opener") if BROWSER_CAPABILITY in (_link.get("caps") or ()) else None
    if not callable(opener):
        return False
    try:
        res = opener(url, task_id)
        if hasattr(res, "__await__"):
            res = await res
        return res is not False
    except Exception as e:  # noqa: BLE001 — a window that could not open is a blocked process, not a crash
        _log.warning("browser_window: daemon could not open %s: %s", url, e)
        return False
