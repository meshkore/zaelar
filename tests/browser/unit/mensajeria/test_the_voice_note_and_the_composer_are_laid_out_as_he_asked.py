"""The voice-note bubble and the composer are laid out as he asked (RENDERED, desktop and 375 px, V2-819).

The operator approved three changes on 2026-10-27, in his words: «onda de audio arriba y metadatos debajo, adjuntar
al lado del texto en desktop, miniaturas de imágenes encima del input». So, measured on the painted card:
  · a voice note's waveform runs across the TOP of the bubble, as wide as the bubble and scrubbable; play, the
    duration and the date/time sit on one line BELOW it, and the bubble prints its time once;
  · the attach clip sits beside the text box, on the same row;
  · a picture he attached waits as a thumbnail ABOVE the box, before it is sent.
Screenshots land in the workspace's TMP/v2-814/ when that folder exists (never inside the repo).
"""
from __future__ import annotations

import io
import math
import pathlib
import socket
import struct
import subprocess
import sys
import wave

import pytest
from tests.waiting import port_listening

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_SHOTS = _ENGINE.parent / "TMP" / "v2-814"
_A = "34600000001@s.whatsapp.net"
_KEY = "c:whatsapp:" + _A
# 1x1 PNG.
_PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf"
                     "c0f01f0005000201a5f0b4a50000000049454e44ae426082")


def _wav(seconds=4.0, rate=8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 9))) for i in range(int(seconds * rate))))
    return buf.getvalue()


def _host(width):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  body{{margin:0;padding:8px;font-family:-apple-system,system-ui,sans-serif}}
  .hb-win{{background:#fff;border:1px solid #e3e8f0;border-radius:16px;padding:16px 12px;display:flex;
          flex-direction:column;width:{width}px;height:640px;box-sizing:border-box;overflow:hidden}}
  .hb-scroll{{flex:1 1 auto;min-height:0;overflow:auto}}
</style></head><body><div class="hb-win"><div class="hb-scroll"><div id="w"></div></div></div></body></html>"""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def _browser():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            b._hb_base = f"http://127.0.0.1:{port}"
            yield b
            b.close()
    finally:
        srv.terminate()


def _data():
    return {"platforms": {"whatsapp": {"status": "connected"}}, "items": [], "chats": [],
            "active_chat": {"platform": "whatsapp", "chatId": _A},
            "active_items": [
                {"platform": "whatsapp", "chatId": _A, "messageId": "W1", "from": "Marta", "dir": "in",
                 "body": "[ptt received]", "mediaType": "ptt", "ts": 1761500000,
                 "media": [{"url": "/widgets/mensajeria/asset/aud_in.wav", "type": "ptt"}]},
                {"platform": "whatsapp", "chatId": _A, "messageId": "W2", "from": "", "dir": "out",
                 "body": "[ptt received]", "mediaType": "ptt", "ts": 1761500100,
                 "media": [{"url": "/widgets/mensajeria/asset/aud_out.wav", "type": "ptt"}]}],
            "thread_meta": {"count": 2, "complete": True, "isGroup": False, "name": "Marta"},
            "muted_channels": [], "draft": None, "sent": [], "outbox": [],
            "drafts": {_KEY: {"key": _KEY, "text": "mira esto", "files": ["up_1_foto.png"],
                              "target": {"platform": "whatsapp", "chatId": _A}}}}


@pytest.fixture(params=[760, 375], ids=["desktop", "phone"])
def page(_browser, request):
    width = request.param
    p = _browser.new_page(viewport={"width": width + 16, "height": 700})
    wav = _wav()

    def _audio(route):
        """Served with byte ranges, as the asset route serves a file — a medium that cannot be ranged cannot seek."""
        rng = route.request.headers.get("range", "")
        start, _, end = rng.replace("bytes=", "").partition("-") if rng else ("0", "", "")
        a, b = int(start or 0), int(end) if end else len(wav) - 1
        route.fulfill(status=206 if rng else 200, body=wav[a:b + 1], content_type="audio/wav",
                      headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes {a}-{b}/{len(wav)}"})
    p.route("**/widgets/mensajeria/asset/aud_*", _audio)
    p.route("**/widgets/mensajeria/asset/up_*", lambda r: r.fulfill(status=200, body=_PNG, content_type="image/png"))
    p.goto(_browser._hb_base + "/widgets/mensajeria/")
    p.set_content(_host(width))
    p.evaluate("""async ([src, data]) => {
        const mod = await import(src);
        mod.render(document.getElementById('w'), data,
                   {action: () => Promise.resolve({ok: true}), top: () => {}, openConnector: () => {}, running: true});
      }""", [_browser._hb_base + "/widgets/mensajeria/widget.js", _data()])
    p._hb_width = width
    yield p
    if _SHOTS.is_dir():
        p.screenshot(path=str(_SHOTS / f"messaging-{'desktop' if width > 400 else 'phone'}.png"))
    p.close()


def _box(page, sel):
    return page.locator(sel).first.bounding_box()


def test_the_waveform_runs_across_the_top_and_the_meta_line_sits_below(page):
    for row in (".tbrow:not(.out)", ".tbrow.out"):
        bubble, wave_, meta = _box(page, f"{row} .tbubble"), _box(page, f"{row} .mawave"), _box(page, f"{row} .mameta")
        assert wave_["y"] + wave_["height"] <= meta["y"] + 1, (row, wave_, meta)
        assert wave_["width"] >= 0.8 * bubble["width"], ("as wide as the bubble", row, wave_, bubble)
        m = page.locator(f"{row} .mameta")
        assert m.locator(".mapbtn").count() == 1 and m.locator(".matime").count() == 1
        assert m.locator(".mawhen").inner_text().strip(), "the date/time is on the meta line"
        assert page.locator(f"{row} .tbwhen").count() == 0, "printed once, not twice"


def test_the_waveform_is_scrubbable(page):
    page.wait_for_function("""() => { const a = document.querySelector('.tbrow .maud');
                                      return a && isFinite(a.duration) && a.duration > 0; }""", timeout=10000)
    w = _box(page, ".tbrow .mawave")
    page.mouse.click(w["x"] + w["width"] * 0.5, w["y"] + w["height"] / 2)
    t = page.evaluate("() => document.querySelector('.tbrow .maud').currentTime")
    assert 1.5 <= t <= 2.5, t
    assert page.locator(".tbrow").first.locator(".mabar.played").count() > 0, "the bars show where he is"


def test_the_clip_sits_beside_the_text_box(page):
    clip, box = _box(page, ".compose .attbtn"), _box(page, ".compose .composebox")
    assert clip["x"] + clip["width"] <= box["x"] + 1, (clip, box)
    assert clip["y"] < box["y"] + box["height"] and clip["y"] + clip["height"] > box["y"], "on the same row"


def test_an_attached_picture_waits_as_a_thumbnail_above_the_box(page):
    page.wait_for_function("() => { const i = document.querySelector('.compose .attthumb img');"
                           " return i && i.complete && i.naturalWidth > 0; }", timeout=5000)
    thumb, box = _box(page, ".compose .attthumb"), _box(page, ".compose .composebox")
    assert thumb["y"] + thumb["height"] <= box["y"] + 1, (thumb, box)
    assert thumb["width"] >= 60 and thumb["height"] >= 60, thumb


def test_nothing_spills_sideways(page):
    over = page.evaluate("""() => Array.from(document.querySelectorAll('.compose, .thread > .tl, .tbubble'))
        .filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.className)""")
    assert not over, over
