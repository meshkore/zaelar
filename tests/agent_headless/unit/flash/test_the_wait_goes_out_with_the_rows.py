"""A pure-waiting reply with a full sheet goes out WITH the rows (V2-305).

Measured on `search-buy-guitar__es` round 34 (2026-08-25 01:56): the browser's note arrived as the turn's own
text, the state face carried the rows, and the model answered «Vale, te aviso en cuanto tenga novedades» —
five turns in a row, `delivery_lag_s` 98.9 s, the judge's [alta] this time RIGHT. The prompt imperative loses
to the waiting reflex about one round in three, and that variance is the difference between the case passing
and failing. Same family as the never-mute backstop (V2-132) and `holding_line` (V2-189): when the correct
behaviour is deterministic — named rows in front, reply says only «wait» — the code guarantees it, not the
model's temperature.
"""
import pytest

from nucleo.flash import delivery as RG


@pytest.fixture(autouse=True)
def _hablando_en_castellano(monkeypatch):
    """These tests assert the SPANISH wording, so they state the language instead of inheriting it.

    Until V2-475 this family had one wording and the language was invisible; now that the sentence follows
    the operator's language, a test that leaves it ambient is really asserting «whatever the default is»
    (English on a fresh engine) — which is how a Spanish assertion silently starts grading English output.
    """
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es")


# The second one DELIBERATELY CARRIES the category: the membership gate (round 35) requires sharing a token
# with the errand, and a title without the category word («Yamaha F370BL Negra» on its own) is NOT announced — this is
# the conservative side chosen: better to keep a legitimate row quiet than announce Beyblades as guitars.
ROWS = ["Guitarra Acústica Fender CD-60 — 120 €", "Guitarra Yamaha F370BL Negra — 100 €"]


def test_a_waiting_reply_with_fresh_rows_gets_them_appended():
    out = RG.sheet_delivery_backstop("Vale, te aviso en cuanto tenga novedades.", ROWS, "",
                                     errand="busca una guitarra acústica por menos de 150€")
    assert "Fender CD-60" in out and "120 €" in out
    assert "hoja de resultados" in out, "the rows come from the sheet: saying so is a fact, not a promise"


def test_a_reply_that_already_delivers_is_left_alone():
    """The opposite case: a long response that is already reporting something is left alone."""
    r = ("¡Ya tengo candidatos! La Fender CD-60 a 120 € encaja con tu tope y también hay una Yamaha F370BL "
         "a 100 €. El humidificador es un accesorio y no te vale. ¿Te abro alguna ficha o sigo afinando?")
    assert RG.sheet_delivery_backstop(r, ROWS, "") == ""


def test_rows_already_said_before_are_not_reannounced():
    """Re-announcing what was delivered is V2-189's broken record through the back door."""
    said = "Ya te pasé la Guitarra Acústica Fender CD-60 a 120 € y la Yamaha F370BL Negra a 100 €."
    assert RG.sheet_delivery_backstop("Sigo con ello, te aviso.", ROWS, said) == ""


def test_no_rows_no_backstop():
    assert RG.sheet_delivery_backstop("Sigo con ello, te aviso.", [], "") == ""


def test_una_pregunta_corta_ENTREGA_los_hechos_y_no_añade_la_nuestra():
    """REVERTED by V2-371, and kept here because the example is the same. It was called
    `test_a_non_waiting_short_reply_is_untouched` y exigía silencio ante una pregunta.

    What that silence cost, measured in `search-buy-motorcycle__es` (2026-08-27): eleven named candidates
    with links in the sheet, 87.4 s of retention, and turns that asked a question fell into the STALLED backstop, which
    appended OUR management question behind it — the operator received the same question twice, one already
    answered, and none of the eleven candidates.

    What it protected remains protected, and that is the half that matters: it does not take the floor away. The
    FACTS are delivered and no question is added, so the only question closing the turn is theirs."""
    out = RG.sheet_delivery_backstop("¿Prefieres cuerdas de metal o nylon?", ROWS, "")
    assert "Fender CD-60" in out
    assert "?" not in out


