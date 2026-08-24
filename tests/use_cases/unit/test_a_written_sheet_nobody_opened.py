"""V2-292 — una caja ESCRITA y nunca abierta no la ve el operador, y hasta hoy tampoco la veía este informe.

`sheet_instances` contaba solo los `show`, y esa era toda la pregunta hasta que dejó de serlo. Medido en la tanda
del 2026-08-24 13:11, `search-buy-guitar__es`: en disco quedaron TRES cajas de ese caso —19, 45 y 12 filas, las
dos últimas tituladas con frases de la CONVERSACIÓN («Ah, bien. ¿Y sabes si están cerca…», «Sí, porfa. Yo estoy
en Madrid…»)— y solo la primera tenía `show`. El informe dijo **«18 candidatos»** sobre **76 que existían**.

Son DOS hechos distintos y el que importa es el HUECO entre ellos:

  · ABIERTA  → el operador la tiene delante.
  · ESCRITA  → sus filas existen y son de este encargo.

Sumarlas sin decir nada convertiría el defecto en un número más alto, que es la manera de esconderlo. Por eso el
lector de la hoja lee TODAS las escritas —«entregó 18» y «entregó 76 repartidas en tres cajas, dos invisibles»
son dos veredictos distintos sobre el mismo caso— y el juez recibe el hueco NOMBRADO, con la advertencia de que
es del MECANISMO: si zaelar nombró un candidato que está en una caja invisible, lo tenía y lo dijo bien.
"""
from tests.use_cases.e2e.agent import judge, verify


def _ev(label, wid, src="worker:1"):
    return {"cat": "widget", "label": label, "id": wid, "src": src}


def test_a_box_written_without_being_shown_is_reported_apart():
    """EL CASO MEDIDO: tres cajas escritas, una sola abierta."""
    out = verify.sheet_instances([
        _ev("show", "results::a-1"), _ev("data", "results::a-1"),
        _ev("data", "results::a-4"), _ev("data", "results::a-6"),
    ])
    assert out["ids"] == ["results::a-1"]                       # lo ABIERTO no cambia
    assert out["n_unseen"] == 2
    assert out["unseen_ids"] == ["results::a-4", "results::a-6"]
    assert out["written_ids"] == ["results::a-1", "results::a-4", "results::a-6"]


def test_the_two_facts_do_not_get_mixed():
    """`n_sheets` sigue contando CAJAS ABIERTAS. Inflarlo con las invisibles borraría la pregunta que contesta."""
    out = verify.sheet_instances([_ev("show", "results::a-1"), _ev("data", "results::a-4")])
    assert out["n_sheets"] == 1
    assert out["n_unseen"] == 1


def test_a_box_both_written_and_shown_is_not_invisible():
    """La contraria, y sin ella «hay cajas invisibles» se cumple con cualquier escritura."""
    out = verify.sheet_instances([_ev("show", "results::a-1"), _ev("data", "results::a-1")])
    assert out["n_unseen"] == 0
    assert out["unseen_ids"] == []


def test_a_clean_round_says_nothing_about_invisible_boxes():
    """Un aviso que sale siempre deja de ser un aviso."""
    mech = {"sheet_instances": verify.sheet_instances([_ev("show", "results::a-1"), _ev("data", "results::a-1")])}
    assert "NADIE LAS ABRIÓ" not in judge.mechanism_facts(mech)


def test_the_judge_is_told_and_told_whose_fault_it_is():
    """El hueco se NOMBRA, con sus ids, y se le dice que es del MECANISMO: sin esa mitad, el juez apunta a las
    respuestas de zaelar por filas que él sí tenía (la familia de `el instrumento acusa al producto`)."""
    mech = {"sheet_instances": verify.sheet_instances([
        _ev("show", "results::a-1"), _ev("data", "results::a-4"), _ev("data", "results::a-6")])}
    txt = judge.mechanism_facts(mech)
    assert "NADIE LAS ABRIÓ" in txt
    assert "results::a-4" in txt and "results::a-6" in txt
    assert "MECANISMO" in txt
    assert "los tenía y los dijo bien" in txt
