"""Una pregunta abierta no es motivo para RETENER la entrega — solo para no robarle la palabra (V2-371).

V2-364 cambió la puerta del backstop de entrega: dejó de ser el vocabulario de espera y pasó a ser LA
PREGUNTA. El razonamiento era bueno —colgarle filas detrás a una pregunta puede dejarla sin contestar— y la
conclusión, callar del todo, era demasiado.

Medido en `search-buy-motorcycle__es` (2026-08-27, 3/5) con ONCE candidatos con nombre y enlace en la hoja:

    122,3 s   primera fila de candidatos en la hoja
    +87,4 s   lo que tardó el turno en nombrar una
    175,6 s   📬 backstop de ATASCO → «¿La paro y probamos por otro lado, o le doy un poco más de margen?»
    446,2 s   📬 backstop de ATASCO → la MISMA pregunta otra vez

Las dos preguntas de gestión que el juez le reprochó a zaelar las escribimos NOSOTROS, y la segunda va
después de que el operador ya hubiera contestado «para ya y prueba en otro sitio». El camino es este: el
turno preguntaba algo, la puerta de V2-364 silenciaba la entrega, y con la entrega callada el flujo caía al
backstop de atasco — cuyo propio comentario dice que con resultados delante la cara correcta es entregarlos.
Su guarda, sin embargo, no era «no hay filas» sino «la entrega no disparó», y esas dos cosas dejaron de ser
la misma en cuanto V2-364 añadió un motivo nuevo para no disparar.

Ahora, con una pregunta abierta, se entregan los HECHOS y se calla la nuestra: la única pregunta que cierra
el turno sigue siendo la suya. Y como la entrega dispara, el flujo ya no llega al atasco — la segunda mitad
se arregla sola, que es la señal de que la causa era una y no dos.
"""
import pytest

from nucleo.flash import delivery as D


@pytest.fixture(autouse=True)
def _hablando_en_castellano(monkeypatch):
    """These tests assert the SPANISH wording, so they state the language instead of inheriting it.

    Until V2-475 this family had one wording and the language was invisible; now that the sentence follows
    the operator's language, a test that leaves it ambient is really asserting «whatever the default is»
    (English on a fresh engine) — which is how a Spanish assertion silently starts grading English output.
    """
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es")


FILAS = ["Yamaha R125 Blanca Deportiva — 500 €", "Brixton 125cc — 1200 €",
         "Honda Varadero XL125V 2006 — 1400 €"]
ENCARGO = "moto de segunda mano de 125cc en buen estado"


def _bs(reply, dicho="", filas=None):
    return D.sheet_delivery_backstop(reply, filas if filas is not None else FILAS, dicho, errand=ENCARGO)


# ── el caso medido ─────────────────────────────────────────────────────────────────────────────────────────

def test_la_pregunta_de_gestion_ya_no_retiene_los_once_candidatos():
    """La forma exacta de la ronda: el turno pregunta si parar, y había once filas sin entregar."""
    out = _bs("¿La paro y probamos por otro lado, o le doy un poco más de margen?")
    assert out, "la entrega volvió a callarse ante una pregunta"
    assert "Yamaha R125" in out


def test_con_una_pregunta_abierta_NO_añadimos_la_nuestra():
    """Lo que la puerta de V2-364 protegía, conservado: si cerramos nosotros el turno con otra pregunta, la
    suya se queda sin contestar. Se entregan los hechos y se calla."""
    out = _bs("¿La paro o le doy un poco más de margen?")
    assert "?" not in out
    assert "sigo afinando" not in out


def test_sin_pregunta_el_cierre_de_siempre_SIGUE():
    """Sensibilidad por el otro lado: sin pregunta suya, preguntar nosotros es lo correcto — es lo que
    convierte una entrega en una conversación."""
    out = _bs("Vale, te aviso en cuanto tenga novedades.")
    assert "Dime si alguno te encaja o sigo afinando." in out


@pytest.mark.parametrize("reply", [
    "¿En qué ciudad la quieres?",
    "Dime una cosa, ¿te vale con 125cc o prefieres más?",
    "¿te importa el color?",
])
def test_una_pregunta_de_DATO_tampoco_retiene(reply):
    """La misma regla, y a propósito: aunque la pregunta sea legítima y necesaria, tener las filas guardadas
    no la ayuda a contestarse. Se entregan igual, sin robarle la palabra."""
    out = _bs(reply)
    assert out and "?" not in out


# ── lo que NO cambia ───────────────────────────────────────────────────────────────────────────────────────

def test_las_filas_YA_dichas_siguen_sin_re_anunciarse():
    """El disco rayado de V2-189 no se reabre por esto.

    V2-471 redefinió «dicha»: nombre + DATO (una fila con precio no está entregada hasta que su precio
    suena — ronda 12 del monitor). El fixture dice ahora las dos mitades, que es lo que una entrega real
    dice; los nombres a secas los cubre `test_a_named_row_whose_datum_never_sounded_is_still_fresh`."""
    dicho = ("Te he encontrado una Yamaha R125 por 500 €, una Brixton 125cc por 1200 € y una "
             "Honda Varadero XL125V del 2006 por 1400 €")
    assert _bs("¿La paro o sigo?", dicho=dicho) == ""


