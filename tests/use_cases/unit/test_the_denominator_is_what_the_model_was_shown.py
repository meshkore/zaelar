"""«¿Entregó lo que TENÍA?» se medía contra la hoja, y al modelo no se le enseña la hoja entera.

`delivery_completeness` (V2-332) prometía en su primera línea medir «de las filas VÁLIDAS que el sistema **le
puso delante**», y dividía por TODA la hoja. Cuando se escribió, la hoja de la ronda medida tenía cinco filas
y las dos cosas eran la misma; dejaron de serlo en cuanto las hojas crecieron.

`live_blocks._sheet_top_rows` empuja **como mucho 5** filas al prompt («bounded hard, because this lands in a
prompt, not on a screen»). Medido el 2026-08-28 en `search-buy-used-car`: hoja de 28, prompt con 5, el modelo
nombró 3 — y el informe lo publicó como **«retención masiva de información, 11 %»** con una lista de `missed`
llena de coches que nunca estuvieron en ningún prompt. La obediencia PERFECTA habría dado 18 %. Un agente
leyendo eso persigue una retención que no existe: el instrumento acusando al producto otra vez.

La diferencia entre las dos cifras no se tira — se publica aparte (`in_sheet`), porque «cuánto de lo que
tenemos no le enseñamos» es un hallazgo sobre NOSOTROS y de los buenos.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import verify as V

_HEAD = "LO QUE YA HA ENTREGADO (nombre y precio, de la hoja): "


def _turno(*filas: str) -> dict:
    """Un turno tal y como lo devuelve `prompt_context`: las filas viajan DENTRO de `live_line`."""
    return {"turn": 0, "live_line": ("TAREAS DE FONDO EN CURSO · la tarea YA HA ENCONTRADO algo. " + _HEAD
                                     + "; ".join(filas) + ". OJO: la hoja guarda TODO lo que dio la página")}


def test_lee_del_prompt_las_filas_que_tuvo_delante():
    got = V.shown_candidates([_turno("MINI Cooper F55 2016 — 11.700 €", "Audi Q5 2015 — 11.990 €")])
    assert got == ["MINI Cooper F55 2016", "Audi Q5 2015"]


def test_un_turno_sin_filas_no_aporta_ninguna():
    """La mitad de sensibilidad: sin esto «lee las filas» y «se inventa filas» pasan igual."""
    assert V.shown_candidates([{"live_line": "TAREAS DE FONDO EN CURSO · sigue buscando"}]) == []
    assert V.shown_candidates([]) == []
    assert V.shown_candidates(None) == []


def test_las_filas_se_unen_entre_turnos_sin_repetirse():
    got = V.shown_candidates([_turno("MINI Cooper — 11.700 €"), _turno("MINI Cooper — 11.700 €",
                                                                       "FIAT Panda 4x4 — 6.900 €")])
    assert got == ["MINI Cooper", "FIAT Panda 4x4"]


def test_el_denominador_es_lo_mostrado_no_la_hoja():
    """EL CASO REAL: hoja de 28, prompt con 5, nombró 3. 60 %, no 11 %."""
    hoja = {"n_named": 28, "titles": [f"coche {i}" for i in range(28)]}
    dichas = {"n": 3, "names": ["coche 0", "coche 1", "coche 2"]}
    got = V.delivery_completeness(dichas, hoja, ["coche 0", "coche 1", "coche 2", "coche 3", "coche 4"])
    assert got["available"] == 5 and got["pct"] == 60
    assert got["in_sheet"] == 28, "lo que TENEMOS y no le enseñamos se publica aparte, no se tira"
    assert got["shown_to_model"] is True


def test_no_se_acusa_de_saltarse_lo_que_nunca_estuvo_en_un_prompt():
    hoja = {"n_named": 28, "titles": [f"coche {i}" for i in range(28)]}
    dichas = {"n": 1, "names": ["coche 0"]}
    got = V.delivery_completeness(dichas, hoja, ["coche 0", "coche 1"])
    assert got["missed"] == ["coche 1"], "solo lo que tuvo delante y no dijo"


def test_sin_contexto_de_prompt_se_comporta_como_antes():
    """Compatibilidad hacia atrás: una ronda vieja o un fallo al leer el prompt no puede quedarse sin métrica.
    Se marca con `shown_to_model=False` para que nadie confunda las dos denominaciones."""
    hoja = {"n_named": 5, "titles": [f"coche {i}" for i in range(5)]}
    got = V.delivery_completeness({"n": 3, "names": ["coche 0", "coche 1", "coche 2"]}, hoja, None)
    assert got["available"] == 5 and got["pct"] == 60 and got["shown_to_model"] is False


def test_la_linea_viva_se_captura_entera_para_que_las_filas_quepan():
    """A 400 caracteres el recorte cortaba justo donde empiezan las filas, y entonces `shown_candidates`
    devuelve vacío siempre — que se lee como «no se le mostró nada» y es lo contrario de la verdad."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/verify.py").read_text(encoding="utf-8")
    assert '"live_line": live[:1200]' in src


