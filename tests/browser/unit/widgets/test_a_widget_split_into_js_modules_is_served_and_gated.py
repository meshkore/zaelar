"""A `widget.js` split into `js/` modules is served AND gated as one client (refactor2710-12 T-03).

The browser imports `./js/<part>.js` relative to `/widgets/<id>/widget.js`, so that prefix has to serve the folder;
and the static house-rules gate (no network, no interpolated innerHTML…) must read the modules too — otherwise
moving a line into `js/` is a way around it.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from widgets import client_files, paths, validator
from widgets import validator_js as _validator_js_m


def _widget(tmp_path, part: str):
    d = tmp_path / "demo"
    (d / "js").mkdir(parents=True)
    (d / "widget.js").write_text('import { paint } from "./js/paint.js";\nexport function render(el){ paint(el); }\n')
    (d / "js" / "paint.js").write_text(part)
    (d / "js" / "notes.txt").write_text("not a module")
    return d


def _client(monkeypatch, d):
    monkeypatch.setattr(paths, "dir_for", lambda wid: str(d) if wid == "demo" else None)
    app = FastAPI()
    app.include_router(client_files.router)
    return TestClient(app)


def test_the_entry_and_its_modules_are_served_and_nothing_else(monkeypatch, tmp_path):
    d = _widget(tmp_path, "export function paint(el){ el.textContent = 'hi'; }\n")
    c = _client(monkeypatch, d)
    assert c.get("/widgets/demo/widget.js").status_code == 200
    r = c.get("/widgets/demo/js/paint.js")
    assert r.status_code == 200 and "paint" in r.text and r.headers["cache-control"] == "no-cache"
    assert c.get("/widgets/demo/js/notes.txt").status_code == 404
    assert c.get("/widgets/demo/js/..%2Fwidget.js").status_code == 404
    assert c.get("/widgets/demo/js/missing.js").status_code == 404


def test_the_gate_reads_the_modules_too(tmp_path):
    d = _widget(tmp_path, "export function paint(el){ fetch('https://x'); }\n")
    assert paths.client_files(str(d)) == [str(d / "widget.js"), str(d / "js" / "paint.js")]
    assert _validator_js_m._scan_widget_js(paths.client_source(str(d))), "a banned sink inside js/ must fail the gate"


def test_disarm_a_gate_that_reads_only_the_entry_lets_it_through(tmp_path):
    d = _widget(tmp_path, "export function paint(el){ fetch('https://x'); }\n")
    assert _validator_js_m._scan_widget_js((d / "widget.js").read_text()) is None
    src = open(validator.__file__, encoding="utf-8").read()
    assert "_scan_widget_js(paths.client_source(d))" in src, "the catalog gate stopped reading the whole client"


def test_only_the_widgets_own_modules_may_be_imported():
    ok = ['import { a } from "./js/list.js";', "import { b } from './style.js';",
          'import * as I from "/frontend/app/lib/icons.js";']           # the one shared file (V2-831 T-12)
    bad = ['import { a } from "../agenda/widget.js";', 'import { a } from "/app/core/store.js";',
           'import { a } from "https://cdn.example/x.js";', 'import { a } from "./js/../../x.js";',
           'import { a } from "/frontend/app/lib/dom.js";', 'import { a } from "/frontend/app/lib/icons.js/../x.js";',
           'import { a } from "/frontend/app/lib/icons.js?x";', 'import { a } from "/frontend/app/lib/%69cons.js";',
           'import { a } from "/frontend/app/lib/icons.js#x";', 'import { a } from "//frontend/app/lib/icons.js";',
           'import { a } from "/frontend/app/lib/../lib/icons.js";', 'import { a } from "/frontend/app/lib%2Ficons.js";']
    assert all(_validator_js_m._scan_widget_js(src) is None for src in ok)
    assert all(_validator_js_m._scan_widget_js(src) for src in bad)


def test_a_versioned_entry_versions_the_whole_module_graph(monkeypatch, tmp_path):
    """The host re-imports `widget.js?v=<n>` to load an edited card with fresh state; its `js/` modules must be new
    too, or they keep the old code and the old module state."""
    d = _widget(tmp_path, 'import { x } from "./other.js";\nexport function paint(el){ x(el); }\n')
    c = _client(monkeypatch, d)
    assert './js/paint.js?v=17"' in c.get("/widgets/demo/widget.js?v=17").text
    assert '"./other.js?v=17"' in c.get("/widgets/demo/js/paint.js?v=17").text
    assert '"./js/paint.js"' in c.get("/widgets/demo/widget.js").text, "no version asked, the file as written"
    assert './js/paint.js?v=x"' in c.get("/widgets/demo/widget.js?v=../x").text, "the version is sanitised"
