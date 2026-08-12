#!/usr/bin/env python3
"""
zaelar.py — start / stop / restart / status for a LOCAL zaelar instance. One command, every platform.

WHY THIS EXISTS
    The old entry points were bash (`scripts/run-livekit.sh`, `scripts/stop.sh`), so they only ever worked on
    macOS/Linux — and zaelar is a public, self-hosted project: a Windows user could not start or stop it. Python is
    already a hard requirement (the app IS Python), so the lifecycle lives here and the Makefile is a thin wrapper.
    Windows users who have no `make` run this file directly:

        python scripts/zaelar.py start        (macOS/Linux: `make start`)

WHAT IT FIXES, LEARNED THE HARD WAY (2026-08-10/12)
    · `start` is IDEMPOTENT. Launching over a live instance used to leave the ports taken, the new process dying on a
      silent EADDRINUSE, and the app looking started while nothing worked. Now it detects the live instance and says so.
    · `stop` covers BOTH listeners. The old script only freed 43917 and never touched 44317 (the HTTPS one), so half
      an instance survived every stop.
    · `stop` ESCALATES. A wedged process ignores SIGTERM — that happened for real: the voice worker thread hung and
      the process had to be killed hard. TERM, wait, then KILL, and report which one it took.
    · `status` answers "is what I am running the code I just wrote?" by comparing the live build against git HEAD.
      Restarting and *believing* it restarted has cost hours here.

DESIGN NOTES
    · Standard library only. No psutil, no extra install step.
    · Ports are declared ONCE (`PORTS`). Adding a listener means adding a line here, not hunting through scripts.
    · Platform-specific bits (who owns a port, how to kill hard) are isolated in two functions with one interface
      each. Everything else is platform-neutral.
    · Never guesses by process name: `pkill -f "python -m server"` silently matched nothing on this very machine
      because the real command line differed. Ownership is resolved by PORT (the thing we actually care about) and
      by the pids we ourselves recorded.
"""
from __future__ import annotations

import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME = os.path.join(ROOT, ".meshkore", ".runtime")
PIDFILE = os.path.join(RUNTIME, "pids.json")
LOGDIR = os.path.join(ROOT, ".meshkore", "logs")

IS_WINDOWS = platform.system() == "Windows"

# The full local surface. `role` is what a human should read when something is still holding a port.
PORTS = [
    (43917, "app (HTTP — internal bridges talk to this one)"),
    (44317, "app (HTTPS — https://local.zaelar.com:44317)"),
    (7880, "livekit-server (voice signalling)"),
]
APP_PORT = 43917
HTTPS_PORT = 44317


# ── tiny helpers ──────────────────────────────────────────────────────────────────────────────────────────────────

def _say(msg: str) -> None:
    print(msg, flush=True)


def port_busy(port: int, host: str = "127.0.0.1") -> bool:
    """Is somebody listening? A plain TCP connect: no external tools, identical on every platform."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def pids_on_port(port: int) -> list[int]:
    """Who owns this port. The ONE place with platform-specific code — deliberately, so callers stay neutral."""
    try:
        if IS_WINDOWS:
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10).stdout
            found = set()
            for line in out.splitlines():
                parts = line.split()
                # PROTO  LOCAL            FOREIGN   STATE      PID
                if len(parts) >= 5 and parts[-2].upper() == "LISTENING" and parts[1].endswith(f":{port}"):
                    found.add(int(parts[-1]))
            return sorted(found)
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=10).stdout
        return sorted({int(x) for x in out.split() if x.strip().isdigit()})
    except Exception:
        return []


def kill_pid(pid: int, hard: bool = False) -> None:
    """Politely, then not. On Windows there is no SIGTERM, so the hard path is `taskkill /F`."""
    try:
        if hard and IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=15)
        elif hard:
            os.kill(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def load_pids() -> dict:
    try:
        with open(PIDFILE, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def save_pids(d: dict) -> None:
    os.makedirs(RUNTIME, exist_ok=True)
    try:
        with open(PIDFILE, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
    except Exception:
        pass


def live_build() -> str | None:
    """What the RUNNING instance says it is (`version.short()` via /api/status). None if it is not answering."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/api/status", timeout=4) as r:
            data = json.loads(r.read().decode("utf-8"))
        for item in data.get("items") or []:
            if item.get("key") == "version":
                return (item.get("extra") or {}).get("short") or item.get("detail")
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None
    return None


