"""V2-760 — the thumbs-down marks «this went wrong» in ONE click, and the report is the session itself.

The operator, 2026-09-24:

    «cada vez que la gente detecte un fallo, les pediré que clique en este pulgar hacia abajo… en el registro
    de feedback va a salir… en este momento el usuario había pedido alguna cosa y el agente personal no lo ha
    hecho bien, revisarlo… así el usuario no tiene que estar rellenando un mail o un texto de descripción…
    quedará vinculado por ID de agente personal en nuestro backoffice, con los datos de observabilidad… y
    cuando se clique saldrá un mensaje hacia la izquierda… dura dos o tres segundos… y desaparece en un
    fundido… y el icono vuelve al color original.» — and: «tendrá que funcionar tanto en agentes locales como
    en la nube».

Building it exposed a defect under EVERY feedback report: `flows.events(limit=200)` returns the FIRST 200
events of a session. Measured on his session `ee542271` (621 events, 12:26:54-12:29:12): the evidence any
report carried was 12:26:54-12:27:33 — the first 39 seconds. A report sent at the end never contained the
failure it described, and for a button whose whole point is «from here backwards», that is fatal.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from tests.waiting import until_sync

from server import feedback_api as fb

ENGINE = pathlib.Path(__file__).resolve().parents[4]
_ES = json.loads((ENGINE / "i18n/bundles/es.json").read_text(encoding="utf-8"))



def _listening(port: int) -> bool:
    import socket as _s
    try:
        _s.create_connection(("127.0.0.1", port), 0.2).close()
        return True
    except OSError:
        return False

def _tr(label, text, trace=""):
    return {"kind": "transcript", "label": label,
            "payload": json.dumps({"kind": "transcript", "label": label, "text": text, "trace": trace})}


_SESSION = [
    _tr("🗣", "Y puedes poner el widget en pantalla completa?", "T5·a1"),
    _tr("zaelar", "el visor a pantalla completa."),
    {"kind": "widget", "label": "maximize", "payload": "{}"},
    _tr("🗣", "Y sal de pantalla completa.", "T6·b2"),
    _tr("zaelar", "Ya está, fuera de pantalla completa."),
]


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {"id": "fb1", "status": "received"}

    def json(self):
        return self._payload


def _capture(monkeypatch, *, cloud: bool, sid="s-live", events=None, status=200):
    sent: list[tuple[str, dict, dict]] = []

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            sent.append((url, json or {}, headers or {}))
            return _Resp(status)

    monkeypatch.setattr(fb.httpx, "AsyncClient", lambda **k: _Client())
    from nucleo import cloud_account
    from observability import identity, flows
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: cloud)
    monkeypatch.setattr(fb, "_control_plane_url", lambda: "https://cp.example")
    monkeypatch.setattr(fb, "_service_token", lambda: "svc-token")
    monkeypatch.setattr(identity, "session_info", lambda: {"session_id": sid})
    monkeypatch.setattr(identity, "user_id", lambda: "4cd1b39d-d879-4137-90d1-fea5c7e9e2d4")
    monkeypatch.setattr(flows, "session", lambda s: {"session_id": s})
    monkeypatch.setattr(flows, "events", lambda session_id, limit, tail=False: list(events or _SESSION))
    return sent


def _click():
    return asyncio.run(fb.thumbs_down())


# ── A · WHAT THE REPORT CARRIES ──────────────────────────────────────────────────────────────────────────────
def test_the_report_is_a_thumbs_down_with_no_text_from_him(monkeypatch):
    sent = _capture(monkeypatch, cloud=False)
    out = _click()
    assert out.get("ok") is True, out
    body = sent[0][1]
    assert body["type"] == "thumbs_down", body
    assert "revisar" in body["message"].lower(), "the inbox row must say what to do with it"


def test_the_message_quotes_his_last_request_and_the_answer_he_got(monkeypatch):
    """The row reads as something before anyone opens the evidence."""
    sent = _capture(monkeypatch, cloud=False)
    _click()
    msg = sent[0][1]["message"]
    assert "Y sal de pantalla completa." in msg, msg
    assert "Ya está, fuera de pantalla completa." in msg, msg
    assert "pon" not in msg.split("Última petición")[1][:20].lower(), "it quoted an OLDER request, not the last"


def test_the_evidence_carries_a_marker_of_WHERE_he_clicked(monkeypatch):
    """«de ahí para atrás la gente tiene que leer la observabilidad» — the marker is that «ahí»."""
    sent = _capture(monkeypatch, cloud=False, sid="ee542271")
    _click()
    ev = sent[0][1].get("session_evidence") or {}
    m = ev.get("marker") or {}
    assert m.get("session_id") == "ee542271", m
    assert m.get("trace") == "T6·b2", f"the marker does not point at the turn he flagged: {m}"
    assert m.get("at"), "no time on the marker"
    assert ev.get("events"), "the session itself did not travel"


def test_with_no_voice_session_it_marks_the_latest_one(monkeypatch):
    """From the written chat there may be no live voice session — the click still has to land somewhere."""
    from observability import flows
    sent = _capture(monkeypatch, cloud=False, sid=None)
    monkeypatch.setattr(flows, "sessions", lambda limit=30, user_id="": [{"session_id": "latest-1"}])
    _click()
    assert (sent[0][1].get("session_evidence") or {}).get("marker", {}).get("session_id") == "latest-1"


def test_an_empty_session_still_sends_the_mark(monkeypatch):
    """Nothing to quote is not a reason to lose the click."""
    sent = _capture(monkeypatch, cloud=False, events=[{"kind": "widget", "label": "x", "payload": "{}"}])
    out = _click()
    assert out.get("ok") is True and sent[0][1]["type"] == "thumbs_down"


# ── B · LOCAL AND CLOUD, THE SAME DOOR AS THE FORM ───────────────────────────────────────────────────────────
def test_a_cloud_engine_sends_it_with_its_workload_credential(monkeypatch):
    sent = _capture(monkeypatch, cloud=True)
    _click()
    url, body, headers = sent[0]
    assert url == "https://cp.example/feedback", url
    assert headers.get("X-Service-Token") == "svc-token"
    assert "install_id" not in body, "the cloud route derives identity from the credential, never the body"


def test_a_self_hosted_engine_sends_it_anonymously_with_its_install_id(monkeypatch):
    sent = _capture(monkeypatch, cloud=False)
    _click()
    url, body, _ = sent[0]
    assert url.endswith("/feedback/anonymous"), url
    assert body.get("install_id") == "4cd1b39d-d879-4137-90d1-fea5c7e9e2d4"


def test_a_refused_send_says_so(monkeypatch):
    _capture(monkeypatch, cloud=False, status=429)
    out = _click()
    assert out.get("ok") is False, "a rate-limited mark came back as a success — the toast would lie"


def test_the_kind_is_one_the_engine_accepts():
    assert "thumbs_down" in fb._KINDS and "thumbs_up" in fb._KINDS


def test_the_thumbs_up_is_the_same_mark_saying_it_went_WELL(monkeypatch):
    """V2-766 — «la mano hacia arriba es un quick feedback… de que todo está yendo bien». Same evidence and
    marker, its own kind, and a row that reads as good news."""
    sent = _capture(monkeypatch, cloud=False, sid="ok-1")
    out = asyncio.run(fb.thumbs_up())
    assert out.get("ok") is True, out
    body = sent[0][1]
    assert body["type"] == "thumbs_up", body
    assert "bien" in body["message"] and "revisar" not in body["message"].lower(), body["message"]
    assert (body.get("session_evidence") or {}).get("marker", {}).get("session_id") == "ok-1"


# ── C · THE EVIDENCE IS THE END OF THE SESSION, NOT ITS BEGINNING ────────────────────────────────────────────
def test_a_tail_read_asks_for_the_newest_and_returns_them_in_order(monkeypatch):
    from observability import flows
    seen = {}

    def _rows(sql, args):
        seen["sql"] = sql
        return [{"id": 3}, {"id": 2}, {"id": 1}]           # what DESC returns
    monkeypatch.setattr(flows, "_rows", _rows)
    out = flows.events(session_id="s", limit=3, tail=True)
    assert "ORDER BY id DESC" in seen["sql"], seen["sql"]
    assert [r["id"] for r in out] == [1, 2, 3], "a tail read must still come back oldest-first"


def test_the_default_read_is_unchanged(monkeypatch):
    """The cursor readers (`since_id`, the backoffice's live follow) walk forward and must keep doing so."""
    from observability import flows
    seen = {}
    monkeypatch.setattr(flows, "_rows", lambda sql, args: seen.update(sql=sql) or [{"id": 1}, {"id": 2}])
    assert [r["id"] for r in flows.events(session_id="s", limit=2)] == [1, 2]
    assert "ORDER BY id ASC" in seen["sql"]


# ── D · THE BUTTON, RENDERED ─────────────────────────────────────────────────────────────────────────────────
pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def widget():
    import socket
    import subprocess
    import sys
    import time

    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    # The shape `/api/i18n/bundle/<code>` really answers: {strings: {...}}. A bare bundle loads nothing and
    # every string comes back as its raw key.
    es = json.dumps({"strings": json.loads((ENGINE / "i18n/bundles/es.json").read_text(encoding="utf-8"))})
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 1280, "height": 800})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg._thumb_status = {"code": 200, "body": {"ok": True, "id": "fb1"}}
            pg._thumb_calls = []

            def _thumb(route):
                pg._thumb_calls.append(1)
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps(pg._thumb_status["body"]))
            def _thumb_any(route):
                pg._thumb_urls.append(route.request.url.rsplit("/", 1)[-1])
                _thumb(route)
            pg._thumb_urls = []
            pg.route("**/api/feedback/thumbs_*", _thumb_any)
            pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json", body=es))
            pg.route("**/api/i18n/state", lambda r: r.fulfill(status=200, content_type="application/json",
                                                               body=json.dumps({"lang": "es", "language": "es"})))
            pg.route("**/api/feedback", lambda r: r.fulfill(status=200, content_type="application/json",
                                                            body=json.dumps({"ok": True, "items": []})))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.evaluate("""async (port) => {
                const css = document.createElement('link'); css.rel = 'stylesheet';
                css.href = `http://127.0.0.1:${port}/frontend/app/core/palette.css`; document.head.append(css);
                const css2 = document.createElement('link'); css2.rel = 'stylesheet';
                css2.href = `http://127.0.0.1:${port}/frontend/app/styles.css`; document.head.append(css2);
                await new Promise(r => setTimeout(r, 300));
                const i18n = await import(`http://127.0.0.1:${port}/frontend/app/core/i18n.js?v=1`);
                await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');
                const m = await import(`http://127.0.0.1:${port}/frontend/app/components/FeedbackWidget.js?v=1`);
                document.body.append(m.FeedbackWidget());
            }""", port)
            pg.wait_for_selector(".fw-launcher", timeout=5000)
            pg._errors = errors
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _open(pg):
    pg.evaluate("async () => { const s = await import('/frontend/app/core/store.js?v=2'); s.setFeedbackOpen(true); }")
    pg.wait_for_selector(".fw-panel.open .fw-row", timeout=3000)


