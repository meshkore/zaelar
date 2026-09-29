"""V2-776 L2 · The document declares its SECTIONS, and where it is looking (node 4.232).

«Go to the part about proof of work» ends with the sheet scrolled to that heading. The card knew its headings
(`_blocks`) and its focus (`goto` writes it) and neither was a fact a verifier could read: no collection, and
`focus` a dict nobody folded. Now `view_data()["sections"]` lists the headings, the manifest declares it as a
read-only collection from the view, and `documento.goto`'s postcondition (`focus` changed) can be attested.
"""
import pytest

BODY = "# Bitcoin, in one page\n\nAn electronic cash system.\n\n## The trust problem\n\ntext\n\n## Proof-of-Work\n\nA nonce whose hash starts with zero bits.\n"


@pytest.fixture
def doc(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.documento import data
    assert data.apply_action("show", {"kind": "markdown", "title": "Bitcoin", "body": BODY})["ok"]
    return data


def test_the_headings_are_rows_with_their_level(doc):
    sec = doc.view_data()["sections"]
    assert [(r["n"], r["title"], r["level"]) for r in sec] == [
        (1, "Bitcoin, in one page", 1), (2, "The trust problem", 2), (3, "Proof-of-Work", 2)]


def test_the_collection_reads_from_the_view_and_is_read_only(doc):
    from widgets import rows
    assert rows.ops_for("documento", "sections") == ("list",)
    assert len(rows.select("documento", "sections", {"title~": "proof"})) == 1


def test_goto_moves_the_focus_and_the_postcondition_reads_it(doc):
    from nucleo import spec, verify
    dw = spec.render("documento", "goto", {"text": "proof of work"})
    assert dw["baseline"] is None, "before any goto the sheet looks at nothing"
    assert doc.apply_action("goto", {"text": "proof of work"})["ok"]
    assert verify.check(dw) is True
    assert verify.check({"widget": "documento", "field": "focus", "has": "proof-of-work"}) is True


def test_an_empty_sheet_declares_it(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.documento import data
    v = data.view_data()
    assert v["empty"] is True and v["sections"] == []
