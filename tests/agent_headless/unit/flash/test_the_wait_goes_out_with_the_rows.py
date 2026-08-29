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


def test_una_pregunta_corta_ENTREGA_los_hechos_y_no_añade_la_nuestra():
    """INVERTIDO por V2-371, y se conserva aquí porque el ejemplo es el mismo. Decía
    `test_a_non_waiting_short_reply_is_untouched` y exigía silencio ante una pregunta.

    Lo que ese silencio costó, medido en `search-buy-motorcycle__es` (2026-08-27): once candidatos con nombre
    y enlace en la hoja, 87,4 s de retención, y los turnos que preguntaban caían al backstop de ATASCO, que
    le colgaba detrás NUESTRA pregunta de gestión — el operador recibió dos veces la misma pregunta, una ya
    contestada, y ni uno de los once candidatos.

    Lo que protegía sigue protegido y es la mitad que importa: no se le roba la palabra. Se entregan los
    HECHOS y no se añade pregunta, así que la única que cierra el turno es la suya."""
    out = RG.sheet_delivery_backstop("¿Prefieres cuerdas de metal o nylon?", ROWS, "")
    assert "Fender CD-60" in out
    assert "?" not in out


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
    # V2-340: el cableado se mudó a `delivery.apply_to_reply`, así que el guarda mira los DOS sitios — que
    # el probe llame, y que la llamada siga llevando el encargo. Comprobar solo el probe daría verde con la
    # función vacía; comprobar solo la función, con el probe sin llamarla.
    probe = "\n".join(ln for ln in Path("nucleo/flash/probe.py").read_text().splitlines()
                      if not ln.strip().startswith("#"))
    assert "delivery.apply_to_reply(spoken" in probe or "_delivery.apply_to_reply(spoken" in probe
    deliv = "\n".join(ln for ln in Path("nucleo/flash/delivery.py").read_text().splitlines()
                       if not ln.strip().startswith("#"))
    assert "sheet_delivery_backstop(spoken" in deliv
    assert "any_live_task_rows()" in deliv
    assert "errand=encargo" in deliv, "sin el encargo, la categoría del dominio mata la frescura de todas las filas"


def test_junk_rows_from_an_unfiltered_feed_are_never_announced():
    """Ronda 35 (2026-08-25 02:20): el worker falló el tecleo, la página devolvió su portada sin filtrar y la
    hoja se llenó de Beyblades, cosmética, velas y un Ford Fiesta. El modelo hizo BIEN en no entregarla — y
    este backstop la habría anunciado. Lo que las delata NO es el encargo (ver el test de abajo) sino que no
    comparten NADA entre sí: unos resultados de búsqueda son coherentes, un feed no."""
    junk = ["Juguetes Beyblade Die-Cast (COLOR AL AZAR) — 15 €",
            "Pack 2x Paula's Choice BHA 2% Exfoliante 118ml — 30 €",
            "Velas de Gruta y Gel artesanales — 12 €",
            "Ford Fiesta 1.0 EcoBoost ST-Line — 8.900 €"]
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", junk, "",
                                     errand="busca una guitarra acústica por menos de 150€")
    assert out == "", "anunciar basura deterministamente es peor que la espera que corrige"


def test_entities_that_never_repeat_the_category_STILL_fire():
    """El defecto de la primera puerta, medido en la tanda de las 10:04: exigir compartir palabra con el
    ENCARGO está adaptado a un dominio — en un marketplace el título repite la categoría, pero un hotel se
    llama «La Banda Living Hostel» y un vuelo «Ryanair directo». Con 36 filas legítimas de hoteles en la
    hoja, el backstop no disparó ni una vez y el juez fichó «retención de 202 s»."""
    hoteles = ["La Banda Living Hostel — € 98", "New Samay Hostel — € 88",
               "La Banda Rooftop Hostel — € 118"]
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", hoteles, "",
                                     errand="Busca el mejor hotel en Sevilla, menos de 120€ la noche")
    assert "La Banda Living Hostel" in out


def test_two_rows_are_never_called_a_feed():
    """Dos cosas distintas no son un feed: por debajo de tres filas no se juzga coherencia, porque callar ahí
    reintroduce justo el silencio que este backstop existe para quitar."""
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.",
                                     ["Hotel Alfonso XIII — 210 €", "Corral del Rey — 180 €"], "",
                                     errand="busca hotel en Sevilla")
    assert "Alfonso XIII" in out