def _footer(pg):
    return pg.evaluate("""() => {
        const row = document.querySelector('.fw-row'), rr = row.getBoundingClientRect();
        const box = sel => { const e = row.querySelector(sel); if (!e) return null;
                             const r = e.getBoundingClientRect(); return {l: r.left, r: r.right, w: r.width}; };
        const panel = document.querySelector('.fw-panel');
        return {up: box('.fw-hand.up'), down: box('.fw-hand.down'), mic: box('.fw-mic'), clip: box('.fw-clip'),
                send: box('.fw-send'), sendText: row.querySelector('.fw-send').textContent.trim(),
                rowL: rr.left, rowR: rr.right, rowW: rr.width, panelH: panel.getBoundingClientRect().height,
                floating: !!document.querySelector('.fw-quick, .fw-thumb')}; }""")


def _screen(pg):
    return pg.evaluate("""() => { const q = document.querySelector('.fw-quickdone');
        const vis = sel => { const e = document.querySelector(sel); return !!e && getComputedStyle(e).display !== 'none'; };
        return {quick: !!q, text: q ? q.querySelector('.fw-quickdone-text').textContent : '',
                btn: q ? q.querySelector('.fw-quickdone-btn').textContent : '',
                form: vis('.fw-panel .fw-new'), open: document.querySelector('.fw-panel').classList.contains('open')}; }""")