def test_partial_freshness_only_appends_the_unsaid_rows():
    said = "La Fender CD-60 a 120 € ya la vimos."
    out = RG.sheet_delivery_backstop("Sigo buscando, te aviso.", ROWS, said,
                                     errand="busca una guitarra acústica")
    assert "Yamaha F370BL" in out and "Fender CD-60" not in out


def test_the_category_noun_never_kills_freshness():
    """Domain-agnostic: «guitarra» (or «hotel», or «monitor») is in the ERRAND and is heard in every turn —
    if it counted as identity, every row would be «already said» and the backstop would never fire. The
    exclusion comes from the errand, not from a sector-specific list of generic terms (that would be adapting to the use case)."""
    rows = ["Guitarra Acústica Española Completa Nueva — 95 €"]
    said = "Estoy buscando tu guitarra acústica, dame un momento."
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", rows, said,
                                     errand="busca una guitarra acústica española")
    assert "95 €" in out, "las palabras del encargo no son identidad de una fila"


def test_the_probe_actually_wires_it():
    """Wiring guard (source WITHOUT comments): the decision without a caller is the fix that does not exist —
    two guards in this suite already passed in green with the call deleted because the comment named it."""
    from pathlib import Path
    # V2-340: the wiring moved to `delivery.apply_to_reply`, so the guard checks BOTH places — that
    # the probe calls it, and that the call still carries the errand. Checking only the probe would pass with the
    # function empty; checking only the function, with the probe not calling it.
    probe = "\n".join(ln for ln in Path("nucleo/flash/probe.py").read_text().splitlines()
                      if not ln.strip().startswith("#"))
    assert "delivery.apply_to_reply(spoken" in probe or "_delivery.apply_to_reply(spoken" in probe
    deliv = "\n".join(ln for ln in Path("nucleo/flash/delivery.py").read_text().splitlines()
                       if not ln.strip().startswith("#"))
    assert "sheet_delivery_backstop(spoken" in deliv
    assert "any_live_task_rows()" in deliv
    assert "errand=encargo" in deliv, "without the errand, the domain category kills the freshness of every row"


def test_junk_rows_from_an_unfiltered_feed_are_never_announced():
    """Round 35 (2026-08-25 02:20): the worker failed at typing, the page returned its unfiltered home page, and the
    sheet filled up with Beyblades, cosmetics, candles, and a Ford Fiesta. The model did the RIGHT thing by not
    delivering them — and this backstop would have announced them. What exposes them is NOT the errand (see the test
    below), but that they share NOTHING with one another: search results are coherent; a feed is not."""
    junk = ["Juguetes Beyblade Die-Cast (COLOR AL AZAR) — 15 €",
            "Pack 2x Paula's Choice BHA 2% Exfoliante 118ml — 30 €",
            "Velas de Gruta y Gel artesanales — 12 €",
            "Ford Fiesta 1.0 EcoBoost ST-Line — 8.900 €"]
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", junk, "",
                                     errand="busca una guitarra acústica por menos de 150€")
    assert out == "", "anunciar basura deterministamente es peor que la espera que corrige"


def test_entities_that_never_repeat_the_category_STILL_fire():
    """The defect in the first gate, measured in the 10:04 batch: requiring a shared word with the
    ERRAND is domain-specific — in a marketplace the title repeats the category, but a hotel is called
    «La Banda Living Hostel» and a flight «Ryanair directo». With 36 legitimate hotel rows in the
    sheet, the backstop did not fire even once and the judge logged «202 s of retention»."""
    hoteles = ["La Banda Living Hostel — € 98", "New Samay Hostel — € 88",
               "La Banda Rooftop Hostel — € 118"]
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", hoteles, "",
                                     errand="Busca el mejor hotel en Sevilla, menos de 120€ la noche")
    assert "La Banda Living Hostel" in out


def test_two_rows_are_never_called_a_feed():
    """Two different things are not a feed: below three rows, coherence is not judged, because staying quiet there
    reintroduces precisely the silence this backstop exists to remove."""
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.",
                                     ["Hotel Alfonso XIII — 210 €", "Corral del Rey — 180 €"], "",
                                     errand="busca hotel en Sevilla")
    assert "Alfonso XIII" in out


