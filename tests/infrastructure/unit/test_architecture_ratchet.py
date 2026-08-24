"""The architecture ratchet — frozen on 2026-08-23, the day the audit measured where complexity actually lives.

Every number below is a MEASUREMENT, not a wish: the audit (over `485c283` + the in-flight work that landed with
`2cb5739`/`c3110f8`) found 70k LOC of engine Python whose complexity is not spread but CONCENTRATED — four god
files, two of them holding the SAME turn implemented twice (`_run_inner` = 2,603 lines in one function,
`run_turn` = 1,051), stitched together by 21 literal «impl PARALELA — cablear en AMBOS» markers and by hundreds
of function-local imports that exist to paper over import cycles.

This file is the F0 of the refactor plan: it does not fix any of that. It freezes it, so it can only SHRINK.
Same mechanism as `test_roadmap_closure`'s declared debt: the values are edited DOWNWARD when a file is split
(that edit is the celebration), and never upward — growth in a listed file means EXTRACT, not raise the ceiling.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ENGINE)) if str(ENGINE) not in sys.path else None


def _loc(p: Path) -> int:
    return p.read_text().count("\n") + 1


def _lazy_imports(p: Path) -> int:
    """Imports INSIDE functions — each one is an import cycle papered over, i.e. hidden coupling."""
    n = 0
    for node in ast.walk(ast.parse(p.read_text())):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.col_offset > 0:
            n += 1
    return n


# ── the frozen table: {file: (max LOC, max lazy imports)} ────────────────────────────────────────────────────
#
# ⚠️ Un techo SUBIÓ el 2026-08-23, el segundo día de vida del trinquete, y conviene que quede escrito porque es
# el proxy fallando y no la regla cediendo: `owner.py` y `probe.py` ganaron UNA línea cada uno —el `import` del
# helper `nucleo.errors.brief`— al retirar 10 y 1 copias respectivamente de un idioma que reventaba con las
# excepciones sin mensaje (nodo 7.24). LOC mide tamaño, no complejidad, y ahí midió al revés. La subida es
# auditable: +1 línea, −11 copias frágiles. Si alguien invoca este precedente sin poder decir QUÉ duplicación
# retiró y CUÁNTAS copias, está subiendo el techo, que es justo lo que la tabla existe para impedir.
# Measured 2026-08-23. Only ever edit DOWNWARD. If a change you are making pushes a file over its ceiling, the
# ratchet is telling you to extract a module — which is the entire point of the audit this was born from.
#
# ── 2026-08-24: TRES techos BAJAN, y conviene decir por qué se subieron primero ────────────────────────────
# El trinquete llevaba rojo desde la noche del 23 y lo rompí yo, en tres commits seguidos (`41355d9`,
# `195a77a`, `58aba18`) — y no me enteré porque corrí las suites que creía tocadas (`agent_headless`,
# `browser`, `use_cases`) y este guarda vive en `infrastructure`. Lección aparte del arreglo: un trinquete
# COMPARTIDO no lo ve quien corre solo su vecindario.
#
# La tentación era invocar el precedente de `owner.py`/`probe.py` de arriba, y no se puede: ese exige poder
# decir QUÉ duplicación se retiró y CUÁNTAS copias, y yo no había retirado ninguna — solo había escrito la
# evidencia de tres arreglos, que en este repo se guarda a propósito y que LOC cuenta como si fuera
# complejidad. Así que se extrae, que es lo que la tabla pide:
#
#   nucleo/flash/prompt.py     1104 → 843   el bloque del NAVEGADOR (5 caras + 3 ayudantes) → flash/live_blocks.py
#   nucleo/dispatch.py         2045 → 1910  la HOJA como superficie del progreso            → nucleo/sheets.py
#
# ── 2026-08-24, más tarde: 1910 → 1879 ────────────────────────────────────────────────────────────────────
# `record_phase` se va con la hoja (V2-281). Es el mismo concern —lo que la pestaña de PROCESO pinta— y su
# cuerpo es puro sobre el registro, así que `dispatch` se queda solo con resolverlo, que es lo único que él
# tiene. Se extrae en vez de subir el techo por UNA línea (un campo nuevo en la pestaña del navegador): shavear
# comentarios para cuadrar un número es exactamente el instinto que esta tabla existe para corregir.
#   nucleo/workers/session.py   879 → 825   los dos constructores de texto del fallo        → workers/handoff.py
#
# ── 2026-08-24, V2-287: 1172 → 1062 ────────────────────────────────────────────────────────────────────────
# `widgets/results/data.py` se pasó del techo por VEINTE líneas al añadir un hecho al digest del prompt (que la
# fila lleva su enlace) con su evidencia detrás. Se extrae en vez de subir, y el corte estaba dado: el digest
# es una función PURA de un dict de hoja —no lee el almacén ni escribe nada—, así que se lleva entero a
# `widgets/results/digest.py` y `data.py` se queda con `prompt_digest()`, que es el único que necesita saber
# QUÉ hojas existen y es el nombre que `widgets/refs.py` busca por convención.
#   widgets/results/data.py    1172 → 1061  el digest del prompt (cabecera + hoja)        → widgets/results/digest.py
#
# Los tres eran fronteras que YA estaban dibujadas —el bloque del navegador tenía su `try` propio, la sección
# de la hoja su banner desde V2-227, y las dos funciones de texto son puras sobre el record— y en dos de los
# tres había además una capa pidiéndole al vecino lo que no es suyo (`widgets/results/data.py` importando de
# `dispatch` cómo se llama su caja). `sheets.py` nace HOJA: recibe el registro como argumento en vez de
# importarlo, que es el ciclo que V2-112 ya pagó.
_CEILINGS: dict[str, tuple[int, int]] = {
    "voice/engine/llm/providers/nucleo.py": (3461, 155),
    "nucleo/dispatch.py": (1879, 57),
    "widgets/navegador/owner.py": (1580, 43),
    "nucleo/flash/router_guards.py": (1282, 15),
    "nucleo/flash/probe.py": (1168, 84),
    "widgets/results/data.py": (1062, 5),
    "memory/api.py": (1076, 19),
    "nucleo/flash/prompt.py": (843, 30),
    "nucleo/workers/session.py": (825, 19),
    "nucleo/flash/router.py": (928, 1),
}

#: No god file may be BORN either: any engine module NOT in the table stays under this. The largest unlisted
#: file today is `connectors/meshkore/bridge.py` at 863, so 900 bounds the whole rest of the tree with margin.
_UNLISTED_MAX = 900

#: The mirror annotation: the turn's decisions copied between the voice provider and probe, each marked «this
#: block lives in both, keep them in sync». 21 on the day of the audit, 18 after F1's first extraction (the
#: vault gate). Each retirement lowers this number; at 0 a NEW mirror is a red test — two channels needing the
#: same rule means extract first.
#:
#: ⚠️ The marker is a CODE ANNOTATION, not narration vocabulary, and the ratchet counts the literal string —
#: so prose ABOUT the pattern counts as the pattern. Caught the first time it mattered: the docstrings written
#: to explain a retired mirror pushed the count from 19 back to 22, i.e. the celebration read as a regression.
#: When you retire one, describe it without quoting the marker.
_MIRROR_MAX = 17

_SKIP_DIRS = {".venv", "tests", "node_modules", "__pycache__", ".git", "frontend/vendor"}


def _engine_py_files():
    for p in ENGINE.rglob("*.py"):
        rel = p.relative_to(ENGINE).as_posix()
        if any(part in _SKIP_DIRS for part in rel.split("/")):
            continue
        yield rel, p


def test_a_listed_file_only_shrinks():
    over = []
    for rel, (max_loc, _max_lazy) in _CEILINGS.items():
        p = ENGINE / rel
        assert p.exists(), f"{rel} está en la tabla y no en el disco: si se partió, baja su techo o retíralo"
        n = _loc(p)
        if n > max_loc:
            over.append(f"{rel}: {n} > {max_loc}")
    assert not over, ("un fichero-dios ha CRECIDO — el trinquete pide extraer un módulo, no subir el techo:\n  "
                      + "\n  ".join(over))


def test_no_god_file_is_born_outside_the_table():
    born = []
    for rel, p in _engine_py_files():
        if rel in _CEILINGS:
            continue
        n = _loc(p)
        if n > _UNLISTED_MAX:
            born.append(f"{rel}: {n} LOC")
    assert not born, ("un fichero nuevo nació gigante — trocéalo antes de que herede la tabla:\n  "
                      + "\n  ".join(born))


def test_hidden_coupling_only_goes_down():
    over = []
    for rel, (_max_loc, max_lazy) in _CEILINGS.items():
        n = _lazy_imports(ENGINE / rel)
        if n > max_lazy:
            over.append(f"{rel}: {n} imports lazy > {max_lazy}")
    assert not over, ("más imports dentro de funciones = más ciclos tapados. Se arregla EXTRAYENDO, no importando "
                      "más tarde:\n  " + "\n  ".join(over))


def test_no_new_parallel_mirror():
    hits = []
    for rel, p in _engine_py_files():
        try:
            n = p.read_text().count("impl PARALELA")
        except Exception:
            continue
        if n:
            hits.append((rel, n))
    total = sum(n for _r, n in hits)
    assert total <= _MIRROR_MAX, (
        f"{total} marcas de «impl PARALELA» (techo {_MIRROR_MAX}). Un espejo NUEVO está vetado: si dos canales "
        f"necesitan la misma decisión, se extrae a un módulo y ambos lo importan. Dónde están: {hits}")


def test_every_testmap_node_id_is_unique():
    """El id de un nodo es cómo se le referencia desde CLAUDE.md y las iniciativas. Dos nodos con el mismo id son
    dos cosas afirmando ser la misma: el 2026-08-23 había CINCO pares así (2.14, 2.15, 7.10, 7.11, 7.13), y el
    sexto estuvo a punto de entrar sin que nadie lo viera. Se renumeraron los cinco menos citados."""
    from tests.platform.catalog import DOMAINS

    seen: dict[str, str] = {}
    dups = []
    for d in DOMAINS:
        for node in d.get("nodes", []):
            nid = node["id"]
            if nid in seen:
                dups.append(f"{nid}: «{seen[nid][:50]}» vs «{node['title'][:50]}»")
            seen[nid] = node["title"]
    assert not dups, "ids de nodo duplicados en el testmap:\n  " + "\n  ".join(dups)


def test_process_identity_has_ONE_owner():
    """F5. Three incidents in 48h had the same shape — a per-instance counter read as global: `escalate._seq`
    keyed the sheet and a restart wiped the previous session's results (32c7dc6); the relay booleans lived on a
    record every relay renews, so six workers ran one errand (0399a1d). The fixes landed where they hurt; this
    closes the CLASS: a module-level sequence counter born anywhere but `nucleo/runtime_ids.py` goes red with a
    name. `itertools.count()` at module level counts too — it is the same pattern wearing a nicer coat."""
    import re
    pat = re.compile(r"^_?[a-z_]*(?:seq|counter)[a-z_]*\s*=\s*(?:0|itertools\.count)", re.M)
    born = []
    for rel, p in _engine_py_files():
        if rel == "nucleo/runtime_ids.py":
            continue
        try:
            src = p.read_text()
        except Exception:
            continue
        for m in pat.finditer(src):
            line = src[:m.start()].count("\n") + 1
            born.append(f"{rel}:{line}: {m.group(0).strip()}")
    assert not born, ("un contador de módulo nació fuera del dueño — usa runtime_ids.next_seq(name), y si el id "
                      "debe sobrevivir a un reinicio, compón boot_id():\n  " + "\n  ".join(born))
