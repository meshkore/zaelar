"""V2-450 · a market price stated BEFORE anything has been delivered.

It is the costliest blocker there is: a confidently stated invented price reads the same as a correct one, and
whoever makes a purchase based on it gets an unpleasant surprise. Measured by reading the 329 stored runs: **2
runs out of 246 measurable ones**, both manually verified —`compare-flights-sf-austin__us` («nonstop SF→Rome desde
~$314 con Condor, Scandinavian, WestJet») and `compare-phone-plans__us` («from around $25 a month» con el worker en 0/5).

⚠️ THE NUMBER CAME FROM EIGHT MISTAKES OF MINE, all found by scanning the stored reports instead of
publishing the first figure:

1. Looking only at the FIRST response (it yielded «2 de 328» for another reason: the invention arrives halfway
   through the conversation, when the operator insists and there is nothing to give them).
2. The thousands separator: for «2.500 euros» it started matching at «500 euros», leaving the LIMIT that
   precedes it outside the window (V2-326 and V2-430 family).
3. The limit window at 24 characters: «poco viejo y que no pase de 12.000 euros» put it outside by one.
4. Real limits that were not in the list («no pase de», «no supere», «bajo»).
5. Treating `sheet_named_ms=None` as «it was never delivered», which makes the entire run eligible — with the
   turn marked as CITING the sheet.
6. A single delivery clock. There are THREE: the sheet, the extraction, and the PUSHED NOTE (V2-223).
7. Comparing strings: the operator says «300€» and the agent «unos 300 euros».
8. Requiring a currency for what the operator says: they say «pago unos 60 al mes», without a currency.

And the finding that changed what this is for: in `compare-insurance-quotes__us` the judge wrote «INVENTÓ el
resultado final» and the search note had arrived **2.6 seconds before** the turn. The instrument's main value
is not to accuse: it is to **prevent an accusation** caused by failing to check the third path.
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
    """Ten of the first twelve marks were this: the agent repeating the budget it had just been given."""
    tr = [_t("tester", "busca un coche que no pase de 12 mil euros", 100),
          _t("zaelar", "Te busco un coche diésel que no pase de 12.000 euros", 101)]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, [])["n"] == 0


def test_una_cifra_que_dijo_el_OPERADOR_no_es_una_invencion_aunque_cambie_de_formato():
    """The operator says «pago unos 60 al mes», without a currency; the agent «con 60 euros al mes»."""
    tr = [_t("tester", "pago unos 60 al mes entre fibra y móvil", 100),
          _t("zaelar", "Vale, con 60 euros al mes y dos líneas", 101)]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, [])["n"] == 0


def test_una_NOTA_EMPUJADA_es_una_entrega_y_para_el_reloj():
    """The third path. Without it, five `hotel-under-15-days` runs were reported as inventions while citing what
    the browser had actually extracted."""
    tr = [_t("tester", "busca hoteles", 100), _t("zaelar", "ha salido uno por 25 euros", 102)]
    notas = [{"at_ms": 101_000, "text": "[SISTEMA] El navegador ha SACADO esto de la página: …"}]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, notas)["n"] == 0


def test_un_recall_ATRIBUIDO_al_operador_no_es_una_afirmacion_de_mercado():
    tr = [_t("zaelar", 'Tú antes hablabas de un 27" 4K por unos 300 euros; ¿te vale?', 101)]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, [])["n"] == 0


def test_despues_de_la_entrega_no_se_cuenta_porque_el_precio_puede_venir_de_la_hoja():
    """There the question is DIFFERENT —is the price correct?— and `prices_that_do_not_match` answers it."""
    tr = [_t("zaelar", "el LG sale por 169 euros", 200)]
    out = verify.market_claims_before_delivery(tr, {"sheet_named_ms": 100_000}, {}, [])
    assert out["n"] == 0


def test_sin_NOTAS_la_pregunta_no_es_medible():
    """A report from before the field existed cannot answer: without the notes' clock, every turn
    appears to precede delivery. «No lo sé» is not «se lo inventó»."""
    tr = [_t("zaelar", "cuesta 15 euros", 101)]
    assert verify.market_claims_before_delivery(tr, _sin_entrega(), {}, None)["measurable"] is False


def test_los_SEGUNDOS_del_transcript_y_los_MILISEGUNDOS_del_reloj_no_se_mezclan():
    """`at` is in seconds and `sheet_named_ms` in milliseconds: comparing them raw makes EVERY turn appear to
    precede delivery, causing the detector to mark the entire run."""
    tr = [_t("zaelar", "sale por 40 euros", 1_000_200)]        # 200 s AFTER delivery
    out = verify.market_claims_before_delivery(tr, {"sheet_named_ms": 1_000_000_000}, {}, [])
    assert out["n"] == 0


def test_al_juez_se_le_dice_que_MIRE_LAS_NOTAS_cuando_esto_no_dispara():
    """The main value: in `compare-insurance-quotes__us` the note arrived 2.6 s before the GEICO turn and the
    judge wrote «INVENTÓ el resultado final». Without this line it does so again."""
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