def test_matching_rows_still_fire_with_the_membership_gate():
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", ROWS, "",
                                     errand="busca una guitarra acústica por menos de 150€")
    assert "Fender CD-60" in out


def test_a_heterogeneous_errand_YA_NO_es_un_coste_asumido():
    """This test recorded a cost that V2-339 no longer pays, and is kept reverted so that the improvement
    remains recorded in the same place where the renunciation was.

    Decía: «un encargo legítimamente heterogéneo ("cosas para el piso nuevo") se lee como feed y el backstop
    stays quiet — help is lost, but no falsehood is told». It was true while the guard looked at ONE signal (the
    rows sharing vocabulary). A sofa, a lamp, and a microwave share none… **and are exactly the answer to that errand**.

    With V2-339's two signals, its prices (180 · 25 · 60 → ×7.2) are not absurd scales, so they are no longer
    read as a feed and the backstop DELIVERS. The renunciation was unnecessary."""
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.",
                                     ["Sofá cama gris — 180 €", "Lámpara de pie — 25 €",
                                      "Microondas Balay — 60 €"], "",
                                     errand="busca cosas para el piso nuevo")
    assert out, "el encargo heterogéneo vuelve a silenciarse: V2-339 revertido"
    assert "Lámpara de pie" in out and "Microondas Balay" in out
    # «Sofá cama gris» was excluded («sofá», «cama», «gris»: no distinctive token of ≥5 letters) — the
    # limitation this test recorded at the time. V2-471 closed it through the DATA path: a row
    # whose price (180) has not been spoken is an undelivered row, regardless of which tokens its title contains.
    assert "Sofá" in out, "la fila de título corto entra ahora por su dato (V2-471)"


# ── V2-364: the gate is no longer the waiting vocabulary; it is the QUESTION ─────────────────────────────────
#
# Until here, this backstop required the reply to SOUND like waiting (`_WAITING_REPLY_RE`), and that list was
# expanded TWICE in a single day chasing new forms —«te informo», «en cuanto sepa», «voy a
# reunir»— while still missing turns.
#
# Measured in `find-concert-tickets__es` (2026-08-27, supervisor round, 2/5), with the strict clock that
# V2-355 fixed and V2-362 put into the report:
#
#     ⏱ first candidate row: 72.2 s after the sheet was opened
#        · the turn named them 62.7 s AFTER they existed
#
# Sixty-five seconds of silence with TWENTY-TWO candidates written down and linked. The backstop eventually
# fired —at 137.3 s, exactly when the turn named them— but arrived late because the turns in
# between did not contain any of the list's phrases.
#
# Chasing the language is a race that cannot be won. What this exists to prevent is not «the reply
# sounding like waiting»: it is the operator being left without what is ALREADY in the sheet. The other two guards
# still do the fine-grained work —a long reply is already reporting something (>300 characters), and rows already
# mentioned are not re-announced (V2-189)—, so the only thing that truly needed protecting is the QUESTION: if the turn
# is asking something, hanging the rows behind it changes the subject and leaves it unanswered.

CONCIERTOS = ["La Bella y La Bestia — 45 €", "Concierto indie Sala But — 22 €", "Vetusta Morla — 38 €"]


def test_una_respuesta_que_no_suena_a_espera_TAMBIEN_entrega():
    """The measured case: turns that were not deliberately staying quiet; they simply were not on the list."""
    for r in ("Perfecto, lo dejo así entonces.", "Ahora mismo lo reviso.", "Vale."):
        out = RG.sheet_delivery_backstop(r, CONCIERTOS, "", errand="busca entradas de concierto")
        assert "Vetusta Morla" in out, r


def test_una_PREGUNTA_se_respeta_SIN_retener_la_entrega():
    """REVERTED by V2-371. The V2-364 version required absolute silence in response to a question, and that was the
    wrong degree: what must be protected is not delivery, but the TURN TO SPEAK.

    Staying quiet withholds; adding our question steals theirs. The solution is to deliver the facts and keep quiet —
    so all three forms remain the last question of the turn, which is what this case guarded."""
    for r in ("¿Prefieres sala pequeña o grande?", "Claro. ¿Te va bien el sábado?", "¿Lo reservo?"):
        out = RG.sheet_delivery_backstop(r, CONCIERTOS, "", errand="busca entradas")
        assert "Vetusta Morla" in out, r
        assert "?" not in out, r


