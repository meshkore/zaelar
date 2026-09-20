"""A link in the conversation is a link — and nothing else is (V2-736).

The operator, about the first conversation: «puedes publicar el enlace de la web
en el chat y dársela para decir: mira, te dejo ahí la web para que veas más
información o acceso a la documentación pública».

Measured before writing a line of prompt: `markdown-lite.js` rendered bold, code
and lists and NOTHING about URLs, so an agent told to publish a link would have
left him text to select and copy by hand — telling the model to use a capability
the surface does not have is the «capacidad sin declarar» failure with the halves
swapped (V2-540).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_link_in_the_conversation_is_a_link.mjs")
MD = Path("frontend/app/lib/markdown-lite.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_urls_become_anchors_and_hostile_markup_does_not():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_escaping_still_happens_before_anything_becomes_a_tag():
    """This file's own rule since it was written: escape FIRST, then introduce only safe tags from the
    escaped string. Autolinking is the first thing added that builds an ATTRIBUTE, which is a new way to
    break that rule — so the order is pinned here, not left to a reader."""
    src = MD.read_text(encoding="utf-8")
    body = src[src.index("function inline("):src.index("export function renderMarkdownLite")]
    assert body.index("escapeHtml(") < body.index("autolink(") or "autolink(\n" in body, body
    assert "autolink(" in body and "escapeHtml(line)" in body
    # the character class is the first line of defence and the explicit check is the second
    assert '[^\\s<>"\']+' in src, "quotes must never be part of a URL match — escapeHtml does not touch them"
    assert '/["\'<>]/.test(url)' in src, "and a quote that gets there anyway must refuse the anchor"
