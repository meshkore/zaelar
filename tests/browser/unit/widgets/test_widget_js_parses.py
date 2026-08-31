"""Every `widget.js` in the catalog must PARSE as an ES module.

Why it exists (2026-08-12, the same failure twice in one day). A `widget.js` puts its CSS in a template literal
(`s.textContent = \\`…\\``), and a single backtick inside it —in a comment, describing a field— is enough to close the
string and break the entire file. The symptom is not a readable error: the module fails to import, `desktop.js` falls
into its `catch`, and the card displays «this widget could not be loaded». The suite saw nothing, because frontend tests
are string contracts and a broken string is still a string.

The cost of the check is one `node --check` per file. The regression it prevents is a dead card in
production, caused moreover by something that cannot be guessed by reading the diff (the diff looks like an innocent comment).

It is skipped if `node` is not available on the machine: the engine does not require it to start, so its absence cannot
become a suite failure — but when it is available (CI and the operator's Mac), this is the guard.
"""
import pathlib
import shutil
import subprocess

import pytest

WIDGETS = pathlib.Path("widgets")
NODE = shutil.which("node")
ENTRIES = sorted(WIDGETS.glob("*/widget.js"))


def _template_literals(src: str):
    """The `…` blocks that the file opens with `s.textContent=` — where the CSS lives and where the failure bites."""
    out, needle = [], "textContent=`"
    at = 0
    while True:
        i = src.find(needle, at)
        if i < 0:
            return out
        i += len(needle)
        j = src.find("`", i)
        if j < 0:
            return out
        out.append(src[i:j])
        at = j + 1


@pytest.mark.skipif(NODE is None, reason="sin node en esta máquina (el motor no lo requiere)")
@pytest.mark.parametrize("entry", ENTRIES, ids=lambda p: p.parent.name)
def test_every_widget_js_parses_as_an_es_module(entry):
    """Bare `node --check` treats the file as a script and fails on the `export`: it must be declared as a module."""
    r = subprocess.run([NODE, "--input-type=module", "--check"],
                       stdin=entry.open("rb"), capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"{entry} no parsea como módulo ES:\n{r.stderr.strip()[:600]}"


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda p: p.parent.name)
def test_no_backtick_inside_a_css_template_literal(entry):
    """The same failure, stated where it makes sense: a backtick inside the CSS block closes it. This test gives the
    EXACT diagnosis (file + line + text) instead of a SyntaxError with a line number from stdin."""
    src = entry.read_text(encoding="utf-8")
    for block in _template_literals(src):
        offenders = [ln.strip()[:120] for ln in block.split("\n") if "`" in ln]
        assert not offenders, (
            f"{entry}: acento grave DENTRO del template literal del CSS — cierra la cadena y rompe el módulo. "
            f"Usa comillas simples en el comentario. Líneas: {offenders}")


def test_the_catalog_is_actually_being_checked():
    """If the glob stopped finding files, the two tests above would pass on an empty set and the guard would be smoke."""
    assert len(ENTRIES) >= 5, f"solo {len(ENTRIES)} widget.js encontrados: ¿cambió el layout del catálogo?"
    assert any(p.parent.name == "results" for p in ENTRIES)
