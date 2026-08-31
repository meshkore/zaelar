"""V2-142 (`reorder-prescription__es`) — two failures with one shape: something that is not this request
becomes part of it.

Turn 1, with a task from ANOTHER request still alive: «Tienes dos cosas: primero necesito los datos del recibo
de la luz para preparar la transferencia, y segundo voy a pedir la reposición de tu receta». The operator had
only ever mentioned the prescription. The background-task block told the model what to DO with the list, and
since V2-130 one thing the list is NOT (a register of his usual places) — but never that it is not part of what
he is asking for now. A small model with a list in front of it and a new request adds them together.

Turn 6, after the operator wrote «¿puedes buscar tú el teléfono de esa, por favor? Para eso te pido ayuda»:
«la forma más fiable es que tú busques "farmacia" en Google Maps y me pases el teléfono». The whole job handed
back, on a turn where zaelar has web_search and a browser. That one is not a prompt problem — the fix is to DO
the search, so it is a backstop, gated on nothing else already running.

Measured first, in both directions: the same words with the verb in the first person («busco yo el teléfono»,
«he mirado en Google Maps») are zaelar doing the work, and sending the operator to his OWN inbox or paper bill
is CORRECT behaviour that another case in this suite scores as such.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import probe
from nucleo.flash import prompt
from nucleo.flash import router_guards as g


HANDBACK = ('La forma más fiable ahora es que tú busques "farmacia" en Google Maps con tu ubicación '
            'y me pases el teléfono.')


class _Handback:
    async def stream(self, *_a, **_kw):
        yield HANDBACK


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


# ── handing a PUBLIC lookup back ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("reply", [
    HANDBACK,
    'la forma más rápida es buscar "farmacia Plaza de Chamberí" en Google Maps o llamar al 010',
    "puedes buscarlo tú en Google Maps y me pasas el teléfono",
    "lo más rápido es que busques el número en internet",
    "you can look it up on Google Maps and send me the number",
])
def test_sending_him_to_look_it_up_himself_is_handing_the_job_back(reply):
    assert g.hands_public_lookup_back(reply) is True


@pytest.mark.parametrize("reply", [
    # His OWN material: zaelar has no connector for it, and asking is the right move.
    "abre tu correo tú mismo, busca cualquier factura de luz reciente y dime cuál es",
    "mira el recibo cuando puedas y dame el número de factura",
    # Same words, first person — zaelar doing the looking.
    "busco yo el teléfono y te lo digo",
    "voy a buscar en Google el horario y te digo",
    "estoy buscando la farmacia en Google Maps",
    "he mirado en Google Maps y la más cercana es esta",
    "te paso las opciones que he encontrado en Google",
    "hola, qué tal",
])
def test_and_these_are_not(reply):
    assert g.hands_public_lookup_back(reply) is False


def test_the_backstop_does_the_search_instead_of_just_forbidding_it(fresh_db, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _Handback)
    monkeypatch.setattr("nucleo.dispatch.has_active", lambda: False)
    res = asyncio.run(probe.run_turn(
        "¿puedes buscar tú el teléfono de esa, por favor? Para eso te pido ayuda.",
        sid="t-v142-a", ingest=False))
    probe._SESSIONS.pop("t-v142-a", None)
    assert res["action"] == "escalate"


def test_but_not_while_something_is_already_running(fresh_db, monkeypatch):
    """With a live task the same sentence can be a suggestion while the work happens, and re-escalating would
    run it twice — the cost V2-123 measured."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _Handback)
    monkeypatch.setattr("nucleo.dispatch.has_active", lambda: True)
    res = asyncio.run(probe.run_turn(
        "¿puedes buscar tú el teléfono de esa, por favor?", sid="t-v142-b", ingest=False))
    probe._SESSIONS.pop("t-v142-b", None)
    assert res["action"] != "escalate"


# ── a running task is not part of the new request ───────────────────────────────────────────────────────────
def test_a_live_task_is_context_not_part_of_the_new_request(monkeypatch):
    from nucleo import dispatch as _disp
    monkeypatch.setattr(_disp, "pending_summaries", lambda: [
        {"id": "7", "request": "pagar la factura de la luz de Iberdrola", "secs": 40, "phase": "",
         "pct": -1, "done": 0, "total": 0, "note": "", "silent_s": 5}])
    live = prompt.live_state()
    assert "NO forman parte de lo que te pide AHORA" in live
    assert "tienes dos cosas" in live          # the exact shape it produced, named


