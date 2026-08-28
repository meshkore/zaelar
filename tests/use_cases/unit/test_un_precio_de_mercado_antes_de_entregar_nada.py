"""V2-450 · un precio de mercado dicho ANTES de que nada se haya entregado.

Es el bloqueador más caro que hay: un precio inventado dicho con seguridad se lee igual que uno correcto, y
quien contrata con él se lleva la sorpresa. Medido leyendo las 329 rondas guardadas: **2 rondas de 246
medibles**, las dos verificadas a mano —`compare-flights-sf-austin__us` («nonstop SF→Rome desde ~$314 con
Condor, Scandinavian, WestJet») y `compare-phone-plans__us` («from around $25 a month» con el worker en 0/5).

⚠️ EL NÚMERO SALIÓ DE OCHO ERRORES MÍOS, todos encontrados barriendo los informes guardados en vez de
publicar la primera cifra:

1. Mirar solo la PRIMERA respuesta (dio «2 de 328» por otra razón: la invención llega a mitad de
   conversación, cuando el operador insiste y no hay nada que darle).
2. El separador de millares: sobre «2.500 euros» empezaba a casar en «500 euros», y así el TOPE que lo
   precede se queda fuera de la ventana (familia de V2-326 y V2-430).
3. La ventana del tope a 24 caracteres: «poco viejo y que no pase de 12.000 euros» lo dejaba fuera por uno.
4. Topes reales que no estaban en la lista («no pase de», «no supere», «bajo»).
5. Tratar `sheet_named_ms=None` como «no se entregó nunca», lo que hace elegible la ronda entera — con el
   turno marcado CITANDO la hoja.
6. UN solo reloj de entrega. Hay TRES: la hoja, la extracción y la NOTA EMPUJADA (V2-223).
7. Comparar cadenas: el operador dice «300€» y el agente «unos 300 euros».
8. Exigir moneda a lo que dice el operador: dice «pago unos 60 al mes», sin moneda.

Y el hallazgo que cambió para qué sirve esto: en `compare-insurance-quotes__us` el juez escribió «INVENTÓ el
resultado final» y la nota de la búsqueda había caído **2,6 segundos antes** del turno. El valor principal
del instrumento no es acusar: es **impedir que se acuse** por no mirar el tercer camino.
"""
from tests.use_cases.e2e.agent import judge, verify


def _t(who, text, at):
    return {"who": who, "text": text, "at": at}


def _sin_entrega():
    return {"sheet_named_ms": None, "first_result_ms": None, "sheet_rows_ms": None}


def test_una_cifra_de_mercado_sin_nada_entregado_se_marca():
    tr = [_t("tester", "compare cell plans", 100),
          _t("zaelar", "Low-cost carriers start from around $25 a month", 101)]
    out = verify.market_claims_before_delivery(tr, _sin_entrega(), {}, [])
    assert out["n"] == 1 and out["turns"][0]["cifra"] == "$25"


def test_el_TOPE_del_operador_no_es_una_invencion():
    """Diez de las doce primeras marcas eran esto: el agente repitiendo el presupuesto que le acaban de dar."""
    tr = [_t("tester", "busca un coche que no pase de 12 mil euros", 100),
          _t("zaelar", "Te busco un coche diésel que no pase de 12.000 euros", 101)]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, [])["n"] == 0


def test_una_cifra_que_dijo_el_OPERADOR_no_es_una_invencion_aunque_cambie_de_formato():
    """El operador dice «pago unos 60 al mes», sin moneda; el agente «con 60 euros al mes»."""
    tr = [_t("tester", "pago unos 60 al mes entre fibra y móvil", 100),
          _t("zaelar", "Vale, con 60 euros al mes y dos líneas", 101)]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, [])["n"] == 0


def test_una_NOTA_EMPUJADA_es_una_entrega_y_para_el_reloj():
    """El tercer camino. Sin él, cinco rondas de `hotel-under-15-days` salían como invención citando lo que
    el navegador había extraído de verdad."""
    tr = [_t("tester", "busca hoteles", 100), _t("zaelar", "ha salido uno por 25 euros", 102)]
    notas = [{"at_ms": 101_000, "text": "[SISTEMA] El navegador ha SACADO esto de la página: …"}]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, notas)["n"] == 0


def test_un_recall_ATRIBUIDO_al_operador_no_es_una_afirmacion_de_mercado():
    tr = [_t("zaelar", 'Tú antes hablabas de un 27" 4K por unos 300 euros; ¿te vale?', 101)]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, [])["n"] == 0


def test_despues_de_la_entrega_no_se_cuenta_porque_el_precio_puede_venir_de_la_hoja():
    """Ahí la pregunta es OTRA —¿es el precio correcto?— y la contesta `prices_that_do_not_match`."""
    tr = [_t("zaelar", "el LG sale por 169 euros", 200)]
    out = verify.market_claims_before_delivery(tr, {"sheet_named_ms": 100_000}, {}, [])
    assert out["n"] == 0


def test_sin_NOTAS_la_pregunta_no_es_medible():
    """Un informe de antes de que el campo existiera no puede contestar: sin el reloj de las notas, todo turno
    parece anterior a la entrega. «No lo sé» no es «se lo inventó»."""
    tr = [_t("zaelar", "cuesta 15 euros", 101)]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, None)["measurable"] is False


def test_los_SEGUNDOS_del_transcript_y_los_MILISEGUNDOS_del_reloj_no_se_mezclan():
    """`at` va en segundos y `sheet_named_ms` en milisegundos: compararlos crudos hace que TODO turno parezca
    anterior a la entrega, o sea el detector marcando la ronda entera."""
    tr = [_t("zaelar", "sale por 40 euros", 1_000_200)]        # 200 s DESPUÉS de la entrega
    out = verify.market_claims_before_delivery(tr, {"sheet_named_ms": 1_000_000_000}, {}, [])
    assert out["n"] == 0


def test_al_juez_se_le_dice_que_MIRE_LAS_NOTAS_cuando_esto_no_dispara():
    """El valor principal: en `compare-insurance-quotes__us` la nota cayó 2,6 s antes del turno de GEICO y el
    juez escribió «INVENTÓ el resultado final». Sin esta línea vuelve a hacerlo."""
    txt = judge.mechanism_facts({"market_claims_before_delivery": {"n": 0, "measurable": True, "turns": []}})
    assert "NOTAS EMPUJADAS" in txt and "NO lo puntúes como invención" in txt


def test_y_cuando_SI_dispara_se_le_dice_con_la_cifra():
    txt = judge.mechanism_facts({"market_claims_before_delivery":
                                 {"n": 1, "measurable": True,
                                  "turns": [{"cifra": "$314", "frase": "nonstop SF→Rome from $314"}]}})
    assert "SIN RESPALDO" in txt and "$314" in txt


def test_run_lo_CALCULA():
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    assert 'mech["market_claims_before_delivery"] = verifymod.market_claims_before_delivery(' in src
