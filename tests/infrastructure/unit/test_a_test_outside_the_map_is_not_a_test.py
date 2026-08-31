"""A test file that no suite runs quietly stops being true (V2-245).

There are THREE ways to disappear, and all three were measured on 2026-08-21, on the same day:

  1. **Unmapped.** 14 of my files, 183 passing tests that `tests run all` did not execute—including the ones I
     had just written for V2-243, meaning that the “green suite” I reported did not cover them. And one had been
     BROKEN since the V2-098 refactor without anyone noticing.
  2. **Mapped to a `live` node.** memoria-dev flagged this after auditing its own (37 unmapped): `deterministic_paths`
     skips live nodes, so attaching a deterministic file to one REMOVES it from the run. Mapping to the wrong node
     looks a lot like not mapping it.
  3. **In a chapter that no suite claims.** The one nobody would have looked for: `deterministic_paths` filters by
     the union of the suites’ `domain_ids`, so an entire chapter that does not appear in any of them is left out
     even if its nodes are perfect.

This is the V2-158 failure—“a test that no suite runs is a test that quietly stops being true”—and it has already
recurred three times. A guard that checked only PRESENCE would certify exactly the failure it exists to prevent:
that is why it checks all three.
"""
import io
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.platform.catalog import DOMAINS, SUITES, deterministic_paths  # noqa: E402

#: Trees that this ratchet does NOT watch, with the reason. A guard its owner does not expect is a guard that gets
#: bypassed immediately, so this only grows with the owner's OK—and the goal is for it to be EMPTY.
#:
#: **Today it is empty, and that is its correct state.** `tests/use_cases/` was here for a few hours on 2026-08-21,
#: twice and for two different reasons: first its `suite.json` with `"domain_ids": []`—36 declared files that were
#: not run, deterministic paths 277 → 313 after fixing it (`f0096c`)—and, when it was emptied, 15 of its files
#: emerged as undeclared in any node. Its owner closed both issues; he wrote the fifteen nodes, with their titles.
FUERA_DEL_TRINQUETE: tuple[str, ...] = ()


def _ficheros_de_test() -> list[str]:
    out = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, "tests")):
        if "__pycache__" in base:
            continue
        for f in files:
            if not (f.startswith("test_") and f.endswith(".py")):
                continue
            rel = os.path.relpath(os.path.join(base, f), ROOT)
            if not any(rel.startswith(x) for x in FUERA_DEL_TRINQUETE):
                out.append(rel)
    return sorted(out)


def _declarados() -> dict[str, str]:
    """path → ID of the node that declares it."""
    out = {}
    for d in DOMAINS:
        for n in d["nodes"]:
            for p in n.get("paths", ()):
                out.setdefault(p, f"{n['id']} ({'live' if n.get('live') else 'determinista'})")
    return out


def test_todo_fichero_de_test_esta_EN_EL_MAPA():
    faltan = [p for p in _ficheros_de_test() if p not in _declarados()]
    assert not faltan, (
        f"{len(faltan)} ficheros de test no están en `tests/run_testmap.py`, así que `tests run all` NO los "
        f"ejecuta: {faltan[:12]}{' …' if len(faltan) > 12 else ''}")


def test_y_ADEMAS_lo_ejecuta_la_corrida_determinista():
    """Being in the map is not enough: it must be in the run. Covers forms 2 and 3 at once, because both
    end the same way—the file does not appear in `deterministic_paths`—and the message says which one it is."""
    det = set(deterministic_paths("all"))
    decl = _declarados()
    fuera = [(p, decl[p]) for p in _ficheros_de_test() if p in decl and p not in det]
    assert not fuera, (
        "estos ficheros están declarados y aun así la corrida determinista no los toca — o cuelgan de un nodo "
        f"`live`, o su capítulo no lo reclama ninguna suite: {fuera[:12]}")


def test_TODO_capitulo_del_mapa_lo_reclama_alguna_suite():
    """The third form, watched where it originates. Without this, an entire chapter disappears from the run and its
    nodes continue to look perfect—which is exactly what happened to chapter 10 until `f0096c9`."""
    reclamados = {d for s in SUITES.values() for d in s.domain_ids}
    huerfanos = sorted((d["id"], d["name"]) for d in DOMAINS if d["id"] not in reclamados)
    assert not huerfanos, (
        f"capítulos del testmap que ninguna suite reclama (sus ficheros no los corre nadie): {huerfanos}")


@pytest.mark.parametrize("ruta", ["tests/agent_headless/unit/flash/test_provider_chain.py",
                                  "tests/cluster/unit/test_brain_relay.py"])
def test_los_que_estaban_invisibles_HOY_corren(ruta):
    """Named, concrete sensitivity: the two worst cases from the audit. `test_provider_chain` had
    22 passing cases that were not run—including those from V2-243—and `test_brain_relay` had also been BROKEN since V2-098."""
    assert ruta in set(deterministic_paths("all"))
