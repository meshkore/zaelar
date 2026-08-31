"""V2-339 — “do not share vocabulary” silenced domains where good results do NOT look alike.

The V2-305 guard exists so that the delivery backstop does not announce a page's FEED as if it were
candidates (round 35: Beyblades, cosmetics, candles, and a Ford Fiesta, after a failed keystroke). Its signal was a
single one: if no word is repeated among the rows, it is a feed.

That silences precisely the domains where legitimate results do NOT share a word:

    coches   «Fiat Panda 4x4» · «Mercedes Clase A» · «Peugeot 3008»
    hoteles  «La Banda Living Hostel» · «Eurostars Sevilla» · «Hotel Don Paco»
    vuelos   «Ryanair directo» · «Vueling 08:15» · …

MEASURED with the instrumentation from V2-336, focused car round (2026-08-26, 12:08:59 and 12:09:57): `rows=3`
and the backstop WAS SILENT both times. Without that event, the silence was indistinguishable from a decision.

What really gave the feed away was not the vocabulary: it was the MIXTURE OF SCALES. A candle and a Ford Fiesta
do not share an order of magnitude; three cars from the same search range from 6,900 to 9,500 (×1.4) and three guitars
from 90 to 120 (×1.3).

Now BOTH signals are required to remain silent, so the guard is **strictly narrower** than before:
it still covers the incident that created it—which had both—and returns the backstop to the domains where its
silence cost delivery.
"""
from nucleo.flash import delivery as RG

_COCHES = ["Fiat Panda 4x4 — 6900 €", "Mercedes Clase A — 9500 €", "Peugeot 3008 — 8490 €"]
_HOTELES = ["La Banda Living Hostel — 48 €", "Eurostars Sevilla — 55 €", "Hotel Don Paco — 60 €"]
_GUITARRAS = ["Guitarra Fender CD-60 — 120 €", "Guitarra Yamaha F310 — 100 €", "Guitarra Admira — 90 €"]
_FEED = ["Beyblade Burst — 15 €", "Paula's Choice serum — 32 €", "Velas aromáticas — 9 €",
         "Ford Fiesta 2012 — 3200 €"]


def test_marcas_DISTINTAS_no_son_un_feed():
    assert RG._looks_like_an_unfiltered_feed(_COCHES) is False
    assert RG._looks_like_an_unfiltered_feed(_HOTELES) is False


def test_y_ANTES_sí_lo_eran_por_UNA_sola_señal():
    """The sensitivity of the case above: with the old rule (vocabulary only), the cars WERE a feed."""
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
    """The incident that created the guard had BOTH signals, so it remains covered."""
    assert RG._looks_like_an_unfiltered_feed(_FEED) is True


def test_compartir_vocabulario_basta_para_NO_ser_feed():
    """First signal alone: if they resemble one another, prices are not even considered."""
    assert RG._looks_like_an_unfiltered_feed(_GUITARRAS) is False


def test_sin_precios_legibles_NO_se_juzga_por_ahi():
    """Fail-open: without prices there is no second signal, and remaining silent on suspicion is the error being removed."""
    assert RG._looks_like_an_unfiltered_feed(
        ["Fontanería Paco", "Cerrajería Luis", "Reformas Ana"]) is False


def test_menos_de_TRES_filas_nunca_es_un_feed():
    assert RG._looks_like_an_unfiltered_feed(["A — 10 €", "B — 5000 €"]) is False


def test_y_el_BACKSTOP_vuelve_a_entregar_los_coches():
    """The part that matters: the guard is not the end; it is the backstop's gateway."""
    out = RG.sheet_delivery_backstop("te aviso en cuanto tenga algo", _COCHES, "", errand="coche segunda mano")
    assert out and "Fiat Panda" in out
