"""A declared SYSTEM widget must EXIST on disk.

Found on 2026-08-20: `widgets/clock/`—a builtin, versioned since the initial commit—had disappeared
from the working tree. Nobody committed that deletion; it simply was no longer there. And **the entire suite passed with it
deleted**, 2696 tests green, because none asserted that builtins existed: the ones that mention the clock
do so by name in routing phrases (“close the clock for me”), which are resolved against the text and not
against the catalog.

What remains when one is missing is not “one fewer widget.” `widgets/registry.py::_BUILTINS` still declares it, so
the registry promises something that the disk does not have—and the place where this becomes visible is the catalog the
operator sees, not a test.

The two causes that seemed obvious were ruled out by MEASUREMENT, not judgment: the complete suite does not delete it
(`clock` survives a full run), and neither does a sandbox's lifecycle (it survives being started and stopped)—the
`teardown` in `tests/platform/sandbox_engine.py` only removes what THAT sandbox created, intersecting its own
`widget-agent: CREATE` lines with the folders that appeared while it was alive, and `clock` was not new. So the cause
remains unidentified, which is why this is a GUARD and not a fix: the next time it happens, it will be known in the same
commit instead of three weeks later.
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
    """The other half: a folder with an unreadable manifest or a different `id` is the same as not having it, and fails
    later and more severely—when someone requests that widget."""
    from widgets import registry

    broken = []
    for wid in sorted(registry._BUILTINS):
        man = WIDGETS / wid / "manifest.json"
        if not man.is_file():
            continue                      # the test above already covers it; do not duplicate the failure here
        try:
            if json.loads(man.read_text(encoding="utf-8")).get("id") != wid:
                broken.append(wid)
        except Exception as e:            # noqa: BLE001
            broken.append(f"{wid} ({e})")
    assert not broken, f"builtins cuyo manifest no se lee o no se llama como su carpeta: {broken}"
