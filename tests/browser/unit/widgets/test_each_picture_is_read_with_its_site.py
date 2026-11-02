"""Each picture on the viewer is read with the SITE that holds it, apart from the search title (node 4.336).

V2-834 T21, use case `show-real-photo-of-a-new-car__es` (sandbox, 2026-11-02): the image search titled picture 1
«Ferrari Amalfi: New $262,000 V-8 Is a Win for the Automaker - Bloomberg» while the file lives on cdn.shopify.com; the
card's items line gave the model only the title, and it called the photo «the Bloomberg report» and «a shopify link»
in one breath — three contradictions about one source. The index now carries the site as the hint, and the generic
items line prints it beside the title.
"""
from __future__ import annotations

from widgets import refs
from widgets.imagenes import data as img


def test_the_items_line_names_title_and_site(monkeypatch):
    items = [{"url": "https://cdn.shopify.com/x.jpg", "site": "cdn.shopify.com",
              "title": "Ferrari Amalfi: New $262,000 V-8 Is a Win for the Automaker - Bloomberg"},
             {"url": "https://www.ferrari.com/a.jpg", "site": "ferrari.com", "title": "Ferrari Amalfi Spider - Ferrari.com"}]
    monkeypatch.setattr(img, "_load", lambda: {"items": items})
    idx = img.ref_index()
    assert [i["hint"] for i in idx] == ["cdn.shopify.com", "ferrari.com"]
    monkeypatch.setattr(refs, "_ref_index", lambda wid: idx)
    monkeypatch.setattr(refs, "_exposes_ref_index", lambda wid: True)
    line = refs.items_line("imagenes")
    assert "Bloomberg» (cdn.shopify.com)" in line and "Ferrari.com» (ferrari.com)" in line, line