def test_the_prompt_says_who_does_the_searching(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "BUSCAR un dato es TU trabajo" in system


def test_a_search_result_is_only_his_if_you_searched_with_his_words(fresh_db):
    """Turn 6 coined «Farmacia Plaza de Chamberí» out of «la plaza de mi barrio» + «Chamberí», turn 7 searched
    THAT and reported someone else's address and phone as his — through two corrections. The existing rule
    already banned inventing the datum; what was missing is that searching an invention disguises it as a
    found fact, which is what beat the correction."""
    system, _ = prompt.build_flash_system()
    assert "busca lo que ÉL ha dicho" in system
    assert "solo es SUYO si buscaste con sus palabras" in system


# ── V2-156: the third way of handing the job back ──────────────────────────────────────────────────────────
#
# Turn 1 of `restaurant-tonight-madrid`, with «resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio»:
# «Te abro la web de Casa Lucio para que hagas la reserva». The operator had to reply «No, quiero que
# reserves TÚ la mesa, no solo que me pases la web».
#
# It is neither «búscalo tú» (V2-142) nor «avísame tú» (V2-136): it is handing the ACTION back wrapped in a favor,
# which is why neither rule covered it. And it was not a lack of capability — the escalation happened and the worker
# went to TheFork; what failed was what it said.
def test_opening_the_page_so_he_does_it_is_also_handing_the_job_back(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "te abro la página y reservas tú" in system
    assert "es devolverle la acción" in system


def test_and_it_says_that_opening_a_page_is_working_not_delegating(fresh_db):
    """Without this half, the rule reads as «no abras páginas», which is the opposite of what is wanted."""
    system, _ = prompt.build_flash_system()
    assert "una forma de TRABAJAR tú" in system


def test_the_wall_is_still_a_legitimate_stopping_point(fresh_db):
    """This case scores stopping at the wall and saying so as the MAXIMUM. The rule cannot prohibit that — it only
    requires trying first."""
    system, _ = prompt.build_flash_system()
    assert "llega hasta ahí y dilo entonces" in system


def test_the_older_two_forms_are_still_covered(fresh_db):
    """The fix expands the family rather than replacing it: the two earlier rules remain."""
    system, _ = prompt.build_flash_system()
    assert "El trabajo es TUYO" in system
    assert "BUSCAR un dato es TU trabajo" in system


# ── V2-357: CANDIDATES are not invented either ────────────────────────────────────────────────────────
#
# The rule above (V2-142) covers the OPERATOR'S data —his city, his pharmacy, his gym— and says nothing about
# the candidates for a job. Measured in `weekend-plan-barcelona__es` (2026-08-27, supervisor round): on TURN 2,
# with the worker just started and zero rows in the sheet, zaelar proposed the via ferratas «de Centelles» and
# «Teresina» — with no price, schedule, link, or source. The judge made it blocker nº1: «nombres plausibles sacados
# del conocimiento del modelo, no de una búsqueda… tiene forma de resultado y no lo es».
#
# It is the third time in the same batch with the same pattern —V2-344 and V2-348 were the other two—: the
# correct instruction, scoped to the wrong branch. And here the harm is worse than silence, because the operator
# CANNOT distinguish an invented name from one found: he trusts it and makes a mistake.

def test_los_candidatos_salen_de_la_busqueda_no_del_modelo():
    system, _ = prompt.build_flash_system()
    assert "CANDIDATOS de lo que te encarga" in system
    assert "JAMÁS de lo que tú sepas" in system


def test_y_dice_que_NO_TENER_es_una_respuesta_completa():
    """Without this half, the block only prohibits, and the model is left without a legitimate way out — which is
    exactly how it ends up inventing. Same lesson as V2-187."""
    system, _ = prompt.build_flash_system()
    assert "«todavía no tengo candidatos» es una respuesta COMPLETA" in system


def test_la_EXCEPCION_va_dentro_del_imperativo():
    """Explaining what something IS in general remains allowed and helpful. It goes in the same sentence, not
    another one: two commands in a paragraph come out heads or tails (V2-348)."""
    system, _ = prompt.build_flash_system()
    assert "qué ES algo" in system and "sí puedes" in system
    i, j = system.index("CANDIDATOS de lo que te encarga"), system.index("qué ES algo")
    assert 0 < j - i < 700, "la excepción se ha separado del imperativo que la acota"


def test_la_regla_HERMANA_sigue_en_pie():
    """The opposite side: the V2-142 rule cannot disappear when its counterpart is added."""
    system, _ = prompt.build_flash_system()
    assert "busca lo que ÉL ha dicho" in system
    assert "Un resultado solo es SUYO" in system
