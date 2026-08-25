"""A pure-waiting reply with a full sheet goes out WITH the rows (V2-305).

Measured on `search-buy-guitar__es` round 34 (2026-08-25 01:56): the browser's note arrived as the turn's own
text, the state face carried the rows, and the model answered «Vale, te aviso en cuanto tenga novedades» —
five turns in a row, `delivery_lag_s` 98.9 s, the judge's [alta] this time RIGHT. The prompt imperative loses
to the waiting reflex about one round in three, and that variance is the difference between the case passing
and failing. Same family as the never-mute backstop (V2-132) and `holding_line` (V2-189): when the correct
behaviour is deterministic — named rows in front, reply says only «wait» — the code guarantees it, not the
model's temperature.
"""
from nucleo.flash import router_guards as RG

# La segunda LLEVA la categoría a propósito: la puerta de pertenencia (ronda 35) exige compartir un token
# con el encargo, y un título sin la palabra categoría («Yamaha F370BL Negra» a secas) NO se anuncia — es el
# lado conservador asumido: mejor callar una fila legítima que anunciar Beyblades como guitarras.
ROWS = ["Guitarra Acústica Fender CD-60 — 120 €", "Guitarra Yamaha F370BL Negra — 100 €"]


def test_a_waiting_reply_with_fresh_rows_gets_them_appended():
    out = RG.sheet_delivery_backstop("Vale, te aviso en cuanto tenga novedades.", ROWS, "",
                                     errand="busca una guitarra acústica por menos de 150€")
    assert "Fender CD-60" in out and "120 €" in out
    assert "hoja de resultados" in out, "las filas vienen de la hoja: decirlo es un hecho, no una promesa"


def test_a_reply_that_already_delivers_is_left_alone():
    """El lado contrario: una respuesta larga que ya está contando algo no se pisa."""
    r = ("¡Ya tengo candidatos! La Fender CD-60 a 120 € encaja con tu tope y también hay una Yamaha F370BL "
         "a 100 €. El humidificador es un accesorio y no te vale. ¿Te abro alguna ficha o sigo afinando?")
    assert RG.sheet_delivery_backstop(r, ROWS, "") == ""


def test_rows_already_said_before_are_not_reannounced():
    """Re-anunciar lo entregado es el disco rayado de V2-189 por la puerta de atrás."""
    said = "Ya te pasé la Guitarra Acústica Fender CD-60 a 120 € y la Yamaha F370BL Negra a 100 €."
    assert RG.sheet_delivery_backstop("Sigo con ello, te aviso.", ROWS, said) == ""


def test_no_rows_no_backstop():
    assert RG.sheet_delivery_backstop("Sigo con ello, te aviso.", [], "") == ""


def test_a_non_waiting_short_reply_is_untouched():
    assert RG.sheet_delivery_backstop("¿Prefieres cuerdas de metal o nylon?", ROWS, "") == ""


def test_partial_freshness_only_appends_the_unsaid_rows():
    said = "La Fender CD-60 a 120 € ya la vimos."
    out = RG.sheet_delivery_backstop("Sigo buscando, te aviso.", ROWS, said,
                                     errand="busca una guitarra acústica")
    assert "Yamaha F370BL" in out and "Fender CD-60" not in out


def test_the_category_noun_never_kills_freshness():
    """Agnóstico del dominio: «guitarra» (o «hotel», o «monitor») está en el ENCARGO y suena en cada turno —
    si contara como identidad, todas las filas serían «ya dichas» y el backstop no dispararía nunca. La
    exclusión sale del encargo, no de una lista de genéricos por sector (eso sería adaptarse al caso de uso)."""
    rows = ["Guitarra Acústica Española Completa Nueva — 95 €"]
    said = "Estoy buscando tu guitarra acústica, dame un momento."
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", rows, said,
                                     errand="busca una guitarra acústica española")
    assert "95 €" in out, "las palabras del encargo no son identidad de una fila"


def test_the_probe_actually_wires_it():
    """Guarda de cableado (fuente SIN comentarios): la decisión sin llamante es el arreglo que no existe —
    dos guardas de esta suite ya pasaron en verde con la llamada borrada porque el comentario la nombraba."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/flash/probe.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    assert "sheet_delivery_backstop(spoken" in src
    assert "any_live_task_rows()" in src
    assert "errand=_goal_del" in src, "sin el encargo, la categoría del dominio mata la frescura de todas las filas"


def test_junk_rows_from_an_unfiltered_feed_are_never_announced():
    """Ronda 35 (2026-08-25): el worker falló el tecleo, Wallapop devolvió su feed sin filtrar y la hoja se
    llenó de Beyblades y cosmética. El modelo hizo BIEN en no entregarla — y este backstop la habría anunciado.
    Una fila solo se anuncia si comparte un token sustantivo con el encargo."""
    junk = ["Juguetes Beyblade Die-Cast (COLOR AL AZAR) — 15 €",
            "Pack 2x Paula's Choice BHA 2% Exfoliante 118ml — 30 €"]
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", junk, "",
                                     errand="busca una guitarra acústica por menos de 150€")
    assert out == "", "anunciar basura deterministamente es peor que la espera que corrige"


def test_matching_rows_still_fire_with_the_membership_gate():
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", ROWS, "",
                                     errand="busca una guitarra acústica por menos de 150€")
    assert "Fender CD-60" in out


def test_a_title_without_the_category_noun_is_skipped_conservatively():
    """El coste asumido de la puerta de pertenencia, escrito para que nadie lo lea como un bug suelto."""
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", ["Yamaha F370BL Negra — 100 €"], "",
                                     errand="busca una guitarra acústica")
    assert out == ""
