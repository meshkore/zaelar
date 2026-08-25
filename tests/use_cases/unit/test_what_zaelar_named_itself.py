"""V2-329 — el informe dice qué candidatos nombró ZAELAR con sus propias palabras, y en qué turno.

El informe ya decía lo que el SISTEMA le puso delante al cerebro (`offered`), y eso responde a «¿se lo
inventó?». No respondía a la otra pregunta, que es la que ha decidido mal tres veredictos el 2026-08-25:
**¿lo dijo?**

Las tres veces con la misma forma — el juez confundió «sigue trabajando en los detalles» con «oculta lo que
tiene»:

  · `search-secondhand-monitor` (21:35) bajó de PASS a FAIL con «tiene los datos y decide no mostrarlos para
    mantener una ficción de búsqueda activa». Turno a turno había entregado CINCO candidatos con nombre y
    precio: «la HP 27 HDMI por 35 €», «el Samsung Curvo 27" por 50 €», «MSI Curvo 27 por 120 €», «AOC 27
    Curvo 144Hz por 60 €», «ViewSonic 27 IPS por 80 €».
  · `search-buy-used-car` (20:08): «interpretando datos reales como errores del sistema», cuando lo que hizo
    fue detectar que «Buen precio» y «Contado» no eran coches, DECIRLO, y mandar abrir las fichas.
  · `search-buy-bicycle` (21:25): dos bloqueadores que eran contaminación nuestra (V2-328).

NO se reutiliza `recites_our_candidates`, y la razón es la ASIMETRÍA DE COSTE. Aquel caza al conductor fuera de
papel, donde un falso positivo TIRA una ronda buena: por eso exige código de modelo o mucha materia, y por eso
descarta «Pantalla HP 27 HDMI». Medido: sobre los turnos del monitor cazaba 1 de 3. Aquí quien habla TIENE la
lista delante, no hay que protegerse de «no podía saberlo», y el casador puede ser —y es— más ancho.
"""
from tests.use_cases.e2e.agent import verify as V

# Los títulos reales de la hoja de aquella ronda.
_HOJA = ["Pantalla HP 27 HDMI", 'Monitor Curvo Samsung 27"', "Monitor AOC 27 Curvo 144Hz",
         "ViewSonic 27 IPS FullHD", "Pantalla Gaming MSI Curva 27 pulgadas", "Monitor Dell que nadie mencionó"]
# Y lo que zaelar dijo, en la forma en que lo dijo.
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
    """La sensibilidad: si contara todo lo de la hoja, el hecho no distinguiría entregar de no entregar."""
    r = V.delivered_by_name(_TR, _HOJA)
    assert not any("Dell" in n for n in r["names"])
    assert not any("MSI" in n for n in r["names"])


def test_los_turnos_del_TESTER_no_cuentan():
    """Que la persona diga un nombre no es que zaelar lo entregara — al revés, eso es un role-flip (V2-285)."""
    tr = [{"who": "tester", "text": "yo he visto el Monitor AOC 27 Curvo 144Hz por 60 €"}]
    assert V.delivered_by_name(tr, _HOJA)["n"] == 0


def test_una_frase_de_pura_espera_no_nombra_nada():
    assert V.delivered_by_name([{"who": "zaelar", "text": "sigo con ello, te aviso"}], _HOJA)["n"] == 0


def test_sin_hoja_no_se_inventa_nada():
    assert V.delivered_by_name(_TR, [])["n"] == 0
    assert V.delivered_by_name([], _HOJA)["n"] == 0


def test_no_cuenta_DOS_veces_el_mismo_candidato():
    """Repetir un candidato es normal en una conversación; contarlo dos veces inflaría el hecho."""
    tr = [{"who": "zaelar", "text": "la pantalla HP 27 HDMI por 35 €"},
          {"who": "zaelar", "text": "te decía, la pantalla HP 27 HDMI sigue siendo la más barata"}]
    assert V.delivered_by_name(tr, _HOJA)["n"] == 1


def test_es_MÁS_ANCHO_que_el_cazador_de_role_flips_y_eso_es_deliberado():
    """La asimetría de coste, fijada: allí un falso positivo tira una ronda; aquí solo debilita un bloqueador.
    Si algún día se unifican los dos casadores, este test dice qué se pierde."""
    linea = "destacan la pantalla HP 27 HDMI por 35 €"
    assert V.recites_our_candidates(linea, ["Pantalla HP 27 HDMI"]) == [], (
        "si el estricto empieza a cazar esto, revisar su tasa de falsos positivos sobre el corpus")
    assert V.delivered_by_name([{"who": "zaelar", "text": linea}], ["Pantalla HP 27 HDMI"])["n"] == 1


def test_el_informe_LO_LLEVA_y_el_JUEZ_lo_recibe():
    """Las dos mitades de cableado: leerlo bien y que llegue a quien decide."""
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


# ── V2-331 · el PRECIO confirma de qué fila habla ─────────────────────────────────────────────────────────
# Exigir los tres primeros tokens del título fallaba contra cómo se nombra una cosa AL HABLAR: la hoja dice
# «Brixton Crossfire 125 XS» y zaelar dice «la Brixton a 1.200 €».
#
# MEDIDO en el turno de las 21:12 del 2026-08-25 —«me centro solo en las tres motos: la Yamaha R125 a 500 €, la
# Brixton a 1.200 € y la Honda Varadero a 2.400 €»— donde el casador de V2-329 devolvía CERO. O sea que el
# hecho construido para contradecir un «retuvo» estaba infra-detectando entregas: hacía justo lo contrario de
# para lo que existe. Lo encontré midiendo mal el defecto hermano y revisando turno a turno lo que mi propia
# regex había contado como «espera».

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
    """La sensibilidad del precio: «Yamaha XSR 700» está en la hoja y NO se mencionó. Sin el precio como
    confirmación, cualquier «Yamaha» las contaría las dos."""
    r = V.delivered_by_name([{"who": "zaelar", "text": _TURNO}], _MOTOS)
    assert not any("XSR" in n for n in r["names"])
    assert not any("Casco" in n for n in r["names"])


def test_la_marca_SOLA_sin_precio_no_basta():
    """Decir «he mirado varias Yamaha» no es entregar una fila concreta."""
    r = V.delivered_by_name([{"who": "zaelar", "text": "he mirado varias Yamaha por ahí"}], _MOTOS)
    assert r["n"] == 0


def test_el_formato_VIEJO_sigue_funcionando():
    """Compatibilidad: quien pase títulos sueltos sin precio sigue midiendo por los dos primeros tokens."""
    r = V.delivered_by_name([{"who": "zaelar", "text": "la pantalla HP 27 HDMI por 35 €"}],
                            ["Pantalla HP 27 HDMI"])
    assert r["n"] == 1
