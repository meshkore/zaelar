"""Un widget de SISTEMA declarado tiene que EXISTIR en disco.

Encontrado el 2026-08-20: `widgets/clock/` —builtin, versionado desde el commit inicial— había desaparecido
del árbol de trabajo. Nadie commiteó ese borrado; simplemente ya no estaba. Y **la suite entera pasaba con él
borrado**, 2696 tests en verde, porque ninguno afirmaba que los builtins existieran: los que mencionan el reloj
lo hacen por su nombre en frases de enrutado («ciérrame el reloj»), que se resuelven contra el texto y no
contra el catálogo.

Lo que queda cuando falta uno no es «un widget menos». `widgets/registry.py::_BUILTINS` sigue declarándolo, así
que el registro promete algo que el disco no tiene — y el sitio donde eso se nota es el catálogo que ve el
operador, no un test.

Descartadas por MEDICIÓN, no por criterio, las dos causas que parecían obvias: la suite completa no lo borra
(corrida entera, `clock` sobrevive) y el ciclo de vida de un sandbox tampoco (arrancado y parado, sobrevive) —
el `teardown` de `tests/platform/sandbox_engine.py` solo retira lo que ESE sandbox creó, intersecando sus
propias líneas `widget-agent: CREATE` con las carpetas que aparecieron mientras estaba vivo, y `clock` no era
nueva. Así que la causa sigue sin identificarse, y por eso esto es un GUARDA y no un arreglo: la próxima vez
que ocurra, se sabrá en el mismo commit en vez de dentro de tres semanas.
"""
from __future__ import annotations

import json
from pathlib import Path

WIDGETS = Path(__file__).resolve().parents[3] / "widgets"


def test_every_declared_builtin_is_on_disk():
    from widgets import registry

    missing = sorted(w for w in registry._BUILTINS if not (WIDGETS / w / "manifest.json").is_file())
    assert not missing, (
        f"widgets de SISTEMA declarados en `_BUILTINS` que no están en disco: {missing}. "
        "El registro los promete y el catálogo del operador no los va a encontrar. Si el borrado es "
        "deliberado, sácalos también de `_BUILTINS` en el MISMO commit; si no lo es, `git checkout` los "
        "recupera — están versionados.")


def test_and_its_manifest_says_who_it_is():
    """La otra mitad: una carpeta con un manifest ilegible o con otro `id` es lo mismo que no tenerla, y falla
    más tarde y peor — en el momento en que alguien pide ese widget."""
    from widgets import registry

    broken = []
    for wid in sorted(registry._BUILTINS):
        man = WIDGETS / wid / "manifest.json"
        if not man.is_file():
            continue                      # ya lo cubre el test de arriba; aquí no se duplica el fallo
        try:
            if json.loads(man.read_text(encoding="utf-8")).get("id") != wid:
                broken.append(wid)
        except Exception as e:            # noqa: BLE001
            broken.append(f"{wid} ({e})")
    assert not broken, f"builtins cuyo manifest no se lee o no se llama como su carpeta: {broken}"
