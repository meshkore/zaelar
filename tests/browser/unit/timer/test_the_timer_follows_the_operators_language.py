#
# V2-613 — timer is the pilot widget for `ctx.t`: RENDERED, because the whole point is what actually reaches the
# DOM for a given ctx, not what the source merely calls. Same harness as musica's V2-366 test.
#
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

_EN = {
    "widgets.timer.label_default": "TIMER", "widgets.timer.finished": "READY!",
    "widgets.timer.finished_with_label": "⏰ {label} done", "widgets.timer.finished_generic": "⏰ Time's up!",
    "widgets.timer.paused": "⏸ Paused", "widgets.timer.empty": "Ask zaelar to set a time",
    "widgets.timer.close": "✕ Close", "widgets.timer.pause": "⏸ Pause", "widgets.timer.resume": "▶ Resume",
    "widgets.timer.cancel": "✕ Cancel",
}
_ES = {
    "widgets.timer.label_default": "TEMPORIZADOR", "widgets.timer.finished": "¡LISTO!",
    "widgets.timer.finished_with_label": "⏰ {label} cumplido", "widgets.timer.finished_generic": "⏰ ¡Tiempo cumplido!",
    "widgets.timer.paused": "⏸ Pausado", "widgets.timer.empty": "Pídele a zaelar que ponga un tiempo",
    "widgets.timer.close": "✕ Cerrar", "widgets.timer.pause": "⏸ Pausar", "widgets.timer.resume": "▶ Reanudar",
    "widgets.timer.cancel": "✕ Cancelar",
}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def mounted():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{port}/widgets/timer/")
        page.set_content("<div id='w'></div>")
        page.evaluate("async (src) => { window.__mod = await import(src); }",
                      f"http://127.0.0.1:{port}/widgets/timer/widget.js")

        def mount(data, translations):
            page.evaluate(
                "([data, dict]) => window.__mod.render(document.getElementById('w'), data, "
                "{action: () => Promise.resolve({ok:true}), close: () => {}, "
                " t: (k, p) => { let s = (dict[k] || k); if (p) for (const kk in p) "
                "s = s.split('{' + kk + '}').join(String(p[kk])); return s; }})",
                [data, translations],
            )

        yield page, mount
        browser.close()
    srv.terminate()


def test_a_paused_timer_reads_in_english(mounted):
    page, mount = mounted
    mount({"remaining": 90, "running": False, "target_seconds": 300, "label": ""}, _EN)
    assert page.inner_text(".ht-sub") == "⏸ Paused"
    assert page.inner_text(".ht-btn.primary") == "▶ Resume"


def test_a_paused_timer_reads_in_spanish(mounted):
    page, mount = mounted
    mount({"remaining": 90, "running": False, "target_seconds": 300, "label": ""}, _ES)
    assert page.inner_text(".ht-sub") == "⏸ Pausado"
    assert page.inner_text(".ht-btn.primary") == "▶ Reanudar"


def test_a_running_timer_pause_button_and_cancel_translate(mounted):
    page, mount = mounted
    mount({"remaining": 90, "running": True, "target_seconds": 300, "label": ""}, _EN)
    buttons = page.eval_on_selector_all(".ht-btn", "els => els.map(e => e.textContent)")
    assert "⏸ Pause" in buttons and "✕ Cancel" in buttons
    mount({"remaining": 90, "running": True, "target_seconds": 300, "label": ""}, _ES)
    buttons = page.eval_on_selector_all(".ht-btn", "els => els.map(e => e.textContent)")
    assert "⏸ Pausar" in buttons and "✕ Cancelar" in buttons


def test_the_default_label_translates_but_a_dictated_one_never_does(mounted):
    """The operator's own dictated label ('pasta al dente') is PRODUCT DATA, not UI chrome — it must never be
    run through a translation table, unlike the widget's own default placeholder text."""
    page, mount = mounted
    mount({"remaining": 90, "running": False, "target_seconds": 300, "label": ""}, _EN)
    assert page.eval_on_selector(".ht-label", "e => e.textContent") == "TIMER"
    mount({"remaining": 90, "running": False, "target_seconds": 300, "label": "pasta al dente"}, _EN)
    assert page.eval_on_selector(".ht-label", "e => e.textContent") == "pasta al dente"
    mount({"remaining": 90, "running": False, "target_seconds": 300, "label": "pasta al dente"}, _ES)
    assert page.eval_on_selector(".ht-label", "e => e.textContent") == "pasta al dente"   # unchanged by a language switch


def test_the_finished_state_names_the_dictated_label_inside_a_translated_sentence(mounted):
    page, mount = mounted
    mount({"remaining": 0, "running": False, "target_seconds": 300, "label": "el arroz", "finished": True}, _ES)
    assert page.inner_text(".ht-digits") == "¡LISTO!"
    assert page.inner_text(".ht-sub") == "⏰ el arroz cumplido"


def test_the_empty_state_and_close_button_translate(mounted):
    page, mount = mounted
    mount({"remaining": 0, "running": False, "target_seconds": 0}, _EN)
    assert page.inner_text(".ht-empty") == "Ask zaelar to set a time"
    mount({"remaining": 0, "running": False, "target_seconds": 300, "finished": True}, _EN)
    assert page.inner_text(".ht-btn.danger") == "✕ Close"


def test_a_ctx_with_no_t_at_all_degrades_to_the_bare_key_not_a_crash(mounted):
    """Older test doubles and any future host that has not been updated yet must not crash a widget that
    started using ctx.t — the widget's own local `tr` fallback (`(ctx && ctx.t) || (k => k)`) covers this."""
    page, _ = mounted
    page.evaluate(
        "() => window.__mod.render(document.getElementById('w'), "
        "{remaining: 90, running: false, target_seconds: 300, label: ''}, "
        "{action: () => Promise.resolve({ok:true}), close: () => {}})"
    )
    assert page.eval_on_selector(".ht-label", "e => e.textContent") == "widgets.timer.label_default"