# ── Y que el JUEZ lo sepa, que es la mitad que decide la nota ───────────────────────────────────────────────
def test_al_juez_se_le_dice_que_hay_filas_que_nunca_vio():
    """Arreglar el número sin decírselo al juez no arregla nada: la nota la pone él.

    Sin esta frase escribía «retención masiva del 11 %» sobre un modelo que había nombrado 3 de las 5 que le
    enseñamos, con una lista de «lo que se dejó» llena de coches que nunca estuvieron en ningún prompt.
    """
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"delivery_completeness": {"named": 3, "available": 5, "in_sheet": 28,
                                                          "pct": 60, "missed": ["coche 3", "coche 4"]}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "TUVO DELANTE 5" in txt and "60 %" in txt
    assert "28" in txt and "23 NUNCA llegaron a su prompt" in txt
    assert "límite NUESTRO" in txt


def test_y_no_se_le_avisa_cuando_lo_vio_todo():
    """La mitad de sensibilidad: un aviso que sale siempre deja de ser un aviso."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"delivery_completeness": {"named": 3, "available": 5, "in_sheet": 5,
                                                          "pct": 60, "missed": ["coche 3"]}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NUNCA llegaron a su prompt" not in txt


# ── Y que el recorte no se lo coma, que es como el arreglo estuvo INERTE ────────────────────────────────────
def test_las_filas_se_leen_de_su_CAMPO_y_no_de_la_prosa_recortada():
    """Medido el 2026-08-28, con V2-420 ya desplegado y midiendo: `shown_to_model` salía **False en las seis
    rondas**. La causa no era el denominador — era que las filas vivían dentro de `live_line`, que va
    recortada a 1200 caracteres, y la lista de TAREAS ya llega sola a ese tope: el bloque de filas empieza más
    allá del corte. `shown_candidates` devolvía vacío siempre, o sea «no se le mostró nada», que es lo
    contrario de la verdad y tiene la pinta exacta de un arreglo funcionando.

    Subir el tope solo mueve el problema al siguiente prompt largo. Un campo no se recorta por accidente.
    """
    # La forma REAL del dato recortado: la cabecera de filas NO está en `live_line`, porque el corte cayó
    # antes. Un fixture que la deje dentro no reproduce nada — medido al desarmarlo: con la cabecera presente
    # el test seguía verde leyendo solo la prosa, o sea sobre el defecto restaurado.
    turno = {"live_line": "TAREAS DE FONDO EN CURSO: " + ("x" * 1174),      # 1200 justos, sin llegar a filas
             "sheet_rows": ["MINI Cooper"]}
    assert _HEAD not in turno["live_line"]
    assert V.shown_candidates([turno]) == ["MINI Cooper"]


def test_un_informe_ANTERIOR_al_campo_se_sigue_leyendo():
    """La rama de la prosa no se tira: los informes ya guardados no tienen `sheet_rows` y siguen siendo la
    única evidencia de sus rondas."""
    viejo = {"live_line": "TAREAS DE FONDO EN CURSO. " + _HEAD + "FIAT Panda 4x4 — 6.900 €. OJO: la hoja"}
    assert V.shown_candidates([viejo]) == ["FIAT Panda 4x4"]


def test_el_campo_lo_escribe_prompt_context_desde_la_linea_ENTERA():
    """La fontanería: si `prompt_context` no lo rellena, el campo existe y siempre está vacío."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/verify.py").read_text(encoding="utf-8")
    assert '"sheet_rows": _rows_in(live),' in src, "el campo no se escribe desde la línea completa"
    assert src.index('"sheet_rows": _rows_in(live),') > src.index("def _rows_in(")


def test_la_cabecera_que_buscamos_es_la_que_el_MOTOR_escribe():
    """Acoplamiento por TEXTO entre dos ficheros, y del que se rompe callado.

    `shown_candidates` localiza las filas empujadas buscando una frase literal del prompt. Si alguien
    reescribe esa frase en `live_blocks` —una coma, un «de la hoja» que se va—, la lectura devuelve vacío
    **para siempre**, y vacío aquí se lee como «no se le mostró nada», que es lo contrario de la verdad y
    tiene la pinta exacta de un arreglo funcionando. Ya pasó una vez esta misma noche por otro motivo (el
    recorte de `live_line`), y costó cuatro horas de rondas medidas con el denominador viejo.

    Esto no es elegante y es lo correcto disponible: mientras el dato viaje dentro de una frase, alguien
    tiene que vigilar la frase.
    """
    from pathlib import Path
    motor = Path("nucleo/flash/live_blocks.py").read_text(encoding="utf-8")
    assert V._ROWS_HEAD in motor, (
        "la cabecera de filas del prompt cambió y el arnés sigue buscando la vieja: `shown_candidates` "
        "devolverá vacío en todas las rondas, que se lee como «no se le mostró nada»")
