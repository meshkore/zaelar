#
# V2-366 — cross-talk guard, the musica side. Both musica's hidden audio player and the youtube widget's
# visible player report onStateChange over the SAME window. musica's handler used to accept ANY ended message,
# which was latent while the youtube widget never did the `listening` handshake — V2-366 wired it, so a VIDEO
# ending would have advanced the MUSIC queue. Verified by RENDERING (the handler binds at module import and
# `_ytEnded` only exists once syncYtPlayer built the hidden iframe — a source test cannot reach it).
#
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

_DATA = {
    "connected": False, "can_connect": False, "own_client_id_set": False, "default_available": False,
    "redirect_uri": "", "now_playing": None, "mode": "youtube",
    "yt": {"videoId": "AAAAAAAAAAA", "title": "Canción", "paused": False, "muted": False, "volume": 70,
           "cmd_seq": 1},
    "playlists": [], "recent": [], "counts": {}, "top": [], "view": {"kind": "home", "id": ""},
}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_an_ended_from_the_youtube_widget_does_not_advance_the_music_queue():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/widgets/musica/")
            page.set_content("<div id='w'></div>")
            page.evaluate(
                """async ([src, data]) => {
                     window.__calls = [];
                     const mod = await import(src);
                     mod.render(document.getElementById('w'), data,
                                {action: (n, p) => { window.__calls.push([n, p || {}]); }, running: true});
                   }""",
                [f"http://127.0.0.1:{port}/widgets/musica/widget.js", _DATA],
            )
            # the youtube WIDGET's player finishing a video: must NOT touch the music queue
            page.evaluate("m => window.postMessage(m, '*')",
                          json.dumps({"event": "onStateChange", "info": 0, "id": "hb-youtube"}))
            page.wait_for_timeout(50)
            assert ["ended", {}] not in page.evaluate("window.__calls")
            # musica's OWN hidden player finishing: the queue advances as always (V2-047 F4)
            page.evaluate("m => window.postMessage(m, '*')",
                          json.dumps({"event": "onStateChange", "info": 0, "id": "hb-musica"}))
            page.wait_for_timeout(50)
            assert ["ended", {}] in page.evaluate("window.__calls")
            browser.close()
    finally:
        srv.terminate()
