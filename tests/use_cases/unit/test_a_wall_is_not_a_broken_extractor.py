"""V2-333 — una hoja vacía DETRÁS de un muro anti-robot no es un fallo de extracción.

El hecho ya viajaba en el informe (`navegador_task.walls_hit` y `last_wall`, con el SITIO), y al juez solo se
le decía cuándo NO había habido muro. Así que ante una hoja vacía concluía lo único que podía.

MEDIDO en `compare-insurance-quotes__es` (2026-08-26 01:39). La ronda recorrió rastreator, acierto, kelisto,
lineadirecta y mutua, chocó con verificaciones anti-robot, y el veredicto fue:

    «el bloqueador nº1 es el fallo grave en el mecanismo de extracción del navegador: el sistema no pudo leer
     ni un solo precio ni nombre de aseguradora»   → mecanismo 2

La MISMA ronda del mismo caso, cuatro horas antes, había sacado **ocho opciones reales con mecanismo 4**. Lo
que cambió no fue el código: fue lo que los sitios dejaron pasar.

Y se comprobó que NO era una regresión nuestra: la extracción sobre `acierto.com` devuelve 9 filas idénticas
antes y después de toda la cadena V2-321…V2-326.

⚠️ NO exime de todo, y el bloque lo dice: lo que SÍ es puntuable es qué hizo zaelar con el obstáculo — si lo
dijo, si probó otro sitio, o si siguió narrando normalidad. Un muro explica la hoja vacía, no el silencio.
"""
from tests.use_cases.e2e.agent.judge import mechanism_facts


def test_sin_muros_no_se_menciona():
    txt = mechanism_facts({"navegador_task": {"walls_hit": 0}})
    assert "CERRÓ LA PUERTA" not in txt


def test_con_muros_se_dice_CUÁNTOS_y_DÓNDE():
    txt = mechanism_facts({"navegador_task": {
        "walls_hit": 3, "last_wall": {"site": "rastreator.com",
                                      "reason": "el sitio interpuso una verificación anti-robot"}}})
    assert "3 muro(s)" in txt
    assert "rastreator.com" in txt, "«me bloquearon» es un hecho; «me bloqueó rastreator» es accionable"
    assert "anti-robot" in txt


def test_y_se_le_PROHIBE_puntuarlo_como_fallo_de_extracción():
    txt = mechanism_facts({"navegador_task": {"walls_hit": 1, "last_wall": {"site": "x.com", "reason": "muro"}}})
    low = txt.lower()
    assert "no es un fallo de" in low and "extracción" in low
    assert "no puedes puntuarla" in low


def test_pero_NO_le_exime_de_juzgar_la_conducta():
    """La sensibilidad que evita convertir esto en una amnistía: un muro explica la hoja vacía, no el silencio."""
    txt = mechanism_facts({"navegador_task": {"walls_hit": 2, "last_wall": {"site": "y.com", "reason": "muro"}}})
    low = txt.lower()
    assert "sí es puntuable" in low
    assert "otro sitio" in low or "lo dijo" in low


def test_un_walls_hit_ilegible_no_rompe_el_informe():
    for malo in ("", None, "no-es-un-numero", {}):
        mechanism_facts({"navegador_task": {"walls_hit": malo}})


def test_sin_tarea_de_navegador_no_inventa_muros():
    assert "CERRÓ LA PUERTA" not in mechanism_facts({})
