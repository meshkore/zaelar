"""V2-448 · a FUTURE case is not a harness failure, nor a turn to spend on every cycle.

The runner refuses to drive a scenario whose roadmap tasks are still pending (operator rule,
2026-08-21: «you would never run it right now, because you would know those tasks are pending»), prints
why, and exits. That is 3 seconds and ZERO measurement.

The supervisor filed it as **INFRA**, which is the label for «the instrument broke» and sends you looking
where nothing is broken — the same lesson as V2-363 one level lower: the absence of a measurement has several
causes, and they are not interchangeable. And because a blocked case never reaches the scoreboard, the
«never measured» branch (V2-367) kept choosing it **on every cycle, forever**.

Measured on 2026-08-28: `repeat-a-finished-search`, pending V2-260 F1 and F2, 3-second INFRA in the
24/7 studio log.
"""
from tests.use_cases.e2e.agent import supervisor as S


def test_el_diario_lo_llama_BLOQUEADO_y_no_INFRA():
    cola = ("⏳ 1 caso(s) de FUTURO, no se conducen (usa --include-blocked para forzarlo):\n"
            "   · repeat-a-finished-search ← pendiente de V2-260 F1, V2-260 F2\n"
            "no queda ningún caso conducible en esta selección\n")
    assert S._veredicto_de_cola(cola) == "BLOQUEADO"


def test_una_averia_de_VERDAD_sigue_siendo_INFRA():
    """The half that keeps the fix from hiding failures: if this swallowed a real INFRA, the loop would stop
    warning that the instrument is broken — which is the one thing that cannot be measured from inside.

    The queue is that of the REAL V2-363 case, with BOTH markers: the runner prints «PASSED 0/1» even if the round
    ran to completion and the judge was the one that failed to answer. A queue with only the INFRA marker proves
    nothing —it would fall into the `else`, which is also INFRA— and that is how the first version was written:
    green with the branch DELETED, verified by dismantling it.
    """
    cola = ("… 10,7 min de navegador; el juez no devolvió JSON tras tres intentos\n"
            "PASSED 0/1\n")
    assert S._veredicto_de_cola(cola) == "INFRA"


def test_un_caso_que_falla_sigue_siendo_FAIL():
    assert S._veredicto_de_cola("PASSED 0/1\n") == "FAIL"


def test_y_uno_que_pasa_sigue_pasando():
    assert S._veredicto_de_cola("PASSED 1/1\n") == "PASS"


def test_la_rotacion_NO_vuelve_a_elegir_un_caso_bloqueado():
    """Without this, it spends a turn on every cycle and leaves a false queue entry each time. Same treatment as
    the `capped`: work that nobody can close today does not enter the improvement loop."""
    from tests.use_cases.e2e.agent import segments as G
    bloqueados = [s.id for s in S._con_runner() if G.blocked_by(s.id)]
    assert bloqueados, "el catálogo ya no tiene casos de futuro: este guarda dejó de medir algo"
    r = S.rotacion()
    assert not (set(bloqueados) & set(r)), f"un caso de futuro sigue en la rotación: {set(bloqueados) & set(r)}"
