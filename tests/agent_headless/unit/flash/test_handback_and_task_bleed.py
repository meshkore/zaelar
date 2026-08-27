"""V2-142 (`reorder-prescription__es`) — two failures with one shape: something that is not this request
becoming part of it.

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


# ── V2-156: la tercera forma de devolver el encargo ──────────────────────────────────────────────────────────
#
# Turno 1 de `restaurant-tonight-madrid`, a «resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio»:
# «Te abro la web de Casa Lucio para que hagas la reserva». El operador tuvo que contestar «No, quiero que
# reserves TÚ la mesa, no solo que me pases la web».
#
# No es «búscalo tú» (V2-142) ni «avísame tú» (V2-136): es devolverle la ACCIÓN envuelta en un favor, y por eso
# ninguna de las dos reglas la cubría. Y no era falta de capacidad — la escalada salió y el worker fue a
# TheFork; lo que falló fue lo que dijo.
def test_opening_the_page_so_he_does_it_is_also_handing_the_job_back(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "te abro la página y reservas tú" in system
    assert "es devolverle la acción" in system


def test_and_it_says_that_opening_a_page_is_working_not_delegating(fresh_db):
    """Sin esta mitad la regla se lee como «no abras páginas», que es lo contrario de lo que se quiere."""
    system, _ = prompt.build_flash_system()
    assert "una forma de TRABAJAR tú" in system


def test_the_wall_is_still_a_legitimate_stopping_point(fresh_db):
    """Este caso puntúa como MÁXIMO pararse en el muro diciéndolo. La regla no puede prohibir eso — solo exige
    haberlo intentado primero."""
    system, _ = prompt.build_flash_system()
    assert "llega hasta ahí y dilo entonces" in system


def test_the_older_two_forms_are_still_covered(fresh_db):
    """El arreglo es una ampliación de familia, no una sustitución: las dos reglas anteriores siguen."""
    system, _ = prompt.build_flash_system()
    assert "El trabajo es TUYO" in system
    assert "BUSCAR un dato es TU trabajo" in system


# ── V2-357: y los CANDIDATOS tampoco se inventan ────────────────────────────────────────────────────────
#
# La regla de arriba (V2-142) cubre los datos DEL OPERADOR —su ciudad, su farmacia, su gimnasio— y no dice
# nada de los candidatos de un encargo. Medido en `weekend-plan-barcelona__es` (2026-08-27, ronda del
# supervisor): en el TURNO 2, con el worker recién arrancado y cero filas en la hoja, zaelar propuso las vías
# ferratas «de Centelles» y «Teresina» — sin precio, sin horario, sin enlace, sin fuente. El juez lo puso de
# bloqueador nº1: «nombres plausibles sacados del conocimiento del modelo, no de una búsqueda… tiene forma de
# resultado y no lo es».
#
# Es la tercera vez en la misma tanda con la misma forma —V2-344 y V2-348 fueron las otras dos—: la
# instrucción correcta, acotada a la rama equivocada. Y aquí el daño es peor que callar, porque el operador NO
# PUEDE distinguir un nombre inventado de uno encontrado: se fía y se equivoca.

def test_los_candidatos_salen_de_la_busqueda_no_del_modelo():
    system, _ = prompt.build_flash_system()
    assert "CANDIDATOS de lo que te encarga" in system
    assert "JAMÁS de lo que tú sepas" in system


def test_y_dice_que_NO_TENER_es_una_respuesta_completa():
    """Sin esta mitad el bloque solo prohíbe, y el modelo se queda sin salida legítima — que es justo cómo se
    llega a inventar. Misma lección que V2-187."""
    system, _ = prompt.build_flash_system()
    assert "«todavía no tengo candidatos» es una respuesta COMPLETA" in system


def test_la_EXCEPCION_va_dentro_del_imperativo():
    """Explicar qué ES algo en general sigue permitido y ayuda. Va en la misma frase, no en otra: dos órdenes
    en un párrafo salen a cara o cruz (V2-348)."""
    system, _ = prompt.build_flash_system()
    assert "qué ES algo" in system and "sí puedes" in system
    i, j = system.index("CANDIDATOS de lo que te encarga"), system.index("qué ES algo")
    assert 0 < j - i < 700, "la excepción se ha separado del imperativo que la acota"


def test_la_regla_HERMANA_sigue_en_pie():
    """El lado contrario: la de V2-142 no puede desaparecer al añadir la suya."""
    system, _ = prompt.build_flash_system()
    assert "busca lo que ÉL ha dicho" in system
    assert "Un resultado solo es SUYO" in system
