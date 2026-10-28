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
