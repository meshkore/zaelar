"""V2-661 — a text the agent produced becomes a FILE on a shelf the operator can see.

Session 1cdcb08e (2026-09-11): «¿has guardado la declaración de independencia en mis archivos?» → the worker
wrote a perfect `.md` into `widgets/_data/navegador/` (the browser task's directory — the only path anybody had
ever told it), read the `archivos` card, saw nothing, and spent four minutes trying to download a PDF instead.
Three seams close it: the library files a text (`save_text`), the file manager declares the action (`save_document`),
the document sheet exports what is already on screen (`save_to_library`), and the worker prompt names the root.
"""
from __future__ import annotations

import importlib
import json
import pathlib

import pytest

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    """A private workspace: the library root, the widget stores and nothing of the operator's."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from library import paths as lpaths
    assert str(lpaths.root()).startswith(str(tmp_path)), "the library must live in the test workspace"
    yield tmp_path
    importlib.reload(workspace)
    importlib.reload(wstore)


def _manifest(wid: str) -> dict:
    return json.loads((_ENGINE / "widgets" / wid / "manifest.json").read_text(encoding="utf-8"))


# ── the library files a text ────────────────────────────────────────────────────────────────────────────────
def test_a_text_lands_on_the_documents_shelf_as_markdown(ws):
    from library import index, paths
    res = index.save_text("Declaración de Independencia (EE. UU.)", "# Declaration\n\nWhen in the Course…")
    assert res["ok"] and res["rel"].startswith(paths.folders()["documents"] + "/")
    assert res["rel"].endswith("Declaración de Independencia (EE. UU.).md"), "no extension → .md"
    assert pathlib.Path(res["path"]).read_text(encoding="utf-8").startswith("# Declaration")
    assert res["entry"]["kind"] == "document"
    assert any(e["rel"] == res["rel"] for e in index.listing("document")), "the shelf lists it"


def test_a_name_cannot_relocate_the_file_and_a_collision_is_suffixed(ws):
    from library import index, paths
    a = index.save_text("../../etc/passwd", "x")
    assert a["ok"] and pathlib.Path(a["path"]).parent == paths.dir_for("documents")
    assert "passwd" in a["rel"] and ".." not in a["rel"]
    b = index.save_text("notas.txt", "uno")
    c = index.save_text("notas.txt", "dos")
    assert b["ok"] and c["ok"] and b["rel"] != c["rel"], "the second file never overwrites the first"
    assert pathlib.Path(b["path"]).read_text() == "uno"


def test_an_empty_text_is_refused_by_name(ws):
    from library import index
    assert not index.save_text("vacío.md", "   ")["ok"]


# ── the file manager declares it and lands on the shelf ─────────────────────────────────────────────────────
def test_the_action_is_declared_as_a_view_and_named_in_the_usage():
    from widgets import actions as wactions
    m = _manifest("archivos")
    assert "save_document" in m["actions"], "an undeclared capability is one the model NARRATES (V2-540)"
    assert wactions.is_view(m["actions"]["save_document"], "save_document")
    assert "save_document" in m["usage"]


def test_save_document_writes_the_file_and_shows_its_folder(ws):
    from widgets.archivos import data as mod
    importlib.reload(mod)
    mod.apply_action("set_provider", {"provider": "local"})
    r = mod.apply_action("save_document", {"name": "Declaración de Independencia", "text": "When in the Course…"})
    assert r["ok"] and r["where"] == "Documentos" and r["folder_id"] == "shelf:documents"
    assert r["path"].endswith("Declaración de Independencia.md")
    v = mod.view_data()
    assert v["folder_id"] == "shelf:documents", "the card lands on the shelf the file went to"
    assert any(e["name"] == "Declaración de Independencia.md" for e in v["entries"])
    assert v["selected"] and v["selected"]["name"] == "Declaración de Independencia.md"


def test_save_document_refuses_an_empty_text_naming_the_fields(ws):
    from widgets.archivos import data as mod
    importlib.reload(mod)
    r = mod.apply_action("save_document", {"name": "x.md"})
    assert not r["ok"] and "text" in r["error"] and "name" in r["error"]


# ── the document sheet exports what is already on screen ────────────────────────────────────────────────────
def test_the_sheet_on_screen_is_saved_without_fetching_anything(ws):
    from widgets.documento import data as doc
    importlib.reload(doc)
    doc.apply_action("show", {"kind": "markdown", "title": "Declaración de Independencia (1776)",
                              "body": "# Declaración\n\nCuando en el curso de los acontecimientos humanos…"})
    r = doc.apply_action("save_to_library", {})
    assert r["ok"] and r["where"] == "documents"
    assert r["file"]["name"] == "Declaración de Independencia (1776).md", "the title names the file"
    assert "Documentos" in r["message"], "the spoken face says where it went (V2-463)"
    assert pathlib.Path(r["path"]).read_text(encoding="utf-8").startswith("# Declaración")
    assert "save_to_library" in _manifest("documento")["actions"]


def test_an_empty_sheet_and_a_pdf_are_refused(ws):
    from widgets.documento import data as doc
    importlib.reload(doc)
    assert not doc.apply_action("save_to_library", {})["ok"]
    doc.apply_action("show", {"kind": "pdf", "src": "https://example.org/x.pdf", "title": "x"})
    r = doc.apply_action("save_to_library", {})
    assert not r["ok"] and "PDF" in r["error"]


# ── the worker is TOLD where the files live ─────────────────────────────────────────────────────────────────
def test_the_worker_prompt_names_the_library_root_and_the_filing_action(ws):
    from library import paths
    from nucleo.dispatch_prompts import library_block
    block = library_block()
    assert str(paths.root()) in block and "save_document" in block and "documents" in block
    assert "navegador" in block, "it names the wrong place the worker actually wrote to"


def test_the_dispatcher_appends_the_block_to_every_trusted_worker():
    src = (_ENGINE / "nucleo" / "dispatch.py").read_text(encoding="utf-8")
    i = src.index("library_block()")
    assert src.index("DOC_SURFACE_BLOCK\n", 0) < i, "after the doc-surface block, before the resume preamble"
    assert "if trusted and not _dev:" in src[i - 400:i], "trusted workers only — the dev channel keeps its own prompt"
