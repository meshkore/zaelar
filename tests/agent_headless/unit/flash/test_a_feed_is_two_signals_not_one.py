"""V2-339 — «no comparten vocabulario» silenciaba los dominios donde los resultados buenos NO se parecen.

La guarda de V2-305 existe para que el backstop de entrega no anuncie el FEED de una página como si fueran
candidatos (ronda 35: Beyblades, cosmética, velas y un Ford Fiesta, tras un tecleo fallido). Su señal era una
sola: si ninguna palabra se repite entre las filas, es un feed.

Eso silencia justo los dominios donde unos resultados legítimos NO comparten palabra:

    coches   «Fiat Panda 4x4» · «Mercedes Clase A» · «Peugeot 3008»
    hoteles  «La Banda Living Hostel» · «Eurostars Sevilla» · «Hotel Don Paco»
    vuelos   «Ryanair directo» · «Vueling 08:15» · …

MEDIDO con la instrumentación de V2-336, ronda enfocada del coche (2026-08-26, 12:08:59 y 12:09:57): `rows=3`
y el backstop CALLÓ las dos veces. Sin ese evento el silencio era indistinguible de una decisión.

Lo que de verdad delataba el feed no era el vocabulario: era la MEZCLA DE ESCALAS. Una vela y un Ford Fiesta
no comparten orden de magnitud; tres coches de una misma búsqueda van de 6.900 a 9.500 (×1,4) y tres guitarras
de 90 a 120 (×1,3).

Ahora se exigen las DOS señales para callar, así que la guarda es **estrictamente más estrecha** que antes:
sigue cubriendo el incidente que la creó —que tenía ambas— y devuelve el backstop a los dominios donde su
silencio costaba la entrega.
"""
from nucleo.flash import router_guards as RG

_COCHES = ["Fiat Panda 4x4 — 6900 €", "Mercedes Clase A — 9500 €", "Peugeot 3008 — 8490 €"]
_HOTELES = ["La Banda Living Hostel — 48 €", "Eurostars Sevilla — 55 €", "Hotel Don Paco — 60 €"]
_GUITARRAS = ["Guitarra Fender CD-60 — 120 €", "Guitarra Yamaha F310 — 100 €", "Guitarra Admira — 90 €"]
_FEED = ["Beyblade Burst — 15 €", "Paula's Choice serum — 32 €", "Velas aromáticas — 9 €",
         "Ford Fiesta 2012 — 3200 €"]


def test_marcas_DISTINTAS_no_son_un_feed():
    assert RG._looks_like_an_unfiltered_feed(_COCHES) is False
    assert RG._looks_like_an_unfiltered_feed(_HOTELES) is False


def test_y_ANTES_sí_lo_eran_por_UNA_sola_señal():
    """La sensibilidad del caso de arriba: con la regla vieja (solo vocabulario) los coches SÍ eran feed."""
    def vieja(rows):
        titles = [RG._norm_txt(str(r or "").split(" — ")[0]) for r in rows]
        counts = {}
        for t in titles:
            for w in set(t.split()):
                if len(w) >= 4:
                    counts[w] = counts.get(w, 0) + 1
        return not any(n >= 2 for n in counts.values())
    assert vieja(_COCHES) is True, "si esto falla, el caso ya no prueba lo que arregla V2-339"


def test_el_FEED_original_sigue_cazado():
    """El incidente que creó la guarda tenía las DOS señales, así que sigue cubierto."""
    assert RG._looks_like_an_unfiltered_feed(_FEED) is True


def test_compartir_vocabulario_basta_para_NO_ser_feed():
    """Primera señal sola: si se parecen entre sí, ni se miran los precios."""
    assert RG._looks_like_an_unfiltered_feed(_GUITARRAS) is False


def test_sin_precios_legibles_NO_se_juzga_por_ahi():
    """Fail-open: sin precios no hay segunda señal, y callar por sospecha es el error que se está quitando."""
    assert RG._looks_like_an_unfiltered_feed(
        ["Fontanería Paco", "Cerrajería Luis", "Reformas Ana"]) is False


def test_menos_de_TRES_filas_nunca_es_un_feed():
    assert RG._looks_like_an_unfiltered_feed(["A — 10 €", "B — 5000 €"]) is False


def test_y_el_BACKSTOP_vuelve_a_entregar_los_coches():
    """La mitad que importa: la guarda no es el fin, es la puerta del backstop."""
    out = RG.sheet_delivery_backstop("te aviso en cuanto tenga algo", _COCHES, "", errand="coche segunda mano")
    assert out and "Fiat Panda" in out
