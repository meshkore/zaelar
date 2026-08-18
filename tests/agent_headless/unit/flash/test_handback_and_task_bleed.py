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