def test_matching_rows_still_fire_with_the_membership_gate():
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.", ROWS, "",
                                     errand="busca una guitarra acústica por menos de 150€")
    assert "Fender CD-60" in out


def test_a_heterogeneous_errand_YA_NO_es_un_coste_asumido():
    """Este test fijaba un coste que V2-339 ha dejado de pagar, y se conserva invertido para que la mejora
    quede registrada en el mismo sitio donde estaba la renuncia.

    Decía: «un encargo legítimamente heterogéneo ("cosas para el piso nuevo") se lee como feed y el backstop
    calla — se pierde una ayuda, no se dice una falsedad». Era cierto mientras la guarda miraba UNA señal (que
    las filas compartieran vocabulario). Un sofá, una lámpara y un microondas no comparten ninguna… **y son
    exactamente la respuesta a ese encargo**.

    Con las dos señales de V2-339, sus precios (180 · 25 · 60 → ×7,2) no son escalas absurdas, así que ya no
    se leen como feed y el backstop ENTREGA. La renuncia sobraba."""
    out = RG.sheet_delivery_backstop("Sigo con ello, te aviso.",
                                     ["Sofá cama gris — 180 €", "Lámpara de pie — 25 €",
                                      "Microondas Balay — 60 €"], "",
                                     errand="busca cosas para el piso nuevo")
    assert out, "el encargo heterogéneo vuelve a silenciarse: V2-339 revertido"
    assert "Lámpara de pie" in out and "Microondas Balay" in out
    # «Sofá cama gris» quedaba fuera («sofá», «cama», «gris»: ningún token distintivo de ≥5 letras) — la
    # limitación que esta prueba dejó ANOTADA en su día. V2-471 la cerró por el camino del DATO: una fila
    # cuyo precio (180) no ha sonado es una fila sin entregar, tenga el título los tokens que tenga.
    assert "Sofá" in out, "la fila de título corto entra ahora por su dato (V2-471)"


# ── V2-364: la puerta ya no es el vocabulario de espera, es la PREGUNTA ─────────────────────────────────
#
# Hasta aquí este backstop exigía que la respuesta SONARA a espera (`_WAITING_REPLY_RE`), y esa lista se
# ensanchó DOS VECES en un solo día persiguiendo formas nuevas —«te informo», «en cuanto sepa», «voy a
# reunir»— sin dejar de perder turnos.
#
# Medido en `find-concert-tickets__es` (2026-08-27, ronda del supervisor, 2/5), con el reloj estricto que
# V2-355 arregló y V2-362 sacó al informe:
#
#     ⏱ primera fila de candidatos: 72,2 s desde que se abrió la hoja
#        · el turno los nombró 62,7 s DESPUÉS de que existieran
#
# Sesenta y cinco segundos de silencio con VEINTIDÓS candidatos escritos y con enlace. El backstop acabó
# disparando —a los 137,3 s, que es justo cuando el turno los nombró— pero llegó tarde porque los turnos de en
# medio no decían ninguna de las frases de la lista.
#
# Perseguir el idioma es una carrera que no se gana. Lo que esto existe para evitar no es «que la respuesta
# suene a espera»: es que el operador se quede sin lo que YA está en su hoja. Las otras dos guardas siguen
# haciendo el trabajo fino —una respuesta larga ya está contando algo (>300 caracteres), y las filas ya dichas
# no se re-anuncian (V2-189)—, así que lo único que había que proteger de verdad es la PREGUNTA: si el turno le
# está preguntando algo, colgarle las filas detrás le cambia el tema y se queda sin contestar.

CONCIERTOS = ["La Bella y La Bestia — 45 €", "Concierto indie Sala But — 22 €", "Vetusta Morla — 38 €"]


def test_una_respuesta_que_no_suena_a_espera_TAMBIEN_entrega():
    """El caso medido: turnos que no callaban a propósito, simplemente no estaban en la lista."""
    for r in ("Perfecto, lo dejo así entonces.", "Ahora mismo lo reviso.", "Vale."):
        out = RG.sheet_delivery_backstop(r, CONCIERTOS, "", errand="busca entradas de concierto")
        assert "Vetusta Morla" in out, r


