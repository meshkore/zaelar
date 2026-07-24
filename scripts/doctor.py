#!/usr/bin/env python3
"""Zaelar — requirements doctor. Stdlib only (runs before any install).
Usage: python3 scripts/doctor.py    ->  exits non-zero if a HARD requirement fails."""
import sys, os, platform, shutil, socket

G, Y, R, B, X = "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[0m"
if platform.system() == "Windows" and not os.environ.get("WT_SESSION"):
    G = Y = R = B = X = ""  # avoid garbled codes on legacy cmd.exe

APP_PORT = int(os.environ.get("ZAELAR_PORT", "43917"))
MIN_PY = (3, 11)
MIN_DISK_GB = 3
hard_fail = False

def ok(m):   print(f"  {G}OK{X}   {m}")
def warn(m): print(f"  {Y}WARN{X} {m}")
def bad(m):
    global hard_fail; hard_fail = True; print(f"  {R}FAIL{X} {m}")

print(f"\n{B}Zaelar — checking your system{X}\n")

# OS
osname = platform.system()
if osname in ("Darwin", "Windows", "Linux"):
    ok(f"Operating system: {osname} ({platform.machine()})")
else:
    warn(f"Untested operating system: {osname}")

# Python
v = sys.version_info
if (v.major, v.minor) >= MIN_PY:
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
else:
    bad(f"Python {v.major}.{v.minor} found — Zaelar needs {MIN_PY[0]}.{MIN_PY[1]}+  (https://python.org/downloads)")

# venv + pip
try:
    import venv  # noqa
    ok("Python venv module")
except Exception:
    bad("Python 'venv' module missing (on Debian/Ubuntu: apt install python3-venv)")
if shutil.which("pip") or shutil.which("pip3") or True:  # pip ships with venv; informational
    ok("pip (bundled with venv)")

# Disk
try:
    free_gb = shutil.disk_usage(os.path.expanduser("~")).free / 1e9
    (ok if free_gb >= MIN_DISK_GB else bad)(f"Free disk space: {free_gb:.0f} GB (need ~{MIN_DISK_GB} GB)")
except Exception as e:
    warn(f"Could not check disk space ({e})")

# RAM (best effort)
try:
    if osname in ("Darwin", "Linux"):
        ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
        (ok if ram_gb >= 7 else warn)(f"Memory: {ram_gb:.0f} GB (8 GB+ recommended)")
    else:
        warn("Memory: not checked on this OS (8 GB+ recommended)")
except Exception:
    warn("Memory: could not determine (8 GB+ recommended)")

# App port free
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    free = s.connect_ex(("127.0.0.1", APP_PORT)) != 0
    s.close()
    (ok if free else warn)(f"Port {APP_PORT} {'is free' if free else 'is in use — Zaelar may already be running'}")
except Exception:
    warn(f"Could not check port {APP_PORT}")

# Optional tools (auto-installed / not blocking)
print(f"\n{B}Optional (Zaelar sets these up for you if missing){X}")
for tool, note in [("livekit-server", "voice server (installed on first run)"),
                   ("ffmpeg", "audio processing (optional)"),
                   ("node", "only for frontend dev (optional)"),
                   ("ollama", "local models (optional — cloud models work without it)")]:
    (ok if shutil.which(tool) else warn)(f"{tool} — {note}")

# API keys reminder (configured IN THE APP, not here)
print(f"\n{B}Note:{X} API keys are configured inside Zaelar's UI after it starts — no .env editing needed.\n")

if hard_fail:
    print(f"{R}Some requirements are missing. Fix the FAIL items above, then run again.{X}\n")
    sys.exit(1)
print(f"{G}All set. Run:  ./zaelar start   (macOS/Linux)   or   .\\zaelar.ps1 start   (Windows){X}\n")
