"""Todo `widget.js` del catálogo tiene que PARSEAR como módulo ES.

Por qué existe (2026-08-12, el mismo fallo dos veces en un día). Un `widget.js` mete su CSS en un template literal
(`s.textContent = \\`…\\``), y basta UN acento grave dentro —en un comentario, describiendo un campo— para cerrar la
cadena y romper el fichero entero. El síntoma no es un error legible: el módulo no importa, `desktop.js` cae en su
`catch`, y la tarjeta enseña «no se pudo cargar este widget». Nada en la suite lo veía, porque los tests de frontend
son contratos de string y un string roto sigue siendo un string.

El coste de la comprobación es un `node --check` por fichero. La regresión que evita es una tarjeta muerta en
producción, y encima con una causa que no se adivina leyendo el diff (el diff parece un comentario inocente).

Se salta si no hay `node` en la máquina: el motor no lo requiere para arrancar, así que su ausencia no puede
convertirse en un fallo de la suite — pero cuando está (CI, y el Mac del operador), esto es el guard.
"""
import pathlib
import shutil
import subprocess

import pytest

WIDGETS = pathlib.Path("widgets")
NODE = shutil.which("node")
ENTRIES = sorted(WIDGETS.glob("*/widget.js"))


def _template_literals(src: str):
    """Los bloques `…` que abre el fichero con `s.textContent=` — donde vive el CSS y donde muerde el fallo."""
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
    """`node --check` a secas trata el fichero como script y falla en el `export`: hay que declararlo módulo."""
    r = subprocess.run([NODE, "--input-type=module", "--check"],
                       stdin=entry.open("rb"), capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"{entry} no parsea como módulo ES:\n{r.stderr.strip()[:600]}"


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda p: p.parent.name)
def test_no_backtick_inside_a_css_template_literal(entry):
    """El mismo fallo, dicho donde se entiende: un acento grave dentro del bloque de CSS lo cierra. Este test da el
    diagnóstico EXACTO (fichero + línea + texto) en vez de un SyntaxError con un número de línea del stdin."""
    src = entry.read_text(encoding="utf-8")
    for block in _template_literals(src):
        offenders = [ln.strip()[:120] for ln in block.split("\n") if "`" in ln]
        assert not offenders, (
            f"{entry}: acento grave DENTRO del template literal del CSS — cierra la cadena y rompe el módulo. "
            f"Usa comillas simples en el comentario. Líneas: {offenders}")


def test_the_catalog_is_actually_being_checked():
    """Si el glob dejara de encontrar ficheros, los dos tests de arriba pasarían por vacío y el guard sería humo."""
    assert len(ENTRIES) >= 5, f"solo {len(ENTRIES)} widget.js encontrados: ¿cambió el layout del catálogo?"
    assert any(p.parent.name == "results" for p in ENTRIES)
