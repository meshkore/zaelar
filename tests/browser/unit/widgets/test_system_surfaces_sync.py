#
# V2-082 — the backend mirror `widgets/system_surfaces.py` must remain SYNCHRONIZED with the source of truth,
# `frontend/app/core/system-surfaces.js`. This test FAILS if they diverge: adding/editing a voice-addressable
# surface requires touching both places. Tolerant parsing (substring), sufficient to catch typical drift (editing
# the JS without touching the .py, or vice versa).
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
    """Every JS entry with name!=null must exist in the backend mirror (there cannot be a voice-addressable surface
    that the backend resolver does not know about)."""
    js = _js_text()
    # JS ids with a non-null name: `id: "X", ... name: "…"` (name null => not addressable).
    ids_with_name = set(re.findall(r'id:\s*"([^"]+)"[^}]*?name:\s*"', js, re.S))
    for sid in ids_with_name:
        assert sid in system_surfaces.SYSTEM_SURFACES, \
            f"superficie de sistema dirigible '{sid}' del JS no está en el espejo backend system_surfaces.py"
