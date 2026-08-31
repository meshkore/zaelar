"""V2-464 — RECORDING a round: what the user would have seen, on video and hands-free.

The operator requested it with the exact analogy (2026-08-28): a screen viewer while the case runs
in the background — chat open to read the conversation, widgets placed “nice and neatly aligned” like
macOS/Windows window snapping — and the result saved as a silent video, linked from the case
report alongside the session and its flows. Direct material for a showcase.

HOW. Playwright records video natively (`record_video_dir` in the context): a headless Chromium at
1920×1080 loads the stage with `?showcase=1` — which opens the docked chat and automatically arranges the grid on each
opening (V2-464 in `sse.js`/`ChatWall.js`/`desktop.js`) — and stays WATCHING while the runner drives the
round through the probe channel. The video is only materialized when the context is CLOSED, so the viewer runs in
a SUBPROCESS with an explicit stdin stop protocol: killing it with signals would lose the entire file,
which is the most expensive possible failure mode here (the round has already run and been paid for).

Fail-soft end to end: a recording that does not start NEVER takes down the measurement — the video is a mirror of
the round, not part of it.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from . import config

VIDEO_DIR = config.RUNS_DIR / "videos"

# The viewer as SUBPROCESS TEXT rather than a function: Playwright sync cannot coexist with an
# asyncio loop that is already running, and the runner has one. A separate process shares neither loop nor GIL with the round.
_WATCHER_SRC = r'''
import json, sys
from playwright.sync_api import sync_playwright

url, out_dir = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                              record_video_dir=out_dir,
                              record_video_size={"width": 1920, "height": 1080})
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    print("READY", flush=True)
    # Wait for the stop command on stdin. EOF counts as a command: if the runner dies, this is not left orphaned.
    try:
        sys.stdin.readline()
    except Exception:
        pass
    video = page.video
    ctx.close()      # ← aquí se materializa el .webm
    browser.close()
    try:
        print("VIDEO " + json.dumps(video.path()), flush=True)
    except Exception:
        print("VIDEO null", flush=True)
'''


class Recorder:
    """A viewer for each round. `start()` waits for the page to load; `stop(name)` closes it, waits
    for the flush, and renames the .webm to a name that says WHICH round it is."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.proc: subprocess.Popen | None = None
        self.error = ""

    def start(self, timeout_s: float = 60.0) -> bool:
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        url = self.base_url.rstrip("/") + "/?showcase=1"
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-c", _WATCHER_SRC, url, str(VIDEO_DIR)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True)
        except Exception as e:  # noqa: BLE001
            self.error = f"no arrancó: {e}"
            return False
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                self.error = f"murió al arrancar: {(self.proc.stderr.read() or '')[-300:]}"
                return False
            line = self.proc.stdout.readline()
            if line.strip() == "READY":
                return True
        self.error = "no llegó a READY"
        self.stop("")
        return False

    def stop(self, name: str) -> str:
        """Cierra el espectador y devuelve la ruta final del vídeo ('' si no hubo)."""
        if not self.proc:
            return ""
        import json as _json
        path = ""
        try:
            if self.proc.poll() is None:
                try:
                    self.proc.stdin.write("stop\n")
                    self.proc.stdin.flush()
                except Exception:  # noqa: BLE001
                    pass
            out, _ = self.proc.communicate(timeout=60)
            for line in (out or "").splitlines():
                if line.startswith("VIDEO ") and line != "VIDEO null":
                    try:
                        path = _json.loads(line[6:])
                    except Exception:  # noqa: BLE001
                        path = ""
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.error = "no cerró a tiempo: el vídeo puede haberse perdido"
        finally:
            self.proc = None
        if path and name:
            # The name says WHICH round it is — Playwright's random hash tells nobody.
            dst = VIDEO_DIR / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.webm"
            try:
                Path(path).rename(dst)
                return str(dst)
            except Exception:  # noqa: BLE001
                return str(path)
        return str(path or "")
