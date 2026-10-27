"""nucleo/browser_window.py — can this engine put a browser window in front of him? (V2-822)

Some steps of an errand need HIM in a real browser: a site that asks him to sign in, a challenge only a person
passes. The process then waits for him and watches the window it opened. Whether there CAN be such a window is one
question with one answer, and it is answered here — never by a caller re-reading the environment on its own:

  · `here`   — the engine runs where he is, on a machine with a display: the window opens directly (the in-process
               browser relaunches headed, its profile keeps the session) and the process watches it.
  · `daemon` — the engine runs where no window exists (a container), and the local daemon on his computer is
               CONNECTED and declares it can open a browser for him (`BROWSER_CAPABILITY`). The window opens there.
  · ``       — neither. No window can reach him, so a process that needs him to authenticate is BLOCKED, with that
               state on its entry in the processes panel, and the agent tells him why it cannot continue.

THE DAEMON LINK. Whatever transport carries a daemon's connection to this engine registers what the daemon declared
with `daemon_connected(capabilities, opener)` and clears it with `daemon_gone()`; `opener(url, task_id)` is how a
window is opened through it. The engine never guesses a daemon's abilities: a capability the engine believes in is
a promise to him (`daemon/http/routes.py` holds the same rule on the daemon's side). Until a transport registers a
daemon that declares the browser capability, an engine without a display answers `` — honestly blocked.

Never raises: a question that cannot be answered answers ``, which blocks with a clear state rather than opening a
window that will never appear.
"""
from __future__ import annotations

import threading

HERE = "here"
DAEMON = "daemon"
#: What a connected daemon declares when it can open a browser window on his computer for him.
BROWSER_CAPABILITY = "browser.auth"

_lock = threading.Lock()
_link: dict = {}          # {"caps": frozenset, "opener": callable} while a daemon is connected


def _has_display() -> bool:
    """Does this engine run where a real window can open? A container has no display."""
    try:
        from config import doctor
        return not bool(doctor.hardware().get("container"))
    except Exception:  # noqa: BLE001 — unknown environment: assume the common self-hosted desktop
        return True


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
        __import__("logging").getLogger(__name__).warning("browser_window: daemon could not open %s: %s", url, e)
        return False
