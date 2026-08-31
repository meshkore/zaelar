"""V2-329 — the report says which candidates ZAELAR named in its own words, and on which turn.

The report already said what the SYSTEM put in front of its mind (`offered`), which answers “did it make
it up?”. It did not answer the other question, the one that led to three incorrect verdicts on 2026-08-25:
**did it say it?**

All three times had the same pattern — the judge confused “it is still working on the details” with “it is
hiding what it has”:

  · `search-secondhand-monitor` (21:35) bajó de PASS a FAIL con «tiene los datos y decide no mostrarlos para
    mantener una ficción de búsqueda activa». Turno a turno había entregado CINCO candidatos con nombre y
    precio: «la HP 27 HDMI por 35 €», «el Samsung Curvo 27" por 50 €», «MSI Curvo 27 por 120 €», «AOC 27
    Curvo 144Hz por 60 €», «ViewSonic 27 IPS por 80 €».
  · `search-buy-used-car` (20:08): «interpretando datos reales como errores del sistema», cuando lo que hizo
    fue detectar que «Buen precio» y «Contado» no eran coches, DECIRLO, y mandar abrir las fichas.
  · `search-buy-bicycle` (21:25): dos bloqueadores que eran contaminación nuestra (V2-328).

`recites_our_candidates` is not reused, and the reason is COST ASYMMETRY. That one catches the driver off the
record, where a false positive WASTES a good round: that is why it requires a model code or substantial
content, and why it discards “Pantalla HP 27 HDMI”. Measured: across the monitor turns it caught 1 of 3. Here
the speaker HAS the list in front of it, there is no need to guard against “it could not have known”, and the
catcher can be —and is— broader.
"""
from tests.use_cases.e2e.agent import verify as V

# The actual titles from that round's sheet.
_HOJA = ["Pantalla HP 27 HDMI", 'Monitor Curvo Samsung 27"', "Monitor AOC 27 Curvo 144Hz",
         "ViewSonic 27 IPS FullHD", "Pantalla Gaming MSI Curva 27 pulgadas", "Monitor Dell que nadie mencionó"]
# And what zaelar said, in the form in which it said it.
_TR = [
    {"who": "zaelar", "text": "Marc, ya tengo cosas: destacan la pantalla HP 27 HDMI por 35 € y el "
                              'Monitor Curvo Samsung 27" por 50 €'},
    {"who": "tester", "text": "vale, sigue"},
    {"who": "zaelar", "text": "han salido un par más: el Monitor AOC 27 Curvo 144Hz por 60 € y el "
                              "ViewSonic 27 IPS FullHD por 80 €"},
    {"who": "zaelar", "text": "Va, te digo en cuanto confirme lo del envío. 👍"},
]


def test_recoge_lo_que_NOMBRÓ_y_su_turno():
    r = V.delivered_by_name(_TR, _HOJA)
    assert r["n"] == 4, r["names"]
    assert r["turns"] == [1, 1, 3, 3]


def test_lo_que_NO_mencionó_no_aparece():
    """Sensitivity: if it counted everything on the sheet, the fact would not distinguish delivery from non-delivery."""
    r = V.delivered_by_name(_TR, _HOJA)
    assert not any("Dell" in n for n in r["names"])
    assert not any("MSI" in n for n in r["names"])


def test_los_turnos_del_TESTER_no_cuentan():
    """The person saying a name does not mean zaelar delivered it — on the contrary, that is a role flip (V2-285)."""
    tr = [{"who": "tester", "text": "yo he visto el Monitor AOC 27 Curvo 144Hz por 60 €"}]
    assert V.delivered_by_name(tr, _HOJA)["n"] == 0


def test_una_frase_de_pura_espera_no_nombra_nada():
    assert V.delivered_by_name([{"who": "zaelar", "text": "sigo con ello, te aviso"}], _HOJA)["n"] == 0


def test_sin_hoja_no_se_inventa_nada():
    assert V.delivered_by_name(_TR, [])["n"] == 0
    assert V.delivered_by_name([], _HOJA)["n"] == 0


def test_no_cuenta_DOS_veces_el_mismo_candidato():
    """Repeating a candidate is normal in a conversation; counting it twice would inflate the fact."""
    tr = [{"who": "zaelar", "text": "la pantalla HP 27 HDMI por 35 €"},
          {"who": "zaelar", "text": "te decía, la pantalla HP 27 HDMI sigue siendo la más barata"}]
    assert V.delivered_by_name(tr, _HOJA)["n"] == 1