def test_una_respuesta_LARGA_sigue_sin_pisarse():
    """Una respuesta larga ya está contando algo; añadirle filas detrás sería peor."""
    largo = "¿La paro? " + ("Te cuento con detalle lo que llevo hasta ahora y por qué. " * 8)
    assert len(largo) > 300
    assert _bs(largo) == ""


def test_sin_filas_frescas_no_hay_nada_que_entregar():
    assert _bs("¿La paro o le doy margen?", filas=[]) == ""


# ── la segunda mitad: el atasco deja de colgar su pregunta ─────────────────────────────────────────────────

def test_con_filas_frescas_el_flujo_NO_llega_al_backstop_de_atasco(monkeypatch):
    """La causa era UNA. Con la entrega disparando, `apply_to_reply` vuelve antes de mirar el atasco, así que
    la pregunta de gestión que el operador recibió dos veces ya no se escribe."""
    from nucleo.flash import live_blocks as LB
    monkeypatch.setattr(LB, "any_live_task_rows", lambda n=3: (ENCARGO, [f.strip("«»") for f in FILAS]))
    llamado = {"atasco": False}

    def _no_deberia(*a, **k):
        llamado["atasco"] = True
        return ("un encargo", 5, "sin avanzar")
    monkeypatch.setattr(LB, "any_stalled_task", _no_deberia)

    out = D.apply_to_reply("¿La paro y probamos por otro lado, o le doy un poco más de margen?", [])
    assert "Yamaha R125" in out
    assert not llamado["atasco"], "con filas frescas delante no se habla del atasco"


def test_sin_filas_el_atasco_SIGUE_contandose(monkeypatch):
    """Y la simétrica, que es la que impide que este arreglo silencie V2-359: sin nada que entregar, un
    atasco detectado se cuenta igual que siempre."""
    from nucleo.flash import live_blocks as LB
    monkeypatch.setattr(LB, "any_live_task_rows", lambda n=3: ("", []))
    monkeypatch.setattr(LB, "any_stalled_task", lambda: ("buscar una moto", 5, "sin avanzar"))
    out = D.apply_to_reply("Sigo con ello, te aviso.", [])
    assert "puede estar atascada" in out


# ── el silencio se ve ──────────────────────────────────────────────────────────────────────────────────────

def test_callar_ante_una_PREGUNTA_deja_su_fila(monkeypatch):
    """V2-336 aplicado al motivo nuevo. Reconstruir esta ronda costó cruzar relojes porque los turnos que
    importaban —los que preguntaban— no emitían nada: la guarda del evento seguía siendo el vocabulario de
    espera que V2-364 ya no usaba para decidir."""
    from nucleo.flash import live_blocks as LB
    vistos = []
    monkeypatch.setattr(LB, "any_live_task_rows", lambda n=3: (ENCARGO, [f.strip("«»") for f in FILAS]))
    monkeypatch.setattr(LB, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(D, "_emit", lambda label, **k: vistos.append((label, k)))
    # nombre + dato: desde V2-471 una fila con precio solo queda «dicha» cuando su precio ha sonado
    dicho = ("Te he encontrado una Yamaha R125 por 500 €, una Brixton 125cc por 1200 € y una "
             "Honda Varadero XL125V del 2006 por 1400 €")
    D.apply_to_reply("¿La paro o sigo?", [{"role": "assistant", "content": dicho}])
    assert any("CALLÓ" in l for l, _ in vistos), "un silencio sin fila es indistinguible de una avería"


def test_a_named_row_whose_datum_never_sounded_is_still_fresh():
    """V2-471, second door of the same property: the deliverable is «name — datum», not the name alone.

    Round 12 of `cheapest-monitor__us`: zaelar had said «Dell S2725QS» in turn 2, so every Dell row counted
    as delivered by the title-token scan — while the $279.99 the row carried never sounded, which was the
    exact thing the five-turn «let me confirm the price» loop owed the operator. A row with a datum is
    delivered when its datum has sounded; the name alone only settles rows that carry no datum."""
    from nucleo.flash import delivery as D
    said = "I've got the Dell S2725QS on Amazon now, let me verify its current price."
    row = "Dell 27 Plus 4K Monitor S2725QS — $279.99"
    out = D.sheet_delivery_backstop("Still pulling that together, give me a moment.",
                                    [row], said_before=said, errand="cheapest 27 inch 4K monitor")
    assert "$279.99" in out, out
    # …and once the datum HAS sounded, the row is delivered — no broken record (V2-189)
    out2 = D.sheet_delivery_backstop("Still pulling that together, give me a moment.",
                                     [row], said_before=said + " It sells for $279.99 right now.",
                                     errand="cheapest 27 inch 4K monitor")
    assert out2 == "", out2
