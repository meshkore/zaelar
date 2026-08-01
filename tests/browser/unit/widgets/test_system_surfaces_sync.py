#
# V2-082 — el espejo backend `widgets/system_surfaces.py` debe mantenerse SINCRONIZADO con la fuente de verdad
# `frontend/app/core/system-surfaces.js`. Este test FALLA si divergen: añadir/editar una superficie dirigible por
# voz obliga a tocar los dos sitios. Parse tolerante (substring), suficiente para cazar la deriva típica (editar el
# JS sin tocar el .py, o al revés).
#
import re
from pathlib import Path

from widgets import system_surfaces

ENGINE = Path(__file__).resolve().parents[4]
_JS = ENGINE / "frontend" / "app" / "core" / "system-surfaces.js"


def _js_text() -> str:
    return _JS.read_text(encoding="utf-8")


def test_every_backend_surface_and_alias_is_in_the_js():
    js = _js_text()
    for sid, spec in system_surfaces.SYSTEM_SURFACES.items():
        assert f'id: "{sid}"' in js, f"superficie backend '{sid}' no está en el JS"
        assert f'"{spec["name"]}"' in js, f"nombre de '{sid}' ('{spec['name']}') no aparece en el JS"
        for a in spec["aliases"]:
            assert f'"{a}"' in js, f"alias '{a}' de '{sid}' no aparece en el JS (deriva JS↔backend)"


def test_every_voice_addressable_js_surface_is_mirrored_in_backend():
    """Cada entrada del JS con name!=null debe existir en el espejo backend (no puede haber una superficie
    dirigible por voz que el resolver del backend no conozca)."""
    js = _js_text()
    # ids del JS que tienen un name no-null: `id: "X", ... name: "…"` (name null => no dirigible).
    ids_with_name = set(re.findall(r'id:\s*"([^"]+)"[^}]*?name:\s*"', js, re.S))
    for sid in ids_with_name:
        assert sid in system_surfaces.SYSTEM_SURFACES, \
            f"superficie de sistema dirigible '{sid}' del JS no está en el espejo backend system_surfaces.py"
