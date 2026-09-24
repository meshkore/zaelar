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

from server import feedback_api as fb

ENGINE = pathlib.Path(__file__).resolve().parents[4]


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
    assert "thumbs_down" in fb._KINDS


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
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError:
            time.sleep(0.1)
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
            pg.route("**/api/feedback/thumbs_down", _thumb)
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
            pg.wait_for_selector(".fw-thumb", timeout=5000)
            pg._errors = errors
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _state(pg):
    return pg.evaluate("""() => { const b = document.querySelector('.fw-thumb'), t = document.querySelector('.fw-thumb-toast');
        const tr = t.getBoundingClientRect(), br = b.getBoundingClientRect(), lr = document.querySelector('.fw-launcher').getBoundingClientRect();
        return {btn: b.className, bg: getComputedStyle(b).backgroundColor, text: t.textContent,
                show: t.classList.contains('show'), op: parseFloat(getComputedStyle(t).opacity),
                toastRight: tr.right, btnLeft: br.left, btnRight: br.right, launcherLeft: lr.left}; }""")


def test_it_sits_beside_the_launcher_in_the_same_colour(widget):
    st = _state(widget)
    launcher_bg = widget.evaluate("() => getComputedStyle(document.querySelector('.fw-launcher')).backgroundColor")
    assert st["bg"] == launcher_bg, f"«quizás en este color»: thumb {st['bg']} vs launcher {launcher_bg}"
    assert st["btnRight"] <= st["launcherLeft"], "the thumb overlaps the launcher"


def test_one_click_shows_thanks_to_the_LEFT_then_fades_and_the_icon_comes_back(widget):
    idle_bg = _state(widget)["bg"]
    widget._thumb_calls.clear()
    widget._thumb_status["body"] = {"ok": True, "id": "fb1"}
    widget.click(".fw-thumb")
    widget.wait_for_function("() => document.querySelector('.fw-thumb-toast').classList.contains('show')", timeout=3000)
    widget.wait_for_timeout(700)                             # past the fade-IN
    on = _state(widget)
    assert "Gracias" in on["text"] and "error" in on["text"], f"the toast says {on['text']!r}"
    assert on["op"] > 0.95, "the message is not readable while it is meant to be"
    assert on["toastRight"] <= on["btnLeft"], "the message is not to the LEFT of the thumb"
    assert "fw-thumb-done" in on["btn"] and on["bg"] != idle_bg, "the icon did not change colour while marked"
    widget.click(".fw-thumb")                               # a second click while it is showing…
    widget.wait_for_timeout(3200)                            # …then past show + fade
    off = _state(widget)
    assert not off["show"] and off["op"] < 0.05, "the message did not fade away"
    assert off["text"] == "", "the text lingered after the fade"
    assert "fw-thumb-idle" in off["btn"] and off["bg"] == idle_bg, "the icon did not return to its colour"
    assert len(widget._thumb_calls) == 1, f"one click, one mark — got {len(widget._thumb_calls)} requests"


def test_a_failed_mark_says_so_instead_of_thanking(widget):
    widget._thumb_status["body"] = {"ok": False, "error": "send_failed"}
    widget.click(".fw-thumb")
    widget.wait_for_function("() => document.querySelector('.fw-thumb-toast').classList.contains('show')", timeout=3000)
    st = _state(widget)
    widget.wait_for_timeout(3700)
    assert "Gracias" not in st["text"] and st["text"], f"a failed mark thanked him: {st['text']!r}"
    assert not widget._errors, widget._errors
