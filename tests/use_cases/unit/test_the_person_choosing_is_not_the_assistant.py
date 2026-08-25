"""V2-319 — la persona que RECHAZA por nombre lo que acaba de oír no está haciendo de asistente.

El detector de role-flip (V2-285/312) marca una línea del tester que recita títulos de NUESTRA hoja. Los ya
OÍDOS solo delataban a partir de DOS en la misma línea, sobre la idea de que recitar una lista es conducta de
asistente aunque los nombres se hayan oído. Ese umbral era un proxy de la POSTURA —lo dice el propio docstring
del detector— y se rompió en cuanto una persona hizo lo que estos casos existen para medir: discriminar entre
las opciones que le acaban de dar.

Medido en la ronda 37 de la guitarra (2026-08-25 15:51), turno 17:

    «la CG-150 y la Yamaha C70 son clásicas, de nylon, ¿no? Esas NO ME VALEN. Quiero acústica de cuerda de
     metal, COMO TE DIJE. La Harley Benton y la acústica de 100 esas pinta mejor, a ver si ME CONFIRMAS zona
     y estado.»

Dos nombres oídos → marcada → ronda INFRA. Y el coste no fue cero: esa ronda traía el defecto del COLGADOR de
guitarra ofrecido como candidato (V2-318). El instrumento tiró una medida buena.

La asimetría entera, y por eso no es una excepción cómoda sino la propiedad escrita: **quien pide dice lo que
quiere y pregunta; quien entrega dice lo que tiene y se ofrece.**
"""
from tests.use_cases.e2e.agent import verify as V

# Los títulos reales de la ronda 37, tal como los devolvió la hoja.
_KNOWN = ["Harley Benton Acústica", "Yamaha C70 Clásica", "Fender CC-60S Natural", "Epiphone DR-100 Nat"]
# Lo que zaelar había dicho ANTES de esa línea — los dos nombres salen de aquí.
_HEARD = ("Van saliendo candidatas que te valen: una Valencia CG-150 a 69€, una acústica a 100€, "
          "una Harley Benton a 100€ y una Yamaha C70 a 25€.")
_PERSONA = ("Oye, la CG-150 y la Yamaha C70 son clásicas, de nylon, ¿no? Esas no me valen. Quiero acústica de "
            "cuerda de metal, como te dije. La Harley Benton y la acústica de 100 esas pinta mejor, a ver si "
            "me confirmas zona y estado.")


def test_la_linea_MEDIDA_ya_no_se_marca():
    assert V.recites_our_candidates(_PERSONA, _KNOWN, heard=_HEARD) == []


def test_y_ANTES_si_se_marcaba_por_el_umbral_de_dos():
    """La sensibilidad: sin la salvedad de postura, esos dos ecos bastan. Si esto deja de ser cierto, el caso
    ya no prueba nada y el test de arriba pasaría por accidente."""
    ecos = [t for t in _KNOWN if V._title_head(t) and V._title_head(t) in V._norm_title(_PERSONA)
            and V._title_head(t) in V._norm_title(_HEARD)]
    assert len(ecos) >= 2


def test_un_titulo_que_zaelar_NUNCA_dijo_sigue_delatando_con_UNO():
    """La salvedad NO toca el caso fuerte: si el nombre no se ha oído, la persona no podía saberlo, y ni la
    postura más de cliente del mundo explica que lo escriba."""
    assert V.recites_our_candidates("no me vale la Epiphone DR-100, porfa busca otra", _KNOWN, heard="")


def test_los_DOS_flips_reales_siguen_cazados():
    """El número que importa de un eximente no es a cuántos inocentes salva, es a cuántos culpables suelta."""
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
    """Y ésta es la razón exacta por la que la lista de marcadores es corta. Esa línea de la cámara termina
    «¿…o QUIERO que siga buscando?» —un garble de «quieres»— y con `quiero` en la lista se eximía sola, siendo
    una línea que empieza «de las que tengo, la más clara es…». Un marcador que un desliz de conjugación puede
    fabricar es ruido con forma de señal."""
    assert V._speaks_as_the_customer("o quiero que siga buscando") is False
    assert V._speaks_as_the_customer("prefiero de metal") is False


def test_los_marcadores_que_SI_valen_son_los_que_la_oferta_no_puede_decir():
    for linea in ("esas no me valen", "como te dije, por debajo de 150",
                  "a ver si me confirmas zona y estado", "pásame el enlace porfa"):
        assert V._speaks_as_the_customer(linea), linea


def test_el_barrido_de_la_ronda_LO_USA():
    """La mitad de cableado: el eximente puede acertar y no llegar al barrido que declara INFRA (V2-199)."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert "verifymod.recites_our_candidates" in inspect.getsource(R._run_scenario)