def test_the_floating_thumb_is_gone(widget):
    """«Vamos a quitar el signo ese del pulgar hacia abajo… no me gusta. Mételo en el feedback.»"""
    assert not _footer(widget)["floating"], "the floating thumb over the launcher is still there"


def test_the_footer_is_hands_left_then_mic_clip_and_a_compact_send_right(widget):
    """«…el botón comprimido hacia la derecha, solo con su texto, enviar… los dos iconitos pegados a ese botón y
    a la izquierda del todo… una mano hacia arriba y otra hacia abajo». And the form a bit taller."""
    _open(widget)
    f = _footer(widget)
    assert f["up"] and f["down"], f"the two hands are not in the footer: {f}"
    assert f["up"]["l"] - f["rowL"] <= 2 and f["up"]["r"] <= f["down"]["l"], f"the hands are not far left: {f}"
    assert f["down"]["r"] < f["mic"]["l"] < f["clip"]["l"] < f["send"]["l"], f"footer order is wrong: {f}"
    assert f["rowR"] - f["send"]["r"] <= 2, "send is not at the right edge"
    assert f["clip"]["r"] <= f["send"]["l"] and f["send"]["l"] - f["clip"]["r"] <= 12, "the icons are not beside send"
    assert f["send"]["w"] < f["rowW"] * 0.4, f"send is not compact: {f['send']['w']} of {f['rowW']}"
    assert f["sendText"] == _ES["feedback.send"] == "Enviar", f["sendText"]
    assert f["panelH"] >= 520, f"the form did not grow: {f['panelH']}"


