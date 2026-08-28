"""Diez minutos de navegador apuntados como «el caso falla», y fue el JUEZ (V2-363).

Medido en `two-searches-two-sheets` (2026-08-27, ronda del supervisor). La conversación corrió ENTERA —641 s,
navegador real, dos encargos en vuelo— y el veredicto se perdió porque el juez no devolvió JSON válido tras
sus tres tentativas. Dos consecuencias, y las dos son del instrumento:

1. EL DIARIO LO APUNTÓ COMO `FAIL`. El runner imprime «PASSED 0/1» también cuando la ronda se corrió y no
   hubo veredicto, y el supervisor leía esa línea. El diario es la lista con la que se decide dónde trabajar y
   con la que se leen las tendencias: una avería del arnés metida ahí es el instrumento acusando al producto —
   el mismo defecto que V2-355 cortó en el reloj de retención, ahora en mi propio cuaderno.

2. Y NO SE PODÍA DIAGNOSTICAR. El error decía «Expecting ',' delimiter: line 22 column 6 (char 1159)» y el
   mensaje adjuntaba `raw[:200]` — los primeros doscientos caracteres, un JSON impecable, mil caracteres antes
   del sitio del fallo. Para ver la causa había que volver a correr diez minutos de navegador. Un fallo del
   instrumento que no deja ver su causa se repite entero cada vez.

Son la misma decisión con dos mitades: el arnés no puede convertir su avería en un veredicto del producto, ni
dejarla sin evidencia para arreglarla.
"""
from tests.use_cases.e2e.agent import supervisor as S


def _veredicto(cola: str) -> str:
    """La clasificación que hace el supervisor con la cola del log, aislada de correr una ronda."""
    if "PASSED 1/1" in cola:
        return "PASS"
    if "INFRA" in cola or "el juez no devolvió JSON" in cola:
        return "INFRA"
    if "PASSED 0/1" in cola:
        return "FAIL"
    return "INFRA"


def test_un_caso_que_de_verdad_falla_sigue_siendo_FAIL():
    assert _veredicto("  judging…\n✓ report → x.md\nPASSED 0/1 (overall>=4)") == "FAIL"


def test_un_caso_que_pasa_sigue_siendo_PASS():
    assert _veredicto("PASSED 1/1 (overall>=4)") == "PASS"


def test_el_juez_sin_JSON_es_INFRA_aunque_el_runner_imprima_PASSED_0_1():
    """La línea medida: las dos frases conviven en el mismo log y la de abajo llegaba primero al clasificador."""
    cola = ("[judge] el juez no devolvió JSON válido tras 3 intentos\n"
            "✓ report → x.md\nPASSED 0/1 (overall>=4)")
    assert _veredicto(cola) == "INFRA", "una avería del arnés en el diario decide dónde NO se trabaja"


def test_la_clasificacion_del_supervisor_es_LA_MISMA_que_esta():
    """Guarda contra la divergencia: si el supervisor cambia su orden y este test no, el test estaría
    afirmando una conducta que el código ya no tiene.

    V2-448 — la clasificación salió a `_veredicto_de_cola`, así que la guarda mira ESA función en vez de las
    líneas sueltas de la ronda. La propiedad no cambia y el ORDEN sigue siendo lo que se protege: «PASSED
    0/1» aparece también en la ronda que el juez no supo puntuar, así que INFRA tiene que ir antes que FAIL —
    y BLOQUEADO antes que INFRA, porque la cola de un caso de futuro no trae «PASSED» de ninguna clase y
    caería en el `else`, que es INFRA.
    """
    from pathlib import Path
    src = "\n".join(ln for ln in Path("tests/use_cases/e2e/agent/supervisor.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    i = src.index("def _veredicto_de_cola")
    cuerpo = src[i:i + 1400]
    assert "el juez no devolvió JSON" in cuerpo
    assert cuerpo.index('return "BLOQUEADO"') < cuerpo.index('return "INFRA"')
    assert cuerpo.index('return "INFRA"') < cuerpo.index('return "FAIL"'), \
        "el orden IMPORTA: «PASSED 0/1» aparece también en la ronda sin veredicto"


def test_el_error_del_juez_lleva_la_VENTANA_del_fallo_no_el_principio():
    """Sin esto, diagnosticar cuesta otra corrida entera de navegador."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("tests/use_cases/e2e/agent/judge.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    assert "alrededor del fallo" in src
    assert "raw[:200]" not in src, "el mensaje volvía a enseñar el principio, que es donde nunca está el error"
    assert "char (" in src or 'char (\\d+)' in src, "la posición sale del propio mensaje de la excepción"
