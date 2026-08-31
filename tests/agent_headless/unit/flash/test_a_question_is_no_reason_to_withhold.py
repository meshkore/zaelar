"""An open question is no reason to WITHHOLD delivery — only a reason not to take the floor from it (V2-371).

V2-364 changed the delivery backstop gate: it stopped being the waiting vocabulary and became THE
QUESTION. The reasoning was sound —hanging rows behind a question can leave it unanswered— but the
conclusion, to stay completely silent, went too far.

Measured in `search-buy-motorcycle__es` (2026-08-27, 3/5) with ELEVEN candidates with a name and link in the sheet:

    122.3 s   first row of candidates in the sheet
    +87.4 s   how long the turn took to name one
    175.6 s   📬 STALL backstop → “Should I stop it and try somewhere else, or give it a little more time?”
    446.2 s   📬 STALL backstop → the SAME question again

We wrote the two management questions that the judge reproached zaelar for, and the second came
after the operator had already answered “stop now and try somewhere else.” The path was this: the
turn asked something, the V2-364 gate silenced delivery, and with delivery silenced the flow fell into the
stall backstop — whose own comment says that when results are in front of you, the right move is to deliver them.
Its guard, however, was not “there are no rows” but “delivery did not trigger,” and those two things stopped being
the same as soon as V2-364 added a new reason not to trigger.

Now, with an open question, the FACTS are delivered and ours stays silent: the only question closing
the turn remains theirs. And because delivery triggers, the flow no longer reaches the stall — the second half
fixes itself, which is the sign that there was one cause, not two.
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


# ── the measured case ───────────────────────────────────────────────────────────────────────────────────────

def test_la_pregunta_de_gestion_ya_no_retiene_los_once_candidatos():
    """The exact form of the round: the turn asks whether to stop, and eleven rows had not been delivered."""
    out = _bs("¿La paro y probamos por otro lado, o le doy un poco más de margen?")
    assert out, "delivery went silent again in response to a question"
    assert "Yamaha R125" in out


def test_con_una_pregunta_abierta_NO_añadimos_la_nuestra():
    """The thing V2-364's gate protected, preserved: if we close the turn with another question, theirs
    goes unanswered. The facts are delivered and we stay silent."""
    out = _bs("¿La paro o le doy un poco más de margen?")
    assert "?" not in out
    assert "sigo afinando" not in out


def test_sin_pregunta_el_cierre_de_siempre_SIGUE():
    """Sensitivity in the other direction: without their question, asking ours is correct — it is what
    turns a delivery into a conversation."""
    out = _bs("Vale, te aviso en cuanto tenga novedades.")
    assert "Dime si alguno te encaja o sigo afinando." in out


@pytest.mark.parametrize("reply", [
    "¿En qué ciudad la quieres?",
    "Dime una cosa, ¿te vale con 125cc o prefieres más?",
    "¿te importa el color?",
])
def test_una_pregunta_de_DATO_tampoco_retiene(reply):
    """The same rule, deliberately: even if the question is legitimate and necessary, keeping the rows
    queued does not help it get answered. They are delivered anyway, without taking the floor from it."""
    out = _bs(reply)
    assert out and "?" not in out


# ── what does NOT change ───────────────────────────────────────────────────────────────────────────────────

def test_las_filas_YA_dichas_siguen_sin_re_anunciarse():
    """The V2-189 broken record is not reopened by this.

    V2-471 redefined “said”: name + DATUM (a row with a price is not delivered until its price
    has sounded — round 12 of the monitor). The fixture now says both halves, as a real delivery does;
    names alone are covered by `test_a_named_row_whose_datum_never_sounded_is_still_fresh`."""
    dicho = ("Te he encontrado una Yamaha R125 por 500 €, una Brixton 125cc por 1200 € y una "
             "Honda Varadero XL125V del 2006 por 1400 €")
    assert _bs("¿La paro o sigo?", dicho=dicho) == ""


def test_una_respuesta_larga_que_YA_NOMBRA_sus_filas_no_se_pisa():
    """The real protection against overwriting a delivery: the turn has already said what the sheet contains.

    Until V2-478 this was approximated by LENGTH (“a long response is already saying something”). The
    approximation was convenient and false —see the test below—, so the real property is now asserted:
    if the rows have already sounded, `fresh` is empty and nothing is added, regardless of the turn's length.
    """
    largo = ("Te cuento con detalle lo que llevo hasta ahora y por qué, con calma. " * 4) + \
            ("Tengo una Yamaha R125 Blanca Deportiva por 500 €, una Brixton 125cc por 1200 € y una "
             "Honda Varadero XL125V del 2006 por 1400 €.")
    assert len(largo) > 300
    assert _bs(largo) == ""


def test_una_respuesta_LARGA_que_NO_NOMBRA_NADA_sí_recibe_las_filas():
    """The defect that toppled the old premise, measured in `find-best-hotel-city__us` round 5 (2026-08-29).

    The turn was long and said “I've got a partial shortlist up on screen — six central candidates for that
    weekend”: it named neither a hotel nor a price. With the 300-character gate, that turn was protected
    as if it were delivering something, and the operator got LESS than after a “I'll let you know” — with
    the added conviction that it already had results. Long is not the same as delivered.
    """
    narrando = ("Ya tengo una preselección en pantalla con varios candidatos centrales para ese fin de "
                "semana, y te cuento cómo la he montado y qué criterios he ido aplicando por el camino, "
                "porque hay bastante que explicar sobre las opciones disponibles y sus condiciones, y "
                "también sobre lo que he tenido que descartar antes de llegar hasta aquí con todo esto.")
    assert len(narrando) > 300
    out = _bs(narrando)
    assert "Yamaha R125" in out


def test_sin_filas_frescas_no_hay_nada_que_entregar():
    assert _bs("¿La paro o le doy margen?", filas=[]) == ""


# ── the second half: the stall stops hanging its question ──────────────────────────────────────────────────

def test_con_filas_frescas_el_flujo_NO_llega_al_backstop_de_atasco(monkeypatch):
    """The cause was ONE. With delivery triggering, `apply_to_reply` returns before checking the stall, so
    the management question the operator received twice is no longer written."""
    from nucleo.flash import live_blocks as LB
    monkeypatch.setattr(LB, "any_live_task_rows", lambda n=3: (ENCARGO, [f.strip("«»") for f in FILAS]))
    llamado = {"atasco": False}

    def _no_deberia(*a, **k):
        llamado["atasco"] = True
        return ("un encargo", 5, "sin avanzar")
    monkeypatch.setattr(LB, "any_stalled_task", _no_deberia)

    out = D.apply_to_reply("¿La paro y probamos por otro lado, o le doy un poco más de margen?", [])
    assert "Yamaha R125" in out
    assert not llamado["atasco"], "with fresh rows in front, the stall is not mentioned"


def test_sin_filas_el_atasco_SIGUE_contandose(monkeypatch):
    """And the symmetric case, which keeps this fix from silencing V2-359: with nothing to deliver, a
    detected stall is reported just as before."""
    from nucleo.flash import live_blocks as LB
    monkeypatch.setattr(LB, "any_live_task_rows", lambda n=3: ("", []))
    monkeypatch.setattr(LB, "any_stalled_task", lambda: ("buscar una moto", 5, "sin avanzar"))
    out = D.apply_to_reply("Sigo con ello, te aviso.", [])
    assert "puede estar atascada" in out


# ── the silence is visible ─────────────────────────────────────────────────────────────────────────────────

def test_callar_ante_una_PREGUNTA_deja_su_fila(monkeypatch):
    """V2-336 applied to the new reason. Reconstructing this round required cross-referencing clocks because
    the turns that mattered —the ones asking questions— emitted nothing: the event guard was still the waiting
    vocabulary that V2-364 no longer used to make its decision."""
    from nucleo.flash import live_blocks as LB
    vistos = []
    monkeypatch.setattr(LB, "any_live_task_rows", lambda n=3: (ENCARGO, [f.strip("«»") for f in FILAS]))
    monkeypatch.setattr(LB, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(D, "_emit", lambda label, **k: vistos.append((label, k)))
    # name + datum: since V2-471 a row with a price is only “said” once its price has sounded
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