@pytest.mark.parametrize("hand,key,url", [("up", "feedback.thumbsUpThanks", "thumbs_up"),
                                          ("down", "feedback.thumbsDownThanks", "thumbs_down")])
def test_a_hand_turns_the_panel_into_its_thanks_and_close_closes_it(widget, hand, key, url):
    """«Cuando se dé a ese botón, se cambia toda la pantalla y se pone gracias… y un botón de cerrar, y se
    cierra el formulario de feedback.»"""
    _open(widget)
    widget._thumb_status["body"] = {"ok": True, "id": "fb1"}
    widget._thumb_urls.clear()
    widget.click(f".fw-hand.{hand}")
    widget.wait_for_selector(".fw-quickdone", timeout=3000)
    st = _screen(widget)
    assert st["text"] == _ES[key], st
    assert not st["form"], "the form is still showing under the thanks"
    assert st["btn"] == _ES["feedback.close"], st
    assert widget._thumb_urls == [url], f"one click, one mark to the right door — got {widget._thumb_urls}"
    widget.click(".fw-quickdone-btn")
    widget.wait_for_timeout(150)
    after = _screen(widget)
    assert not after["open"] and not after["quick"], f"close did not close the form: {after}"


def test_a_failed_mark_says_so_and_goes_back_to_the_form(widget):
    _open(widget)
    widget._thumb_status["body"] = {"ok": False, "error": "send_failed"}
    widget.click(".fw-hand.down")
    widget.wait_for_selector(".fw-quickdone", timeout=3000)
    st = _screen(widget)
    assert st["text"] == _ES["feedback.quickFailed"] and st["btn"] == _ES["feedback.back"], st
    widget.click(".fw-quickdone-btn")
    widget.wait_for_timeout(150)
    back = _screen(widget)
    assert back["open"] and back["form"] and not back["quick"], f"«Volver» did not bring the form back: {back}"
    assert not widget._errors, widget._errors