def git_head() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


# ── status ────────────────────────────────────────────────────────────────────────────────────────────────────────

def cmd_status() -> int:
    up = []
    for port, role in PORTS:
        busy = port_busy(port)
        owners = pids_on_port(port) if busy else []
        mark = "UP  " if busy else "down"
        who = f"  pid {','.join(str(p) for p in owners)}" if owners else ""
        _say(f"  {mark}  {port:<6} {role}{who}")
        if busy:
            up.append(port)

    build, head = live_build(), git_head()
    if build:
        _say(f"\n  build running : {build}")
        if head:
            # V2-074's restart proof: a build whose sha is not HEAD means the restart did NOT pick up your code.
            same = head in build
            _say(f"  git HEAD      : {head}   {'✓ match' if same else '✗ MISMATCH — the instance is NOT running HEAD'}")
    elif APP_PORT in up:
        _say("\n  the app port is open but /api/status did not answer — the instance may be wedged (try `stop`)")

    if not up:
        _say("\n  zaelar is not running.  Start it with:  make start   (or: python scripts/zaelar.py start)")
        return 1
    if APP_PORT in up:
        _say(f"\n  open:  https://local.zaelar.com:{HTTPS_PORT}/   ·   http://127.0.0.1:{APP_PORT}/")
    return 0


# ── stop ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def _stop_port(port: int, role: str, grace: float) -> bool:
    """Free one port. Returns True if it ended up free. TERM first, KILL only if it refuses to die."""
    if not port_busy(port):
        return True
    owners = pids_on_port(port)
    if not owners:
        _say(f"  {port}: busy but the owner could not be identified — leaving it alone")
        return False

    for pid in owners:
        kill_pid(pid, hard=False)
    deadline = time.time() + grace
    while time.time() < deadline:
        if not port_busy(port):
            _say(f"  {port}: stopped ({role})")
            return True
        time.sleep(0.3)

    # It ignored SIGTERM. This is not hypothetical: a hung voice-worker thread did exactly this.
    _say(f"  {port}: ignored the polite stop, forcing it")
    for pid in owners:
        kill_pid(pid, hard=True)
    deadline = time.time() + 5
    while time.time() < deadline:
        if not port_busy(port):
            _say(f"  {port}: stopped, forced ({role})")
            return True
        time.sleep(0.3)
    _say(f"  {port}: STILL BUSY — something else owns it")
    return False


def _unload_ollama() -> None:
    """Ask Ollama to drop the models it has resident. Local models pin GPU/RAM and drain the battery long after
    zaelar is gone, so stopping means stopping. A no-op when Ollama is not installed or nothing is loaded."""
    from shutil import which
    if not which("ollama"):
        return
    try:
        out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return
    names = [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip()]
    for name in names:
        try:
            subprocess.run(["ollama", "stop", name], capture_output=True, timeout=20)
            _say(f"  ollama: unloaded {name}")
        except Exception:
            pass


def cmd_stop(keep_livekit: bool = False, grace: float = 6.0) -> int:
    _say("stopping zaelar…")
    ok = True
    for port, role in PORTS:
        if keep_livekit and port == 7880:
            continue
        ok = _stop_port(port, role, grace) and ok

    # Children we launched ourselves that hold no port of their own (the livekit wrapper, mostly).
    rec = load_pids()
    for name, pid in list(rec.items()):
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        if keep_livekit and name == "livekit":
            continue
        kill_pid(pid, hard=False)
    save_pids({} if not keep_livekit else {k: v for k, v in rec.items() if k == "livekit"})

    # Only on a real stop: a restart is about to need them warm again.
    if not keep_livekit:
        _unload_ollama()

    _say("stopped." if ok else "stopped, with leftovers (see above).")
    return 0 if ok else 1


# ── start ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def _venv_python() -> str:
    """The interpreter that has zaelar's dependencies. Falls back to the current one (a venv-aware caller)."""
    cand = os.path.join(ROOT, ".venv", "Scripts" if IS_WINDOWS else "bin", "python.exe" if IS_WINDOWS else "python")
    return cand if os.path.exists(cand) else sys.executable


