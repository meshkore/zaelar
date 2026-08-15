"""La imagen de la nube tiene que traer TODO lo que el motor importa al arrancar.

Por qué existe: el 2026-08-12 se desplegó `observability/` (V2-090) y la Machine crash-loopeó en boot con
`ModuleNotFoundError: No module named 'observability'` — faltaba su `COPY` en el `Dockerfile`. Lo desagradable
del fallo es que **la imagen construye perfectamente**: no hay ningún import en tiempo de build, así que nada
avisa hasta que el proceso arranca en producción. Lo cazó el smoke y revirtió, o sea que el coste fue un
despliegue perdido en vez de una caída — pero el workflow de release lo dejó escrito como una **sonda manual
antes de cortar el tag**, y una sonda manual es una que algún día no se corre.

Esto la vuelve automática. No sustituye al smoke (que prueba la imagen de verdad); llega antes, que es donde
sale barato.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]

# Paquetes top-level que NO tienen que estar en la imagen, cada uno con su motivo. Igual que `_EXENTOS` del gate
# de Energy: saltarse la regla cuesta escribir por qué, y ese texto es lo que otro puede discutir.
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
    """Una exención sobre un paquete borrado es un permiso que ya no protege nada y hace creer que el gate
    cubre algo que no existe. Se caduca sola."""
    muertas = [n for n in _FUERA_DE_LA_IMAGEN if n != "tests" and not (RAIZ / n).is_dir()]
    assert not muertas, f"exenciones que ya no apuntan a un paquete: {muertas}"
