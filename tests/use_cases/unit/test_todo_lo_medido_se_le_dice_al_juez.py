"""Todo lo que el arnés MIDE tiene que llegarle al juez EN PALABRAS — o estar exento con motivo (V2-399).

La clase está probada con medición, dos veces en dos días:
  · V2-395 — `widgets_producing` viajaba en el JSON crudo del prompt y el juez puntuó 2/5 «ni sonó la
    música» con la música sonando. En cuanto se dijo en palabras, la acusación desapareció.
  · V2-398 — `tool_calls` ni siquiera se guardaba; el juez dedujo del texto y dedujo mal.

Auditado el informe entero (2026-08-27): SEIS campos más estaban en ese estado. El peor,
`delivery_completeness`, decía en la ronda de Bilbao **«tenía 24 resultados y nombró 1 (4 %)»** — el hecho
central del veredicto— y solo existía en JSON. `worker_bridges` llevaba errores de puente dentro. El juez
ignora lo que no se le dice: está medido, no supuesto.

El arreglo no es añadir seis líneas: es el TRINQUETE. Cada campo que el informe produce, o se renderiza en
`mechanism_facts` (directo o por delegación a `verify`), o está en `judge.RAW_ONLY` con el motivo escrito.
Un campo nuevo sin decisión rompe este test — que es exactamente lo que les faltó a los seis.
"""
import ast
import re
from pathlib import Path

import pytest

from tests.use_cases.e2e.agent import judge as J

BASE = Path("tests/use_cases/e2e/agent")


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


# ── qué produce el informe (leído del CÓDIGO productor, no de un informe de ejemplo) ───────────────────────

def _campos_producidos() -> set[str]:
    campos: set[str] = set()
    vtree = ast.parse((BASE / "verify.py").read_text())
    fn = next(n for n in ast.walk(vtree) if isinstance(n, ast.FunctionDef) and n.name == "mechanism_report")
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            campos |= {k.value for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    rtree = ast.parse((BASE / "run.py").read_text())
    for n in ast.walk(rtree):
        if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Subscript)
                and isinstance(n.targets[0].value, ast.Name) and n.targets[0].value.id == "mech"
                and isinstance(n.targets[0].slice, ast.Constant)):
            campos.add(n.targets[0].slice.value)
    return campos


