"""V2-616 F5 — the custom audio player genuinely PLAYS, PAUSES and SEEKS, not just renders.

The operator: he could play a voice note with the old native `<audio controls>` but could not drag to a point
in it ("no puedo avanzar hasta cierto punto como hago en WhatsApp"). This is the behavioral half — a fixture
plays a REAL (tiny, silent, one-second) WAV through the actual `<audio>` element and drives the pointer
events by hand, because a source-level read cannot tell "the click handler exists" from "the click handler
moves the play head".
"""
from __future__ import annotations

import asyncio
import io
import os
import wave

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "mensajeria", "widget.js")


def _one_second_silent_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)   # 8000 frames at 8kHz = exactly 1.0s
    return buf.getvalue()


_WAV = _one_second_silent_wav()

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#0a1017}#host{width:520px}
</style></head><body><div id="host"></div></body></html>"""

_ITEM = {"n": 1, "platform": "whatsapp", "from": "JOSE VICENTE", "dir": "in", "chatId": "111",
          "messageId": "m1", "body": "[ptt received]", "ts": 1, "urgencia": "media", "dirigido_a_mi": True,
          "mediaType": "ptt", "media": [{"url": "/widgets/mensajeria/asset/aud_x.wav", "type": "ptt", "name": "aud_x.wav"}]}
_DATA = {
    "platforms": {"whatsapp": {"status": "connected"}, "telegram": {"status": "off"}, "email": {"status": "off"}},
    "updated": "10:00:00", "items": [], "count": 0, "chats": [],
    "active_chat": {"platform": "whatsapp", "chatId": "111"}, "active_items": [_ITEM],
    "thread_meta": {"isGroup": False, "complete": True},
    "muted_channels": [], "notify_policy": {}, "connect_focus": None, "view": None,
}


def _run():
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
            pg = await b.new_page(viewport={"width": 560, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            async def _page(route):
                await route.fulfill(status=200, content_type="text/html", body=_HTML)
            await pg.route("http://zaelar.test/", _page)

            # The real asset route (widgets/server_api.py) is Starlette's FileResponse, which answers a
            # `Range:` request with 206 Partial Content on its own — that is what makes Chromium mark a clip
            # SEEKABLE at all (measured: without it `audio.seekable` stays `[[0,0]]` forever, even fully
            # downloaded, and every `currentTime =` assignment is silently ignored). A route mock that just
            # echoes the whole body on every request tests a server this widget will never actually be
            # served by — so this one answers Range the same way FileResponse does.
            async def _asset(route, request):
                headers = request.headers
                rng = headers.get("range")
                if not rng:
                    await route.fulfill(status=200, content_type="audio/wav", body=_WAV,
                                        headers={"Accept-Ranges": "bytes"})
                    return
                start_s, _, end_s = rng.replace("bytes=", "").partition("-")
                start = int(start_s or 0)
                end = int(end_s) if end_s else len(_WAV) - 1
                chunk = _WAV[start:end + 1]
                await route.fulfill(status=206, content_type="audio/wav", body=chunk, headers={
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes {start}-{end}/{len(_WAV)}",
                })
            await pg.route("http://zaelar.test/widgets/mensajeria/asset/*", _asset)
            await pg.goto("http://zaelar.test/")
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(content=src.replace("export function render", "window.render = function render"))
            await pg.evaluate(
                "d => window.render(document.getElementById('host'), d, "
                "{action: async () => ({}), top: () => {}})", _DATA)
            # Duration only becomes known once metadata loads — wait for the real event rather than a fixed
            # timeout, so this test is not a coin flip against how fast Chromium happens to load a local WAV.
            await pg.evaluate(
                "() => new Promise(res => { const a = document.querySelector('audio.maud'); "
                "if (a.readyState >= 1) return res(); a.addEventListener('loadedmetadata', res, {once:true}); })")

            before = await pg.evaluate("() => document.querySelector('audio.maud').currentTime")
            playing_before = await pg.evaluate("() => !document.querySelector('audio.maud').paused")

            await pg.click(".mapbtn")
            await pg.wait_for_timeout(60)
            playing_after_click = await pg.evaluate("() => !document.querySelector('audio.maud').paused")

            wave_box = await pg.locator(".mawave").bounding_box()
            # Click at 75% across the wave — a real pointer gesture, real hit-testing.
            await pg.mouse.click(wave_box["x"] + wave_box["width"] * 0.75, wave_box["y"] + wave_box["height"] / 2)
            await pg.wait_for_timeout(60)
            after_seek = await pg.evaluate("() => document.querySelector('audio.maud').currentTime")
            duration = await pg.evaluate("() => document.querySelector('audio.maud').duration")
            played_bars = await pg.evaluate("() => document.querySelectorAll('.mabar.played').length")
            time_text = await pg.evaluate("() => document.querySelector('.matime').textContent")

            await b.close()
            return {
                "errors": errors, "before": before, "playing_before": playing_before,
                "playing_after_click": playing_after_click, "after_seek": after_seek, "duration": duration,
                "played_bars": played_bars, "time_text": time_text,
            }
    return asyncio.run(go())


@pytest.fixture(scope="module")
def result(playwright_available):
    return _run()


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def test_the_clip_never_autoplays(result):
    assert result["errors"] == [], result["errors"]
    assert result["playing_before"] is False, "a received voice note must not play itself"
    assert result["before"] == 0


def test_the_play_button_actually_starts_playback(result):
    assert result["playing_after_click"] is True


def test_dragging_the_wave_actually_seeks(result):
    """The operator's exact complaint: he could play it but not jump to a point in it."""
    d = result["duration"]
    assert d and d > 0.9, f"duration must be known (real 1s clip): {d}"
    # 75% across a ~1s clip: allow generous slack for click-vs-drag rounding, but it must have MOVED, and
    # moved toward the far end — not stayed at 0 (the old native-controls-only behavior this replaces).
    assert result["after_seek"] > d * 0.5, result["after_seek"]


def test_the_waveform_and_time_label_reflect_the_seek(result):
    assert result["played_bars"] > 0, "bars up to the seek point must be marked played"
    assert "/" in result["time_text"], result["time_text"]
