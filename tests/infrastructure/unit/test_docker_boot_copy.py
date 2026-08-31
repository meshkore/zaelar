"""The cloud image must include EVERYTHING the engine imports at startup.

Why it exists: on 2026-08-12, `observability/` (V2-090) was deployed and the Machine crash-looped at boot with
`ModuleNotFoundError: No module named 'observability'` — its `COPY` was missing from the `Dockerfile`. The unpleasant
thing about the failure is that **the image builds perfectly**: there are no imports at build time, so nothing
raises an alert until the process starts in production. The smoke test caught it and rolled it back, meaning the
cost was a lost deployment rather than an outage — but the release workflow recorded it as a **manual probe
before cutting the tag**, and a manual probe is one that eventually goes unrun.

This makes it automatic. It does not replace the smoke test (which tests the actual image); it runs earlier, where
the cost is low.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]

# Top-level packages that must NOT be in the image, each with its reason. As with Energy's gate `_EXENTOS`,
# bypassing the rule requires writing down why, and that text is what someone else can challenge.
_FUERA_DE_LA_IMAGEN: dict[str, str] = {
    "files":
        "SHIM de compatibilidad (V2-003 · T55): el módulo se plegó en la memoria central y el boot importa "
        "`memory.server_api`, no éste. Nadie dentro del repo lo importa — meterlo en la imagen sería enviar "
        "código muerto a producción.",
    "tests":
        "el arnés de pruebas no viaja en la imagen de producción.",
}


def _paquetes_top_level() -> set[str]:
    return {p.name for p in RAIZ.iterdir()
            if p.is_dir() and (p / "__init__.py").exists() and not p.name.startswith((".", "_"))}


def _copiados() -> set[str]:
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    return set(re.findall(r"^COPY (\S+) ", dockerfile, re.M))


def test_todo_paquete_del_motor_viaja_en_la_imagen():
    faltan = sorted(_paquetes_top_level() - _copiados() - set(_FUERA_DE_LA_IMAGEN))
    assert not faltan, (
        f"paquetes top-level que NO están en el COPY del Dockerfile: {faltan}\n"
        "La imagen construirá bien y la Machine morirá al arrancar con ModuleNotFoundError. Añade su COPY, "
        "o —si de verdad no tiene que viajar— añádelo a _FUERA_DE_LA_IMAGEN con el motivo escrito."
    )


def test_una_exencion_apunta_a_algo_que_existe():
    """An exemption for a deleted package is a permission that no longer protects anything and makes it seem that
    the gate covers something that does not exist. It expires on its own."""
    muertas = [n for n in _FUERA_DE_LA_IMAGEN if n != "tests" and not (RAIZ / n).is_dir()]
    assert not muertas, f"exenciones que ya no apuntan a un paquete: {muertas}"
