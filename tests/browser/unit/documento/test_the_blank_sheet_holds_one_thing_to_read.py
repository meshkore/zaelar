#
# V2-549 — the blank sheet: ONE thing to read (a recipe, a report, instructions, a PDF), and the borders that
# keep it from becoming every other widget.
#
# Two halves on purpose. The store half fixes the contract a caller depends on — the actions are DECLARED (an
# undeclared one is invisible to the brain, V2-520), `show` is a VIEW action (an unflagged `show` is what turned
# «enséñame la foto de un Ferrari» into an empty viewer, V2-547), an empty `show` does not blank a sheet the
# operator is reading, and a `src` cannot walk out of the widget's own directory.
#
# The RENDERING half is not decoration. This widget's entire job is to display text that arrived from the web,
# from a worker or from a model — exactly the text that must never execute — and no source-level assertion can
# tell a stripped attribute from one that merely looks stripped. It also caught, in mensajeria, a backtick
# inside a CSS comment silently closing the widget's template literal (V2-546).
#
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time

import pytest

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_WIDGET = _ENGINE / "widgets" / "documento"


# ── the contract ────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def data(tmp_path, monkeypatch):
    """A private store. A unit test never touches the operator's live sheet."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    import importlib
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from widgets.documento import data as mod
    importlib.reload(mod)
    yield mod
    importlib.reload(workspace)
    importlib.reload(wstore)


def _manifest() -> dict:
    return json.loads((_WIDGET / "manifest.json").read_text(encoding="utf-8"))


def test_the_three_actions_are_declared_and_showing_is_a_view():
    """An action the manifest does not name cannot be reached by voice; and the action that IS this widget's
    purpose has to be runnable on a pure show order, or «enséñame la receta» can only open a bare card."""
    from widgets import actions as wactions
    acts = _manifest()["actions"]
    assert set(acts) == {"show", "append", "clear"}, "keep the vocabulary small — that was the ask"
    assert wactions.is_view(acts["show"], "show"), "`show` FILLS the sheet: it must be a view action (V2-547)"
    assert wactions.is_view(acts["append"], "append")
    assert wactions.classify(acts["clear"], "clear") == wactions.FAST


def test_the_sheet_ships_with_the_agent():
    from widgets import registry
    assert "documento" in registry._BUILTINS, "a shipped widget that is not in _BUILTINS reads as user-created"


def test_a_recipe_lands_whole_and_the_brain_can_read_it_back(data):
    body = "## Ingredientes\n\n- 5 patatas\n- 6 huevos\n\n## Pasos\n\n1. Pela las patatas."
    out = data.apply_action("show", {"title": "Tortilla", "body": body, "source": "de casa"})
    assert out["ok"] and out["kind"] == "markdown"
    v = data.view_data()
    assert v["title"] == "Tortilla" and v["body"] == body and not v["empty"]
    # The reason a document widget beats a screenshot: with the sheet open, «how much egg?» is a question
    # about text we already hold.
    assert "6 huevos" in data.prompt_digest()


def test_an_empty_show_never_blanks_a_sheet_being_read(data):
    data.apply_action("show", {"title": "Informe", "body": "algo que el operador está leyendo"})
    out = data.apply_action("show", {"title": "Informe"})
    assert out["ok"] is False and "body" in out["error"]
    assert data.view_data()["body"], "an empty show wiped the sheet — the operator is left staring at nothing"


def test_a_long_report_can_be_written_while_it_is_read(data):
    data.apply_action("show", {"title": "Informe", "body": "Primera parte."})
    out = data.apply_action("append", {"body": "Segunda parte."})
    assert out["ok"] and out["added"] > 0
    body = data.view_data()["body"]
    assert body.startswith("Primera parte.") and body.endswith("Segunda parte.")
    assert data.apply_action("append", {"body": "   "})["ok"] is False


def test_the_sheet_has_a_ceiling_and_says_so_instead_of_growing(data):
    data.apply_action("show", {"body": "x" * (data.MAX_CHARS - 1)})
    out = data.apply_action("append", {"body": "y" * 500})
    assert out["ok"] is False and "llena" in out["error"]
    assert len(data.view_data()["body"]) <= data.MAX_CHARS


def test_a_pdf_is_a_url_or_a_file_we_hold_and_nothing_else(data):
    from widgets import store as wstore
    assert data.apply_action("show", {"kind": "pdf", "src": "https://x.test/a.pdf"})["ok"]
    assert data.view_data()["src"] == "https://x.test/a.pdf"

    # A path is refused even when it names a real file: a widget reads inside its own directory or nowhere.
    out = data.apply_action("show", {"kind": "pdf", "src": "../../../etc/passwd"})
    assert out["ok"] is False and "passwd" in out["error"]
    assert data.view_data()["src"] == "https://x.test/a.pdf", "a refused src must not disturb what is on screen"

    (pathlib.Path(wstore.data_dir("documento")) / "contrato.pdf").write_bytes(b"%PDF-1.4\n")
    assert data.apply_action("show", {"kind": "pdf", "src": "contrato.pdf"})["ok"]
    assert data.view_data()["src"] == "/widgets/documento/asset/contrato.pdf"
    # The refusal NAMES what is actually here, so the next attempt can be right (V2-463).
    missing = data.apply_action("show", {"kind": "pdf", "src": "otro.pdf"})
    assert "contrato.pdf" in missing["error"] and "state.json" not in missing["error"]


def test_the_kind_is_inferred_from_what_actually_arrived(data):
    assert data.apply_action("show", {"src": "https://x.test/a.pdf"})["kind"] == "pdf"
    assert data.apply_action("show", {"body": "texto llano"})["kind"] == "markdown"
    assert data.apply_action("show", {"kind": "receta", "body": "# Sopa"})["kind"] == "markdown"


def test_a_pdf_says_it_cannot_be_quoted_rather_than_letting_the_model_invent_it(data):
    data.apply_action("show", {"kind": "pdf", "src": "https://x.test/a.pdf", "title": "Contrato"})
    digest = data.prompt_digest()
    assert "Contrato" in digest and "no lo inventes" in digest
    assert data.apply_action("append", {"body": "hola"})["ok"] is False


def test_an_open_and_empty_sheet_is_a_fact_the_brain_must_see(data):
    data.apply_action("show", {"body": "algo"})
    assert data.apply_action("clear")["ok"]
    assert data.view_data()["empty"] is True
    assert "VACÍA" in data.prompt_digest()


# ── the rendering ───────────────────────────────────────────────────────────────────────────────────────────
pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def page():
    # A REAL http origin: an ES module cannot be loaded from `about:blank`/`file:`.
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
            pg = browser.new_page()
            pg._hb_origin = f"http://127.0.0.1:{port}/widgets/documento/"
            pg._hb_widget = f"http://127.0.0.1:{port}/widgets/documento/widget.js"
            yield pg
            browser.close()
    finally:
        srv.terminate()


def _mount(pg, view: dict, host_title: bool = False):
    pg.goto(pg._hb_origin)
    pg.set_content("<div id='w'></div>")
    pg.evaluate(
        """async ([src, data, hostTitle]) => {
             const mod = await import(src + '?v=' + Math.random());
             const el = document.getElementById('w');
             if(hostTitle) el.dataset.hostTitle = '1';
             mod.render(el, data, { action: () => {}, running: true });
           }""",
        [pg._hb_widget, view, host_title],
    )


def _view(**kw) -> dict:
    base = {"kind": "markdown", "title": "", "subtitle": "", "body": "", "src": "", "source": "",
            "updated": 0, "chars": 0, "empty": True}
    base.update(kw)
    base["empty"] = not (base["body"] or base["src"])
    base["chars"] = len(base["body"])
    return base


_RECIPE = ("# Tortilla\n\n"
           "Una receta **clásica** con un toque *lento* y un `sartén` de 24 cm.\n\n"
           "## Ingredientes\n\n- 5 patatas\n- 6 huevos\n\n"
           "## Pasos\n\n1. Pelar\n2. Freír\n\n"
           "> Reposar antes de dar la vuelta.\n\n"
           "| Paso | Tiempo |\n|---|---|\n| Freír | 20 min |\n| Cuajar | 4 min |\n\n"
           "---\n\n```\nfuego lento\n```\n\n"
           "Ver [la fuente](https://example.test/receta).\n")


def test_markdown_becomes_a_document_and_not_a_wall_of_asterisks(page):
    _mount(page, _view(title="Tortilla", body=_RECIPE, source="de casa"))
    sheet = page.locator(".hbd-sheet")
    assert sheet.count() == 1
    assert page.locator(".hbd-sheet h1").inner_text() == "Tortilla"
    assert page.locator(".hbd-sheet h2").count() == 2
    assert page.locator(".hbd-sheet ul li").count() == 2
    assert page.locator(".hbd-sheet ol li").count() == 2
    assert page.locator(".hbd-sheet strong").inner_text() == "clásica"
    assert page.locator(".hbd-sheet em").inner_text() == "lento"
    assert page.locator(".hbd-sheet code").first.inner_text() == "sartén"
    assert page.locator(".hbd-sheet blockquote").count() == 1
    assert page.locator(".hbd-sheet hr").count() == 1
    assert page.locator(".hbd-sheet pre code").inner_text().strip() == "fuego lento"
    assert page.locator(".hbd-sheet table th").count() == 2
    assert page.locator(".hbd-sheet table tbody tr").count() == 2
    assert page.locator(".hbd-sheet a").get_attribute("href") == "https://example.test/receta"
    # The marks themselves must be GONE from the text — the whole complaint about raw markdown.
    assert "**" not in sheet.inner_text() and "|---|" not in sheet.inner_text()


def test_a_wide_table_scrolls_inside_its_own_box(page):
    """House rule: the page never scrolls sideways; the wide thing does."""
    _mount(page, _view(body="| a | b |\n|---|---|\n| 1 | 2 |\n"))
    assert page.locator(".hbd-tw > table").count() == 1


def test_a_link_with_a_scheme_we_do_not_trust_is_shown_as_text(page):
    _mount(page, _view(body="Pulsa [aquí](javascript:alert(1)) para nada."))
    assert page.locator(".hbd-sheet a").count() == 0, "a javascript: link became a real link"
    assert "aquí" in page.locator(".hbd-sheet").inner_text()


def test_pasted_html_cannot_bring_behaviour_or_a_foreign_stylesheet_with_it(page):
    body = ('<h2 class="ttl" style="position:fixed;top:0">Receta</h2>'
            '<p onclick="window.__pwned=1">hola <b>mundo</b></p>'
            '<script>window.__pwned=1</script>'
            '<img src="x" onerror="window.__pwned=1">'
            '<iframe src="https://evil.test"></iframe>'
            '<form><input name="p"></form>'
            '<ul><li>uno</li></ul>')
    _mount(page, _view(kind="html", body=body))
    assert page.evaluate("() => window.__pwned") is None, "html content executed"
    for gone in ("script", "iframe", "form", "input", "img"):
        assert page.locator(f".hbd-sheet {gone}").count() == 0, f"<{gone}> survived the whitelist"
    assert page.locator(".hbd-sheet [onclick]").count() == 0
    h2 = page.locator(".hbd-sheet h2")
    assert h2.inner_text() == "Receta"
    # class/style are dropped so a fragment from anywhere lands in THIS sheet's typography and theme.
    assert h2.get_attribute("class") in (None, "") and h2.get_attribute("style") in (None, "")
    assert page.locator(".hbd-sheet b").inner_text() == "mundo", "harmless markup must survive"
    assert page.locator(".hbd-sheet li").inner_text() == "uno"


def test_a_pdf_is_handed_to_the_browsers_own_viewer(page):
    _mount(page, _view(kind="pdf", src="/widgets/documento/asset/contrato.pdf", title="Contrato"))
    frame = page.locator("iframe.hbd-pdf")
    assert frame.count() == 1
    assert frame.get_attribute("src").endswith("/contrato.pdf")
    assert page.locator(".hbd-sheet").count() == 0


def test_an_empty_sheet_says_it_is_empty_instead_of_showing_nothing(page):
    _mount(page, _view())
    assert page.locator(".hbd-blank").count() == 1
    assert "blanco" in page.locator("#w").inner_text().lower()


def test_the_title_is_not_printed_twice_when_the_card_already_carries_it(page):
    _mount(page, _view(title="Tortilla", body="texto"), host_title=True)
    assert page.locator(".hbd-title").count() == 0, "the card header already shows the title"
    _mount(page, _view(title="Tortilla", body="texto"), host_title=False)
    assert page.locator(".hbd-title").inner_text() == "Tortilla"
