"""memory/contract.py — la frontera de la memoria, con trinquete (V2-114 F0).

La memoria tiene que poder reimplementarse sin que el agente se entere, y eso exige que se sepa por dónde entra
el agente. Medido el 2026-08-18: 84 de ~108 imports de producción ya pasan por `memory.api`; las ~24 fugas están
en pocos ficheros y casi todas son explicables. El riesgo no es el estado de hoy, es la DERIVA — que dentro de
tres meses haya cuarenta imports nuevos de tripas y nadie lo haya notado.

Estos tests son el trinquete. Mismo patrón que `test_observer_categories.py` (inventario CERRADO: un `kind`
nuevo sin clasificar rompe) y `test_roadmap_closure.py` (la deuda declarada solo puede BAJAR).

⚠️ Si uno de estos falla al añadir código, la pregunta correcta NO es «¿cómo silencio el test?» sino «¿esto
debería ir por la fachada?». Si genuinamente no puede, se añade a `BLESSED_INTERNAL_IMPORTS` **con su razón**,
y el número del techo baja solo cuando se cierra una fuga de verdad.
"""
from __future__ import annotations

import pathlib
import re

from memory import api as memapi
from memory.contract import BLESSED_INTERNAL_IMPORTS, MemoryContract

REPO = pathlib.Path(__file__).resolve().parents[3]

# Cota superior de fugas de tripas en PRODUCCIÓN. Es un TRINQUETE: solo puede bajar. Medido hoy = 24.
MAX_INTERNAL_IMPORTS = 24

_IMPORT_RE = re.compile(r"^[ \t]*from[ \t]+memory(\.[a-z_]+)?[ \t]+import[ \t]+(.+)$", re.MULTILINE)
_SKIP_DIRS = ("/memory/", "/tests/", "/.venv/", "/TMP/", "/.meshkore/")
# La fachada y este propio contrato son los caminos bendecidos por definición.
_FACADE = {"api", "contract"}


def _submodules() -> set[str]:
    """Los submódulos REALES de `memory/`, leídos del disco. Hace falta porque la forma dominante en este repo
    es `from memory import db as memdb` (el submódulo viaja en la lista de NOMBRES, no tras un punto), así que
    distinguir «importa la fachada» de «importa tripas» exige saber qué nombres son módulos."""
    return {p.stem for p in (REPO / "memory").glob("*.py") if p.stem != "__init__"}


def _production_files() -> list[pathlib.Path]:
    """Ficheros .py de producción: fuera `memory/` (es la implementación) y `tests/` (puede tocar tripas)."""
    out = []
    for p in REPO.rglob("*.py"):
        s = str(p)
        if any(d in s for d in _SKIP_DIRS):
            continue
        out.append(p)
    return out


def _internal_imports() -> list[tuple[str, str]]:
    """`[(submódulo, fichero_relativo)]` por cada import de tripas de `memory` en producción.

    Cubre las DOS formas que aparecen en el árbol:
      `from memory.rem import synthesize`   → el submódulo va tras el punto
      `from memory import db as memdb`      → el submódulo va en la lista de nombres (la forma dominante)
    """
    subs = _submodules()
    found: list[tuple[str, str]] = []
    for p in _production_files():
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(REPO))
        for dotted, names in _IMPORT_RE.findall(src):
            if dotted:                                  # from memory.<sub> import …
                sub = dotted.lstrip(".")
                if sub not in _FACADE:
                    found.append((f"memory.{sub}", rel))
                continue
            # from memory import a as x, b   →  cada nombre que sea un submódulo real cuenta
            for chunk in names.split("#")[0].split(","):
                name = chunk.strip().split(" as ")[0].strip().strip("()")
                if name in subs and name not in _FACADE:
                    found.append((f"memory.{name}", rel))
    return found


def test_the_facade_satisfies_the_contract():
    """`memory.api` debe cumplir el Protocol. Es tipado ESTRUCTURAL, así que esto se rompe en el momento en que
    alguien renombre o borre una función que el agente necesita — que es justo lo que un sustituto rompería."""
    assert isinstance(memapi, MemoryContract), (
        "memory.api ya no cumple MemoryContract: falta o cambió de nombre alguna función que el agente usa. "
        "Si el cambio es deliberado, actualiza el contrato en el MISMO commit."
    )


def test_every_contract_member_actually_exists_on_the_facade():
    """Un Protocol con `...` de cuerpo no verifica que la implementación exista si el chequeo estructural se
    relaja. Se comprueba a mano, y además da un mensaje útil (qué falta, no «no cumple»)."""
    esperados = [m for m in dir(MemoryContract) if not m.startswith("_")]
    faltan = [m for m in esperados if not callable(getattr(memapi, m, None))]
    assert not faltan, f"la fachada no expone: {faltan}"


def test_no_unblessed_internal_imports_in_production():
    """Cada import de tripas fuera de `memory/` tiene que estar declarado en BLESSED_INTERNAL_IMPORTS con su
    razón. Un submódulo nuevo alcanzado desde producción es una decisión de arquitectura, no un descuido."""
    intrusos = {}
    for sub, fichero in _internal_imports():
        if sub not in BLESSED_INTERNAL_IMPORTS:
            intrusos.setdefault(sub, []).append(fichero)
    assert not intrusos, (
        "imports de tripas de memory SIN bendecir:\n" +
        "\n".join(f"  {s} ← {', '.join(sorted(set(f)))}" for s, f in sorted(intrusos.items())) +
        "\n\n¿Puede ir por memory.api? Si de verdad no puede, añádelo a BLESSED_INTERNAL_IMPORTS con su razón."
    )


def test_internal_import_count_only_goes_down():
    """El trinquete numérico. Bendecir un submódulo no debe convertirse en licencia para importarlo desde
    cuarenta sitios: el TOTAL también está acotado."""
    n = len(_internal_imports())
    assert n <= MAX_INTERNAL_IMPORTS, (
        f"{n} imports de tripas en producción, techo {MAX_INTERNAL_IMPORTS}. La frontera se está abriendo: "
        f"mueve la llamada nueva a memory.api."
    )


def test_lowering_the_ceiling_is_noticed():
    """Si alguien cierra fugas y el número real baja bastante por debajo del techo, hay que BAJAR el techo — si
    no, el trinquete deja de morder. Este test avisa; no es un fallo de código, es mantenimiento del trinquete."""
    n = len(_internal_imports())
    assert n >= MAX_INTERNAL_IMPORTS - 4, (
        f"solo quedan {n} imports de tripas (techo {MAX_INTERNAL_IMPORTS}): baja MAX_INTERNAL_IMPORTS a {n} "
        f"para que el trinquete siga apretando."
    )


def test_blessed_list_has_no_dead_entries():
    """Una entrada bendecida que ya nadie usa es deuda documental: hace parecer que la frontera es más porosa
    de lo que es. Se limpia."""
    usados = {sub for sub, _ in _internal_imports()}
    # `vault_api`/`server_api` se montan por cadena en el servidor y pueden no aparecer como `from memory.x`
    exentos = {"memory.vault_api", "memory.server_api"}
    muertas = [s for s in BLESSED_INTERNAL_IMPORTS if s not in usados and s not in exentos]
    assert not muertas, (
        f"entradas bendecidas que ya nadie importa (quítalas de BLESSED_INTERNAL_IMPORTS): {sorted(muertas)}"
    )