def _livekit_binary() -> str | None:
    from shutil import which
    return which("livekit-server") or which("livekit-server.exe")


def _spawn(cmd: list[str], logname: str, env: dict) -> int | None:
    os.makedirs(LOGDIR, exist_ok=True)
    log = open(os.path.join(LOGDIR, logname), "ab", buffering=0)
    kwargs: dict = {"cwd": ROOT, "stdout": log, "stderr": subprocess.STDOUT, "env": env}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True   # survives the shell that launched it
    try:
        return subprocess.Popen(cmd, **kwargs).pid
    except Exception as e:  # noqa: BLE001
        _say(f"  could not launch {' '.join(cmd[:2])}: {e}")
        return None


def cmd_start(wait: float = 180.0, brain: str = "nucleo") -> int:
    if port_busy(APP_PORT):
        build = live_build()
        if build:
            _say(f"zaelar is already running ({build}).")
            _say(f"  open:  https://local.zaelar.com:{HTTPS_PORT}/")
            _say("  to load new code:  make restart")
            return 0
        # Port taken but not answering: exactly the state that used to look like "it won't start".
        _say("port 43917 is taken but the app is not answering — a previous instance is wedged.")
        _say("  run `make stop` first (or `make restart`, which does it for you).")
        return 1

    env = dict(os.environ)
    env.setdefault("BRAIN", brain)
    py = _venv_python()

    lk = _livekit_binary()
    if not lk:
        _say("livekit-server is not installed — voice needs it.  Run:  make install-livekit")
        return 1
    rec = load_pids()
    if not port_busy(7880):
        _say("starting livekit-server…")
        pid = _spawn([lk, "--dev", "--bind", "127.0.0.1"], "livekit-dev.log", env)
        if pid:
            rec["livekit"] = pid
        # The app registers its embedded voice worker against this, so give it a moment to bind.
        deadline = time.time() + 20
        while time.time() < deadline and not port_busy(7880):
            time.sleep(0.3)
        if not port_busy(7880):
            _say("  livekit-server did not come up — see .meshkore/logs/livekit-dev.log")
            return 1
    else:
        _say("livekit-server already up, reusing it.")

    _say("starting zaelar…")
    pid = _spawn([py, "-m", "server"], "server.log", env)
    if not pid:
        return 1
    rec["app"] = pid
    save_pids(rec)

    deadline = time.time() + wait
    while time.time() < deadline:
        if live_build():
            break
        if port_busy(APP_PORT):
            time.sleep(0.5)
            continue
        time.sleep(0.5)
    build = live_build()
    if not build:
        _say(f"  zaelar did not answer within {int(wait)}s — see .meshkore/logs/server.log")
        return 1

    head = git_head()
    _say(f"\nzaelar is up  ({build})")
    if head and head not in build:
        _say(f"  ⚠ git HEAD is {head}: the instance is NOT running your latest commit")
    _say(f"  open:  https://local.zaelar.com:{HTTPS_PORT}/   ·   http://127.0.0.1:{APP_PORT}/")
    return 0


def cmd_restart() -> int:
    # livekit is left alone on purpose: it holds no zaelar state and restarting it forces every browser to
    # renegotiate. The app is what carries new code.
    cmd_stop(keep_livekit=True)
    time.sleep(1.0)
    return cmd_start()


USAGE = """usage: python scripts/zaelar.py {start|stop|restart|status}

  start     start the local instance (idempotent: says so if it is already up)
  stop      stop it — both listeners, escalating to a forced kill if it hangs
  restart   stop + start, reusing livekit-server (this is how you load new code)
  status    what is up, and whether the running build matches git HEAD
"""


def main(argv: list[str]) -> int:
    cmd = (argv[1] if len(argv) > 1 else "").strip().lower()
    if cmd in ("start", "up"):
        return cmd_start()
    if cmd in ("stop", "down"):
        return cmd_stop()
    if cmd == "restart":
        return cmd_restart()
    if cmd in ("status", "st"):
        return cmd_status()
    _say(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