def _cadenas_de(tree: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _campos_visibles_para_el_juez() -> set[str]:
    """Cadenas del AST de judge.py (los comentarios NO cuentan: no son código) + las de cada función de
    `verify` a la que el juez delega (p. ej. `measured_in_flight` lee `quiescence` por él)."""
    jtree = ast.parse((BASE / "judge.py").read_text())
    # el propio diccionario RAW_ONLY no cuenta como «renderizado»: sus claves son cadenas del AST, y sin
    # excluirlas la prueba de exclusión mutua se contradice a sí misma (todo exento parecería también dicho)
    _raw_only_nodes = set()
    for n in ast.walk(jtree):
        if (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "RAW_ONLY"
                                              for t in n.targets)):
            _raw_only_nodes = {id(x) for x in ast.walk(n)}
    visibles = {c.value for c in ast.walk(jtree)
                if isinstance(c, ast.Constant) and isinstance(c.value, str) and id(c) not in _raw_only_nodes}
    delegadas = {n.func.attr for n in ast.walk(jtree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == "_V"}
    vtree = ast.parse((BASE / "verify.py").read_text())
    for fn in ast.walk(vtree):
        if isinstance(fn, ast.FunctionDef) and fn.name in delegadas:
            visibles |= _cadenas_de(fn)
    return visibles


def test_ningun_campo_del_informe_es_invisible_para_el_juez():
    producidos = _campos_producidos()
    assert len(producidos) > 30, "el lector de campos se ha roto: no puede haber tan pocos"
    visibles = _campos_visibles_para_el_juez()
    exentos = set(J.RAW_ONLY)
    invisibles = sorted(producidos - visibles - exentos)
    assert not invisibles, (
        f"campos MEDIDOS que el juez no puede ver ({len(invisibles)}): {invisibles}. "
        f"O se renderizan en mechanism_facts, o entran en judge.RAW_ONLY con el motivo escrito.")


def test_toda_exencion_lleva_su_motivo():
    for campo, motivo in J.RAW_ONLY.items():
        assert isinstance(motivo, str) and len(motivo) >= 20, f"«{campo}» está exento sin motivo real"


def test_una_exencion_no_puede_tapar_un_campo_que_ya_se_dice():
    """Si alguien renderiza un campo exento, la exención sobra y hay que quitarla — dos verdades derivan."""
    visibles = _campos_visibles_para_el_juez()
    de_mas = sorted(set(J.RAW_ONLY) & visibles)
    assert not de_mas, f"exentos Y renderizados a la vez: {de_mas}"


# ── los cuatro que la auditoría encontró mudos, ahora en palabras ──────────────────────────────────────────

def test_entrego_1_de_24_se_dice():
    txt = _texto(J.mechanism_facts({"delivery_completeness": {
        "named": 1, "available": 24, "pct": 4,
        "missed": ["Clase de surf en Laga", "Curso en Sopelana"]}}))
    assert "24" in txt and "ENTREGÓ" in txt.upper()
    assert "Sopelana" in txt


def test_entregarlo_todo_no_avisa():
    txt = _texto(J.mechanism_facts({"delivery_completeness": {"named": 5, "available": 5, "pct": 100,
                                                              "missed": []}}))
    assert "ENTREGÓ" not in txt.upper()


def test_encargos_duplicados_se_dicen():
    txt = _texto(J.mechanism_facts({"duplicate_errands": {
        "read": True, "worst": 3, "identical_repeats": 2,
        "groups": [{"n": 3, "goal": "buscar hotel en Bilbao", "identical": True}]}}))
    assert "DUPLICADO" in txt.upper() or "REPETIDO" in txt.upper()
    assert "buscar hotel en Bilbao" in txt


def test_encargos_limpios_no_dicen_nada():
    txt = _texto(J.mechanism_facts({"duplicate_errands": {"read": True, "worst": 0, "groups": [],
                                                          "identical_repeats": 0}}))
    assert "DUPLICADO" not in txt.upper() and "REPETIDO" not in txt.upper()


def test_errores_de_puente_se_dicen():
    txt = _texto(J.mechanism_facts({"worker_bridges": {
        "read": True, "sessions": 1, "by_bridge": {"nav_cli": 3}, "errors": {"nav_cli": 2}}}))
    assert "PUENTE" in txt.upper()
    assert "nav_cli" in txt


def test_puentes_sanos_callan():
    txt = _texto(J.mechanism_facts({"worker_bridges": {"read": True, "sessions": 2,
                                                       "by_bridge": {"nav_cli": 5}, "errors": {}}}))
    assert "PUENTE" not in txt.upper()


def test_un_lector_de_seccion_averiado_se_dice():
    """`prompt_context_error` y `proactive_notes_error` son la avería de V2-381 en pequeño: el lector de UNA
    sección revienta y su ausencia se leería como un hecho. El trinquete de arriba no basta aquí — cuenta que
    la cadena exista en el AST, no que el aviso DISPARE (un `if False` lo deja verde)."""
    txt = _texto(J.mechanism_facts({"prompt_context_error": "boom en sqlite"}))
    assert "no pudo componer" in txt and "prompt_context" in txt and "NO se puntúa" in txt
    txt2 = _texto(J.mechanism_facts({"proactive_notes_error": "columna que falta"}))
    assert "no pudo componer" in txt2 and "note_coverage" in txt2


def test_sin_averia_no_hay_aviso_de_averia():
    assert "no pudo componer" not in _texto(J.mechanism_facts({"results_sheet": {"n_named": 3}}))


def test_embeddings_degradados_se_dicen():
    txt = _texto(J.mechanism_facts({"embeddings": {"backend": "hash", "degraded": True, "skipped": False}}))
    assert "EMBEDDINGS" in txt.upper() or "MEMORIA SEMÁNTICA" in txt.upper()


def test_embeddings_sanos_callan():
    txt = _texto(J.mechanism_facts({"embeddings": {"backend": "ollama", "degraded": False,
                                                   "skipped": False}}))
    assert "EMBEDDINGS" not in txt.upper()
