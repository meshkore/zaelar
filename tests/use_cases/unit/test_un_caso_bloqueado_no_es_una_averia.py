"""V2-448 · un caso de FUTURO no es una avería del arnés, ni un turno que gastar cada vuelta.

El runner se niega a conducir un escenario cuyas tareas de roadmap siguen pendientes (norma del operador,
2026-08-21: «así ahora mismo jamás lo ejecutarías, porque sabrías que esas tareas están pendientes»), imprime
por qué y sale. Eso son 3 segundos y CERO medida.

El supervisor lo archivaba como **INFRA**, que es la etiqueta de «el instrumento se rompió» y manda a mirar
donde no hay nada roto — la misma lección de V2-363 un escalón más abajo: la ausencia de medida tiene varias
causas y no sirven para lo mismo. Y como un caso bloqueado nunca llega al marcador, la rama de
«nunca medidos» (V2-367) volvía a elegirlo **en cada vuelta, para siempre**.

Medido el 2026-08-28: `repeat-a-finished-search`, pendiente de V2-260 F1 y F2, INFRA de 3 segundos en el
diario del plató 24/7.
"""
from tests.use_cases.e2e.agent import supervisor as S


def test_el_diario_lo_llama_BLOQUEADO_y_no_INFRA():
    cola = ("⏳ 1 caso(s) de FUTURO, no se conducen (usa --include-blocked para forzarlo):\n"
            "   · repeat-a-finished-search ← pendiente de V2-260 F1, V2-260 F2\n"
            "no queda ningún caso conducible en esta selección\n")
    assert S._veredicto_de_cola(cola) == "BLOQUEADO"


def test_una_averia_de_VERDAD_sigue_siendo_INFRA():
    """La mitad que impide que el arreglo esconda averías: si esto se tragara un INFRA real, el bucle dejaría
    de avisar de que el instrumento está roto — que es lo único que no se puede medir desde dentro.

    La cola es la del caso REAL de V2-363, con las DOS marcas: el runner imprime «PASSED 0/1» aunque la ronda
    se corriera entera y quien no contestara fuera el juez. Una cola con solo la marca de INFRA no prueba
    nada —caería en el `else`, que también es INFRA— y así estaba escrita la primera versión: verde con la
    rama BORRADA, comprobado desarmando.
    """
    cola = ("… 10,7 min de navegador; el juez no devolvió JSON tras tres intentos\n"
            "PASSED 0/1\n")
    assert S._veredicto_de_cola(cola) == "INFRA"


def test_un_caso_que_falla_sigue_siendo_FAIL():
    assert S._veredicto_de_cola("PASSED 0/1\n") == "FAIL"


def test_y_uno_que_pasa_sigue_pasando():
    assert S._veredicto_de_cola("PASSED 1/1\n") == "PASS"


def test_la_rotacion_NO_vuelve_a_elegir_un_caso_bloqueado():
    """Sin esto gasta un turno cada vuelta y deja una fila falsa cada vez. Mismo trato que los `capped`:
    trabajo que nadie puede cerrar hoy no entra en el bucle de mejora."""
    from tests.use_cases.e2e.agent import segments as G
    bloqueados = [s.id for s in S._con_runner() if G.blocked_by(s.id)]
    assert bloqueados, "el catálogo ya no tiene casos de futuro: este guarda dejó de medir algo"
    r = S.rotacion()
    assert not (set(bloqueados) & set(r)), f"un caso de futuro sigue en la rotación: {set(bloqueados) & set(r)}"