def test_una_PREGUNTA_se_respeta_SIN_retener_la_entrega():
    """INVERTIDO por V2-371. La versión de V2-364 exigía silencio absoluto ante una pregunta, y ese era el
    error de grado: lo que hay que proteger no es la entrega, es el TURNO DE PALABRA.

    Callar retiene; añadir nuestra pregunta le roba la suya. La salida es entregar los hechos y callarnos —
    con lo que sus tres formas siguen siendo la última pregunta del turno, que es lo que este caso vigilaba."""
    for r in ("¿Prefieres sala pequeña o grande?", "Claro. ¿Te va bien el sábado?", "¿Lo reservo?"):
        out = RG.sheet_delivery_backstop(r, CONCIERTOS, "", errand="busca entradas")
        assert "Vetusta Morla" in out, r
        assert "?" not in out, r


def test_lo_que_ya_protegian_las_otras_guardas_sigue_protegido():
    """Ensanchar la puerta no puede aflojar el resto: una respuesta larga que ya cuenta algo, y las filas ya
    dichas, se quedan exactamente como estaban."""
    larga = ("¡Ya tengo entradas! Vetusta Morla el sábado por 38 € en la Sala But, y hay una de indie por 22 €. "
             "La Bella y La Bestia está a 45 € pero es teatro, no concierto, así que la dejo fuera. ¿Te abro "
             "alguna o sigo mirando otras salas?")
    assert RG.sheet_delivery_backstop(larga, CONCIERTOS, "") == ""
    dicho = "Ya te pasé Vetusta Morla a 38 €, el indie de la Sala But a 22 € y La Bella y La Bestia a 45 €."
    assert RG.sheet_delivery_backstop("Vale, lo dejo así.", CONCIERTOS, dicho) == ""


def test_el_backstop_de_ATASCO_conserva_la_puerta_vieja():
    """A propósito y no por olvido: contar un atasco es más intrusivo que entregar lo que ya existe, así que
    ahí sí conviene que la respuesta esté en modo espera. Ensanchar los dos a la vez habría metido la frase del
    atasco en turnos donde no venía a cuento."""
    assert RG.stalled_task_backstop("Perfecto, lo dejo así entonces.", "busca entradas", 5, "sin avanzar") == ""
    assert RG.stalled_task_backstop("Sigo con ello, te aviso.", "busca entradas", 5, "sin avanzar") != ""


def test_una_hoja_de_DOCE_filas_viaja_entera_hasta_su_techo_de_tamano(monkeypatch):
    """V2-479 — cinco filas eran pocas, y el cambio tiene que poder comprobarse.

    Medido dos veces: `search-buy-camera__es` con CATORCE candidatos (cuatro de las cinco mostradas eran
    accesorios) y `find-best-hotel-city__us` ronda 6 con DOCE hoteles, dos por debajo del tope del operador,
    mostrando las caras. El turno concluyó sobre el total un conjunto que no había visto entero.
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
    """El bound real es de TAMAÑO, no de unidades — y por eso se prueba pidiendo MÁS de doce.

    A doce filas el techo no muerde (medido: 926 de 1200 caracteres con los títulos al máximo, o sea que el
    tope de doce lleva una fila de holgura), y eso está bien: el techo existe para que subir `n` mañana no
    meta en el prompt lo que le dé la gana. Un test que fingiera que corta a doce estaría afirmando algo
    falso sobre el código que dice guardar.
    """
    from nucleo.flash import live_blocks as LB

    filas = [{"title": "H" * 70, "price": f"${i}"} for i in range(30)]
    monkeypatch.setattr(LB, "boxes_of_tab", lambda t: ["results"], raising=False)
    monkeypatch.setattr("widgets.results.data.view_data", lambda c=None: {"items": filas}, raising=False)

    out = LB._sheet_top_rows("t1", 30)
    cuerpo = [r for r in out if "no listados aquí" not in r]
    assert len(cuerpo) < 30, "el techo de tamaño no cortó nada con treinta filas largas"
    assert sum(len(r) for r in cuerpo) <= LB._SHEET_ROWS_BUDGET + 100, "el bloque se pasó de su techo"
    # V2-374 — lo que queda fuera se sigue CONTANDO: cortar y callarse devuelve el defecto original.
    assert any("no listados aquí" in r for r in out), "cortó y se calló el resto"
