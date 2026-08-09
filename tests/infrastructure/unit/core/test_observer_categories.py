"""
INVENTARIO de categorías del visor (2026-08-09, norma del operador: «si tenemos N familias, TODOS los eventos
tienen que estar asociados a una de ellas»).

El filtro superior del visor solo puede ser fiable si cada `kind` que el sistema emite pertenece a una familia
conocida. Cuando no es así pasa lo que el operador vio: filas `SESSION` y `BACKGROUND` cayendo por el hilo sin
que ningún chip las gobierne — no se pueden apagar, y peor, no se sabe a qué pieza pertenecen.

Este test NO mantiene una lista a mano: RECORRE el código, saca los `kind` literales de cada llamada real a
`voice.observer.emit` (siguiendo también los wrappers locales `def _emit(kind, ...)`, que son legión) y exige
que todos estén en `_CAT`. Añadir una capacidad nueva con su propio kind y olvidarse de clasificarlo falla aquí,
no en la cara del operador tres semanas después.

Se ignora a propósito `tests/`: los tests inventan kinds sintéticos («boom», «oops») que no son del producto.
"""
from __future__ import annotations

import ast
from pathlib import Path

from voice import observer

ENGINE = Path(__file__).resolve().parents[4]
_SKIP = (".venv", "node_modules", "__pycache__", "TMP")

# Familias que el visor pinta como chip (frontend/app/components/DebugPanel.js::CATS). El backend no puede
# inventarse una familia que la UI no ofrece: sería un evento inalcanzable desde el filtro.
CATS = {"flash", "worker", "memory", "widget", "system", "pulse"}


def _emitted_kinds() -> dict[str, set[str]]:
    """{kind: {ficheros}} de cada `emit("<kind>", …)` del PRODUCTO."""
    found: dict[str, set[str]] = {}
    for f in ENGINE.rglob("*.py"):
        rel = f.relative_to(ENGINE).as_posix()
        if rel.startswith("tests/") or any(p in rel for p in _SKIP):
            continue
        try:
            src = f.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except Exception:
            continue
        if "observer" not in src:
            continue

        # Nombres que EN ESTE fichero son el emit del observer: el import directo (con o sin alias) y los
        # wrappers locales cuyo PRIMER parámetro se llama `kind` (los que se llaman `label` reciben otra cosa
        # — p.ej. widgets/navegador/owner.py — y colarlos daría kinds falsos).
        names: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module and "observer" in n.module:
                names.update(a.asname or a.name for a in n.names if a.name == "emit")
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in ("emit", "_emit"):
                args = [a.arg for a in n.args.args if a.arg != "self"]
                if args and args[0] == "kind":
                    names.add(n.name)

        for n in ast.walk(tree):
            if not isinstance(n, ast.Call) or not n.args:
                continue
            fn = n.func
            direct = isinstance(fn, ast.Name) and fn.id in names
            dotted = (isinstance(fn, ast.Attribute) and fn.attr == "emit"
                      and isinstance(fn.value, ast.Name) and "observer" in fn.value.id.lower())
            if (direct or dotted) and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                found.setdefault(n.args[0].value, set()).add(rel)
    return found


def test_the_scan_finds_the_real_kinds():
    """Guarda del propio guard: si el escaneo dejara de encontrar nada, el test de abajo pasaría en vacío."""
    kinds = _emitted_kinds()
    assert {"brain", "widget", "memory", "task"} <= set(kinds), f"escaneo sospechoso: {sorted(kinds)}"


def test_every_emitted_kind_belongs_to_a_family():
    unmapped = {k: sorted(v) for k, v in _emitted_kinds().items() if k not in observer._CAT}
    assert not unmapped, (
        "kinds sin familia en voice/observer.py::_CAT — el operador no puede filtrarlos:\n"
        + "\n".join(f"  {k}  ← {', '.join(v)}" for k, v in sorted(unmapped.items()))
    )


def test_families_exist_in_the_viewer():
    bad = {k: c for k, c in observer._CAT.items() if c not in CATS}
    assert not bad, f"familias que el visor no pinta como chip (evento inalcanzable desde el filtro): {bad}"
