"""V2-702 — the LINK half that the widget cannot fix on its own, and the `kind` the sheet is allowed to declare.

Rendering the url was the surface's job and it was dropping urls it already had (see
`tests/browser/e2e/widgets/test_a_result_looks_like_a_result.py`). SUPPLYING it is the filler's, and nothing was
asking for it: the `present` example in the manifest — which is what a model copies — had no `url` on its item
at all, and `presentation.audit` never mentioned the field.

Operator, 2026-09-15: «asegúrate de que cuando un widget de resultados busca cosas SIEMPRE muestre los links a
la página web original en donde se puede ver pues todo el detalle súper ampliado de la ficha». A result whose
original page cannot be opened is a dead end: what the record shows is whatever we judged worth copying, and the
rest of the listing becomes unreachable.

The second subject is `kind`. `widgets/presentation.py` rule 1 says the SURFACE owns the layout and whoever
fills it must not send `columns` — so the seam that lets a search influence the list format has to carry a fact
about the RESULTS ("these are products"), never an instruction about the drawing ("two columns"). These tests
pin that distinction, because it is the thing a future hand would erode.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from widgets import presentation

_ENGINE = Path(__file__).resolve().parents[4]
_MANIFEST = _ENGINE / "widgets" / "results" / "manifest.json"


def _audit(**payload):
    return presentation.audit("results", payload)


def _issue(issues, needle):
    return [i for i in issues if needle in i]


# ── the link ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_web_sheet_where_NO_result_carries_a_link_is_reported():
    issues = _audit(items=[{"title": "Olla A"}, {"title": "Olla B"}],
                    sources=[{"name": "Amazon", "url": "https://amazon.es"}])
    assert _issue(issues, "ningún resultado trae `url`"), issues


def test_one_link_is_enough_to_stop_the_blanket_complaint():
    """The blanket rule is about a sheet with no way out at all; a partial sheet is caught by the shape rule
    below, which says something more precise."""
    issues = _audit(items=[{"title": "Olla A", "url": "https://amazon.es/dp/A"}],
                    sources=[{"name": "Amazon", "url": "https://amazon.es"}])
    assert not _issue(issues, "ningún resultado trae `url`"), issues


def test_a_sheet_that_did_not_come_from_the_WEB_is_not_accused():
    """A list of the operator's own files, or of his own calendar, has no page to link to. The check is gated on
    the sheet declaring `sources`, which is what "I went out and looked" means on this surface — a rule that
    fires where it cannot be satisfied gets ignored, and then it stops protecting the case it was written for.
    """
    issues = _audit(items=[{"title": "informe-2025.pdf"}, {"title": "informe-2024.pdf"}])
    assert not _issue(issues, "ningún resultado trae `url`"), issues


def test_some_with_a_link_and_some_without_breaks_the_comparison():
    """Same reasoning the surface already applied to `price` and `facts`: comparing needs comparable columns,
    and "this one I can open and that one I cannot" is the least comparable difference of all."""
    issues = _audit(items=[{"title": "Olla A", "url": "https://amazon.es/dp/A"},
                           {"title": "Olla B"}],
                    sources=[{"name": "Amazon", "url": "https://amazon.es"}])
    assert _issue(issues, "unos traen `url` y otros no"), issues


def test_the_directive_ASKS_for_the_link_before_anyone_gets_it_wrong():
    """An incident report after the fact is the second line. The prompt block is the first, and it travels to
    every worker that names this sheet (`presentation.directive_for`)."""
    d = presentation.directive("results")
    assert "`url`" in d and "ficha COMPLETA" in d, d
    # …and it also tells them to stop pre-cropping photos, now that the surface shows them whole.
    assert "proporciones" in d or "entera" in d, d


def test_the_EXAMPLE_a_model_copies_has_a_link_on_its_item():
    """The manifest's `present` payload is a worked example, and a worked example without a `url` teaches an
    item without a `url` more effectively than any prose telling it to include one."""
    m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    item = m["actions"]["present"]["payload"]["items"][0]
    assert item.get("url"), "el ejemplo del manifest sigue enseñando un item sin enlace"


# ── the kind ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_sheet_remembers_WHAT_it_found(tmp_path, monkeypatch):
    from widgets import store
    from widgets.results import data as sheet
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    sheet.apply_action("present", {"q": "t1", "title": "Ollas", "kind": "product",
                                   "items": [{"title": "Olla A", "url": "https://x.test/a"}]})
    assert sheet.view_data("t1").get("kind") == "product"


def test_a_kind_the_surface_does_not_know_is_DROPPED_not_stored(tmp_path, monkeypatch):
    """It arrives from a model. An unrecognised word must cost nothing and must not reach the widget, which
    would then have to defend itself against it a second time."""
    from widgets import store
    from widgets.results import data as sheet
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    sheet.apply_action("present", {"q": "t2", "title": "Ollas", "kind": "dos columnas",
                                   "items": [{"title": "Olla A", "url": "https://x.test/a"}]})
    assert "kind" not in sheet.view_data("t2")


def test_a_second_present_does_not_forget_what_the_hunt_was_about(tmp_path, monkeypatch):
    """A search delivers provisionally and then finally. The second delivery replaces the ITEMS; what they ARE
    has not changed, and letting the list reflow into another format mid-search would be the surface flickering
    for no reason the operator can see."""
    from widgets import store
    from widgets.results import data as sheet
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    sheet.apply_action("present", {"q": "t3", "kind": "product",
                                   "items": [{"title": "A", "url": "https://x.test/a"}]})
    sheet.apply_action("present", {"q": "t3", "items": [{"title": "B", "url": "https://x.test/b"}]})
    assert sheet.view_data("t3").get("kind") == "product"


def test_kind_is_a_FACT_about_the_results_not_an_order_about_the_drawing():
    """The line that separates this seam from the `columns` the audit refuses. Every accepted value names a sort
    of thing; none of them names a shape.

    Without this, `kind` is one well-meaning commit away from becoming `kind: "two-columns"` — which is exactly
    the parameter `widgets/presentation.py` exists to have removed, and it cost three rich cards and an orphan
    the first time.
    """
    import re
    from widgets.results import data as sheet
    src = (_ENGINE / "widgets" / "results" / "widget.js").read_text(encoding="utf-8")
    assert "function layoutFor(" in src, "el formato ya no lo elige la superficie"
    # The layout names are READ from the widget rather than copied here: the two vocabularies have to stay
    # disjoint, and a copy would only prove that this file's copy is disjoint from itself. (The first draft of
    # V2-702 called the photo-left format `media` and the kinds already had a `media` — two meanings on one word
    # in one file, which is how the older one silently wins. It is `split` now.)
    m = re.search(r"const LAYOUTS = \[([^\]]*)\]", src)
    assert m, "no encuentro la tabla de formatos"
    layouts = set(re.findall(r'"([a-z]+)"', m.group(1)))
    assert len(layouts) >= 4, layouts
    generic = {"grid", "list", "columns", "cards", "table"}
    assert (layouts | generic).isdisjoint(set(sheet._KINDS)), (
        f"`kind` ha empezado a nombrar FORMAS: {(layouts | generic) & set(sheet._KINDS)}")


def test_the_audit_still_refuses_a_columns_parameter():
    """The rule `kind` must not become. Asserted here so the two live side by side and the difference is legible
    to whoever reads this file next."""
    issues = _audit(items=[{"title": "A"}], columns=2)
    assert _issue(issues, "`columns` viene en el payload"), issues


@pytest.mark.parametrize("kind", ["product", "place", "media", "photo", "document", "link", "plan"])
def test_every_declared_kind_is_documented_for_whoever_fills_the_sheet(kind):
    """A vocabulary a filler cannot read is a vocabulary it will not use."""
    guide = json.loads(_MANIFEST.read_text(encoding="utf-8"))["worker_guide"]
    assert f"`{kind}`" in guide, f"«{kind}» se acepta pero no está en la guía del worker"