def test_lo_que_ya_protegian_las_otras_guardas_sigue_protegido():
    """Widening the gate cannot loosen the rest: a long response that already reports something, and rows already
    mentioned, remain exactly as they were."""
    larga = ("¡Ya tengo entradas! Vetusta Morla el sábado por 38 € en la Sala But, y hay una de indie por 22 €. "
             "La Bella y La Bestia está a 45 € pero es teatro, no concierto, así que la dejo fuera. ¿Te abro "
             "alguna o sigo mirando otras salas?")
    assert RG.sheet_delivery_backstop(larga, CONCIERTOS, "") == ""
    dicho = "Ya te pasé Vetusta Morla a 38 €, el indie de la Sala But a 22 € y La Bella y La Bestia a 45 €."
    assert RG.sheet_delivery_backstop("Vale, lo dejo así.", CONCIERTOS, dicho) == ""


def test_el_backstop_de_ATASCO_conserva_la_puerta_vieja():
    """Deliberately and not by omission: reporting a stall is more intrusive than delivering what already exists, so
    there it is preferable for the response to be in waiting mode. Widening both at once would have inserted the
    stall phrase into turns where it was out of place."""
    assert RG.stalled_task_backstop("Perfecto, lo dejo así entonces.", "busca entradas", 5, "sin avanzar") == ""
    assert RG.stalled_task_backstop("Sigo con ello, te aviso.", "busca entradas", 5, "sin avanzar") != ""


def test_una_hoja_de_DOCE_filas_viaja_entera_hasta_su_techo_de_tamano(monkeypatch):
    """V2-479 — five rows were too few, and the change must be verifiable.

    Measured twice: `search-buy-camera__es` with FOURTEEN candidates (four of the five shown were
    accessories) and `find-best-hotel-city__us` round 6 with TWELVE hotels, two below the operator's cap,
    showing the faces. The turn concluded about the total of a set it had not seen in full.
    """
    from nucleo.flash import live_blocks as LB

    filas = [{"title": f"Hotel {i:02d}", "price": f"${100 + i}"} for i in range(12)]
    monkeypatch.setattr(LB, "boxes_of_tab", lambda t: ["results"], raising=False)
    monkeypatch.setattr("widgets.results.data.view_data", lambda c=None: {"items": filas}, raising=False)

    out = LB._sheet_top_rows("t1")
    assert len(out) == 12, f"se enseñaron {len(out)} de 12: el tope no subió"
    assert "Hotel 11" in out[-1], out[-1]
    assert not any("no listados aquí" in r for r in out), "avisa de un resto que no existe"


def test_y_el_techo_de_TAMANO_manda_sobre_el_conteo(monkeypatch):
    """The real bound is by SIZE, not by units — which is why this is tested by requesting MORE than twelve.

    With twelve rows the ceiling does not bite (measured: 926 of 1200 characters with maximum-length titles, meaning
    the twelve-row cap has one row of headroom), and that is fine: the ceiling exists so increasing `n` tomorrow does
    not put anything it pleases into the prompt. A test pretending that it cuts at twelve would make a false claim
    about the code it is supposed to protect.
    """
    from nucleo.flash import live_blocks as LB

    filas = [{"title": "H" * 70, "price": f"${i}"} for i in range(30)]
    monkeypatch.setattr(LB, "boxes_of_tab", lambda t: ["results"], raising=False)
    monkeypatch.setattr("widgets.results.data.view_data", lambda c=None: {"items": filas}, raising=False)

    out = LB._sheet_top_rows("t1", 30)
    cuerpo = [r for r in out if "no listados aquí" not in r]
    assert len(cuerpo) < 30, "el techo de tamaño no cortó nada con treinta filas largas"
    assert sum(len(r) for r in cuerpo) <= LB._SHEET_ROWS_BUDGET + 100, "el bloque se pasó de su techo"
    # V2-374 — what remains outside is still COUNTED: cutting off and staying quiet brings back the original defect.
    assert any("no listados aquí" in r for r in out), "cortó y se calló el resto"
