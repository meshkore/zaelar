"""Un fichero de test que ninguna suite ejecuta deja de ser verdad sin avisar (V2-245).

Hay TRES formas de desaparecer, y las tres se midieron el 2026-08-21 en el mismo día:

  1. **Sin mapear.** 14 ficheros míos, 183 tests verdes que `tests run all` no ejecutaba — incluidos los que
     acababa de escribir para V2-243, o sea que el «suite verde» que reporté no los cubría. Y uno llevaba ROTO
     desde el refactor de V2-098 sin que nadie lo viera.
  2. **Mapeado a un nodo `live`.** Lo avisó memoria-dev tras auditar la suya (37 sin mapear): `deterministic_paths`
     salta los nodos live, así que colgar un fichero determinista de uno lo SACA de la corrida. Mapear al nodo
     equivocado se parece mucho a no mapear.
  3. **En un capítulo que ninguna suite reclama.** La que nadie habría buscado: `deterministic_paths` filtra por
     la unión de los `domain_ids` de las suites, así que un capítulo entero que no aparezca en ninguna se queda
     fuera aunque sus nodos estén perfectos.

Es la avería de V2-158 —«un test que ninguna suite ejecuta es un test que deja de ser verdad sin avisar»— y ya
lleva tres reincidencias. Un guarda que solo comprobara PRESENCIA certificaría exactamente el fallo que existe
para evitar: por eso comprueba las tres.
"""
import io
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.platform.catalog import DOMAINS, SUITES, deterministic_paths  # noqa: E402

#: Árboles que este trinquete todavía NO vigila, con su motivo. Un guarda que su dueño no espera es un guarda que
#: se salta a la primera, así que esto solo crece con el OK del dueño — y el objetivo es que ADELGACE.
#: · `tests/use_cases/` es del arnés. El 2026-08-21 se le entregó medido que su `suite.json` lleva
#:   `"domain_ids": []`, así que sus 36 tests están declarados en el capítulo 10 y aun así no los corre nadie.
#:   Entra aquí en cuanto lo cierre y dé el OK.
FUERA_DEL_TRINQUETE = ("tests/use_cases/",)


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
    """ruta → id del nodo que la declara."""
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
    """Estar en el mapa no basta: hay que estar en la corrida. Cubre las formas 2 y 3 de una vez, porque las dos
    terminan igual —el fichero no aparece en `deterministic_paths`— y el mensaje dice cuál de las dos es."""
    det = set(deterministic_paths("all"))
    decl = _declarados()
    fuera = [(p, decl[p]) for p in _ficheros_de_test() if p in decl and p not in det]
    assert not fuera, (
        "estos ficheros están declarados y aun así la corrida determinista no los toca — o cuelgan de un nodo "
        f"`live`, o su capítulo no lo reclama ninguna suite: {fuera[:12]}")


def test_TODO_capitulo_del_mapa_lo_reclama_alguna_suite():
    """La tercera forma, vigilada donde se origina. Sin esto, un capítulo entero desaparece de la corrida y sus
    nodos siguen pareciendo perfectos — que es exactamente lo que le pasa hoy al capítulo 10."""
    reclamados = {d for s in SUITES.values() for d in s.domain_ids}
    huerfanos = sorted((d["id"], d["name"]) for d in DOMAINS
                       if d["id"] not in reclamados and d["id"] not in ("10",))
    assert not huerfanos, (
        f"capítulos del testmap que ninguna suite reclama (sus ficheros no los corre nadie): {huerfanos}")


@pytest.mark.parametrize("ruta", ["tests/agent_headless/unit/flash/test_provider_chain.py",
                                  "tests/cluster/unit/test_brain_relay.py"])
def test_los_que_estaban_invisibles_HOY_corren(ruta):
    """Sensibilidad con nombre y apellidos: los dos peores casos de la auditoría. `test_provider_chain` llevaba
    22 casos verdes sin correr —incluidos los de V2-243— y `test_brain_relay` llevaba además ROTO desde V2-098."""
    assert ruta in set(deterministic_paths("all"))
