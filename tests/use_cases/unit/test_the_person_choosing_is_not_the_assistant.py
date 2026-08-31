"""V2-319 — the person who REJECTS by name what they have just heard is not acting as an assistant.

The role-flip detector (V2-285/312) flags a tester line that recites titles from OUR sheet. Names already
HEARD only gave it away starting at TWO on the same line, based on the idea that reciting a list is assistant
behavior even when the names have been heard. That threshold was a proxy for STANCE —as the detector's own
docstring says— and it broke as soon as a person did what these cases exist to measure: distinguish among
the options they have just been given.

Measured in guitar round 37 (2026-08-25 15:51), turn 17:

    «la CG-150 y la Yamaha C70 son clásicas, de nylon, ¿no? Esas NO ME VALEN. Quiero acústica de cuerda de
     metal, COMO TE DIJE. La Harley Benton y la acústica de 100 esas pinta mejor, a ver si ME CONFIRMAS zona
     y estado.»

Two names heard → flagged → INFRA round. And the cost was not zero: that round contained the guitar HANGER
defect offered as a candidate (V2-318). The instrument threw away a good measurement.

The whole asymmetry, and therefore not a convenient exception but the stated property: **the one who asks says
what they want and asks questions; the one who delivers says what they have and offers it.**
"""
from tests.use_cases.e2e.agent import verify as V

# The actual titles from round 37, as returned by the sheet.
_KNOWN = ["Harley Benton Acústica", "Yamaha C70 Clásica", "Fender CC-60S Natural", "Epiphone DR-100 Nat"]
# What zaelar had said BEFORE that line — the two names come from here.
_HEARD = ("Van saliendo candidatas que te valen: una Valencia CG-150 a 69€, una acústica a 100€, "
          "una Harley Benton a 100€ y una Yamaha C70 a 25€.")
_PERSONA = ("Oye, la CG-150 y la Yamaha C70 son clásicas, de nylon, ¿no? Esas no me valen. Quiero acústica de "
            "cuerda de metal, como te dije. La Harley Benton y la acústica de 100 esas pinta mejor, a ver si "
            "me confirmas zona y estado.")


def test_la_linea_MEDIDA_ya_no_se_marca():
    assert V.recites_our_candidates(_PERSONA, _KNOWN, heard=_HEARD) == []


def test_y_ANTES_si_se_marcaba_por_el_umbral_de_dos():
    """Sensitivity: without the stance caveat, those two echoes are sufficient. If this stops being true, the case
    no longer proves anything and the test above would pass by accident."""
    ecos = [t for t in _KNOWN if V._title_head(t) and V._title_head(t) in V._norm_title(_PERSONA)
            and V._title_head(t) in V._norm_title(_HEARD)]
    assert len(ecos) >= 2


def test_un_titulo_que_zaelar_NUNCA_dijo_sigue_delatando_con_UNO():
    """The caveat does NOT affect the strong case: if the name has not been heard, the person could not know it, and not even
    the most customer-like stance in the world explains them writing it."""
    assert V.recites_our_candidates("no me vale la Epiphone DR-100, porfa busca otra", _KNOWN, heard="")


def test_los_DOS_flips_reales_siguen_cazados():
    """What matters about an exemption is not how many innocents it saves, but how many guilty parties it lets go."""
    guitarra = ("He estado mirando y tengo un par de opciones de cuerdas de metal que encajan con lo que "
                "pides: la Yamaha F370BL por 100 € y la Fender CD-60 por 120 €. Todavía no tengo los enlaces "
                "a mano, pero si quieres puedo centrarme en una de las dos y buscarte el anuncio completo.")
    oido_g = "la Yamaha F370BL por 100 € y la Fender CD-60 por 120 €"
    assert V.recites_our_candidates(guitarra, ["Yamaha F370BL Negra", "Fender CD-60"], heard=oido_g)

    camara = ("Mira, de las que tengo, la más clara es la Canon EOS 4000D: 2.019 disparos y 205€. La Nikon "
              "D800 tiene 15.000 disparos y está justo en 400€. Las demás no especifican el contador en el "
              "anuncio, así que no te las recomiendo de primeras. ¿Te encaja alguna de esas dos o quiero que "
              "siga buscando?")
    oido_c = "la Canon EOS 4000D a 205€ y la Nikon D800 a 400€"
    assert V.recites_our_candidates(camara, ["2.019 DISPAROS Canon EOS 4000D con objetivo kit",
                                             "Nikon D800 solo 15000 disparos último precio."], heard=oido_c)


def test_QUIERO_no_es_un_marcador_de_postura():
    """And this is the exact reason why the list of markers is short. That camera line ends
    "«¿…o QUIERO que siga buscando?» —a garble of «quieres»— and with `quiero` in the list it exempted itself, despite
    being a line that starts "«de las que tengo, la más clara es…». A marker that a conjugation slip can
    create is noise shaped like a signal."""
    assert V._speaks_as_the_customer("o quiero que siga buscando") is False
    assert V._speaks_as_the_customer("prefiero de metal") is False


def test_los_marcadores_que_SI_valen_son_los_que_la_oferta_no_puede_decir():
    for linea in ("esas no me valen", "como te dije, por debajo de 150",
                  "a ver si me confirmas zona y estado", "pásame el enlace porfa"):
        assert V._speaks_as_the_customer(linea), linea


def test_el_barrido_de_la_ronda_LO_USA():
    """The wiring half: the exemption can work and still not reach the sweep that declares INFRA (V2-199)."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert "verifymod.recites_our_candidates" in inspect.getsource(R._run_scenario)
