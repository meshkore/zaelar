"""Demo pass 2026-09-28, full11 F2: «go to the part about the complaints against the king» over a document that HAS
«## The grievances against King George III» — the reply said «the grievances aren't written up yet», because the
digest the model reads stopped at 1400 characters. A cut digest now carries the whole outline."""


def test_a_long_document_digest_names_every_section(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.documento import data as doc
    body = "# The Declaration\n\n## Purpose\n" + ("word " * 400) + "\n\n## The grievances against King George III\n" \
           + ("charge " * 200) + "\n\n## The concluding declaration\nend"
    monkeypatch.setattr(doc, "_load", lambda: {"title": "Decl", "kind": "markdown", "body": body})
    out = doc.prompt_digest()
    assert "The grievances against King George III" in out and "The concluding declaration" in out
    assert "Recortado" in out


def test_a_short_document_is_shown_whole_without_an_outline(tmp_path, monkeypatch):
    from widgets.documento import data as doc
    monkeypatch.setattr(doc, "_load", lambda: {"title": "T", "kind": "markdown", "body": "# A\n\nshort"})
    assert "Recortado" not in doc.prompt_digest()