def test_es_MÁS_ANCHO_que_el_cazador_de_role_flips_y_eso_es_deliberado():
    """The cost asymmetry, made explicit: there a false positive wastes a round; here it only weakens a blocker.
    If the two catchers are ever unified, this test says what is lost."""
    linea = "destacan la pantalla HP 27 HDMI por 35 €"
    assert V.recites_our_candidates(linea, ["Pantalla HP 27 HDMI"]) == [], (
        "si el estricto empieza a cazar esto, revisar su tasa de falsos positivos sobre el corpus")
    assert V.delivered_by_name([{"who": "zaelar", "text": linea}], ["Pantalla HP 27 HDMI"])["n"] == 1


def test_el_informe_LO_LLEVA_y_el_JUEZ_lo_recibe():
    """The two halves of the wiring: read it correctly and get it to the decision-maker."""
    import inspect

    from tests.use_cases.e2e.agent import judge as J
    from tests.use_cases.e2e.agent import run as R
    assert 'mech["delivered_by_name"] = verifymod.delivered_by_name(' in inspect.getsource(R._run_scenario)
    src = inspect.getsource(J.mechanism_facts)
    assert 'mech.get("delivered_by_name")' in src
    assert "RETUVO" in src, "el hecho llega sin decirle al juez qué hacer con él"


def test_y_le_dice_al_juez_que_ese_bloqueador_TIENE_QUE_EXPLICARSE():
    from tests.use_cases.e2e.agent.judge import mechanism_facts
    txt = mechanism_facts({"delivered_by_name": {"n": 2, "names": ["Pantalla HP 27 HDMI", "Monitor AOC 27"],
                                                 "turns": [3, 7]}})
    assert "NOMBRÓ ESTO ÉL MISMO" in txt
    assert "turno(s) 3, 7" in txt
    low = txt.lower()
    assert "retuvo" in low and "ficción" in low
    assert "eficiencia" in low, "seguir trabajando tras entregar tiene que quedar nombrado como lo que es"


# ── V2-331 · the PRICE confirms which row is being discussed ─────────────────────────────────────────────────
# Requiring the first three title tokens failed against how a thing is named IN SPEECH: the sheet says
# “Brixton Crossfire 125 XS” and zaelar says “la Brixton a 1.200 €”.
#
# MEASURED in the 21:12 turn on 2026-08-25 —“I will focus only on the three motorcycles: the Yamaha R125 at
# 500 €, the Brixton at 1.200 € and the Honda Varadero at 2.400 €”— where the V2-329 catcher returned ZERO. In
# other words, the fact built to contradict a “retained” finding was under-detecting deliveries: it was doing
# the exact opposite of what it exists for. I found it by measuring the related defect incorrectly and reviewing
# turn by turn what my own regex had counted as “waiting”.

_MOTOS = [("Moto Yamaha R125 2020 pocos km", "500 €"), ("Brixton Crossfire 125 XS", "1.200 €"),
          ("Honda Varadero 125 revisada", "2.400 €"), ("Casco integral MT sin usar", "40 €"),
          ("Yamaha XSR 700 impecable", "5.900 €")]
_TURNO = ("Entendido, me centro solo en las tres motos: la Yamaha R125 a 500 €, la Brixton a 1.200 € y la "
          "Honda Varadero a 2.400 €")


def test_nombrar_por_la_MARCA_con_su_precio_cuenta_como_entrega():
    r = V.delivered_by_name([{"who": "zaelar", "text": _TURNO}], _MOTOS)
    assert r["n"] == 3, r["names"]
    assert any("Brixton" in n for n in r["names"]), "la que solo se nombró por la marca"


def test_y_NO_arrastra_a_la_que_comparte_marca():
    """Price sensitivity: “Yamaha XSR 700” is on the sheet and was NOT mentioned. Without the price as
    confirmation, any “Yamaha” would count both of them."""
    r = V.delivered_by_name([{"who": "zaelar", "text": _TURNO}], _MOTOS)
    assert not any("XSR" in n for n in r["names"])
    assert not any("Casco" in n for n in r["names"])


def test_la_marca_SOLA_sin_precio_no_basta():
    """Saying “I have looked at several Yamahas” is not delivering a specific row."""
    r = V.delivered_by_name([{"who": "zaelar", "text": "he mirado varias Yamaha por ahí"}], _MOTOS)
    assert r["n"] == 0


def test_el_formato_VIEJO_sigue_funcionando():
    """Compatibility: callers passing standalone titles without prices are still measured by the first two tokens."""
    r = V.delivered_by_name([{"who": "zaelar", "text": "la pantalla HP 27 HDMI por 35 €"}],
                            ["Pantalla HP 27 HDMI"])
    assert r["n"] == 1
