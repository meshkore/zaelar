"""nucleo/flash/probe.py::run_turn — what the operator said must remain in the window EVEN IF the turn
fails (V2-167/V2-176, measured twice).

Measured on 2026-08-19 in `restaurant-tonight-madrid` and again on 2026-08-20 in `book-hotel-night-known__es`.
The window was written ONLY at the end of the turn (step (f) of `run_turn`), so any early exit
lost the phrase that had just been said. When the provider call failed, the turn returned `ok: False`
—no response— and the request went with it. Verbatim from the run:

    TESTER  Resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio.
    ZAELAR  (sin respuesta)
    ...
    TESTER  Oye, ¿lo conseguiste?
    ZAELAR  Sobre lo de las entradas para El Rey León en Madrid — ese encargo quedó bloqueado.
    TESTER  No, hablo de la mesa para 2 en Casa Lucio...
    ZAELAR  no tengo constancia de ese encargo en mi estado — no me habías pedido que reservara una mesa

The judge scored it as “context hallucination” and “gaslighting the user.” It was neither: it was
TRUE, and the cause was ours. The only request the engine knew about was the one from the previous case in the same batch
(memory intentionally survives the reset between cases, and the harness seals this in the evidence).

`dialog.push_user` already had this principle written for voice —“what the operator said HAPPENED; canceling the
RESPONSE does not erase the PHRASE”— and the text channel called that SAME function at the one point where it could not
serve any purpose.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import probe
from voice import brain_notes


class _BrokenFastClient:
    """Stub: the provider crashes halfway through the stream — insufficient funds, rate limit, dropped connection."""

    async def stream(self, *_a, **_kw):
        raise RuntimeError("insufficient balance (code 1113)")
        yield  # pragma: no cover — never reached; keeps this an async generator


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


@pytest.fixture
def probe_session():
    sid = "test-what-was-said"
    brain_notes.drain()
    yield sid
    probe._SESSIONS.pop(sid, None)
    brain_notes.drain()


def _window(sid: str) -> list[dict]:
    return probe._SESSIONS[sid].window


def test_a_turn_that_never_reached_the_model_still_remembers_the_request(
        fresh_db, probe_session, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)

    said = "Resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio."
    res = asyncio.run(probe.run_turn(said, sid=probe_session, ingest=False))

    assert res["ok"] is False, "este test mide el camino del fallo; si dejó de fallar, ya no mide nada"
    users = [m["content"] for m in _window(probe_session) if m["role"] == "user"]
    assert said in users, "el turno falló y se llevó la petición con él"


def test_and_it_leaves_no_answer_after_it_so_the_next_turn_can_see_the_gap(
        fresh_db, probe_session, monkeypatch):
    """The form matters as much as the fact: a user line with NO response after it reads as “I did not
answer that one,” which is exactly what happened. An invented marker would say less and could lie."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    asyncio.run(probe.run_turn("Resérvame mesa en Casa Lucio.", sid=probe_session, ingest=False))

    win = _window(probe_session)
    assert win, "la ventana quedó vacía"
    assert win[-1]["role"] == "user"


def test_the_second_request_does_not_erase_the_first_one(fresh_db, probe_session, monkeypatch):
    """Two failed turns in a row: the operator persisted, and both things they said happened."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    asyncio.run(probe.run_turn("Resérvame mesa en Casa Lucio.", sid=probe_session, ingest=False))
    asyncio.run(probe.run_turn("Oye, ¿lo conseguiste?", sid=probe_session, ingest=False))

    users = [m["content"] for m in _window(probe_session) if m["role"] == "user"]
    assert "Resérvame mesa en Casa Lucio." in users
    assert "Oye, ¿lo conseguiste?" in users


def test_a_normal_turn_records_the_line_exactly_once(fresh_db, probe_session, monkeypatch):
    """The other half: recording it early AND at the end must not duplicate the phrase. A small model seeing the
same phrase twice is exactly what V2-032 measured as degrading it."""

    class _Talks:
        async def stream(self, *_a, **_kw):
            yield "Voy con ello."

    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _Talks)
    said = "Resérvame mesa en Casa Lucio."
    asyncio.run(probe.run_turn(said, sid=probe_session, ingest=False))

    users = [m["content"] for m in _window(probe_session) if m["role"] == "user"]
    assert users.count(said) == 1, f"la frase entró {users.count(said)} veces"


def test_the_window_stays_bounded_across_failed_turns(fresh_db, probe_session, monkeypatch):
    """Trimming also lived in step (f), so recording early without trimming would leave the window
growing without bound precisely along the path that repeats most: the provider being down."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    for i in range(probe._WINDOW_MAX + 6):
        asyncio.run(probe.run_turn(f"petición número {i}", sid=probe_session, ingest=False))

    assert len(_window(probe_session)) <= probe._WINDOW_MAX


def test_a_turn_that_was_ONLY_a_secret_never_puts_the_secret_in_the_window(
        fresh_db, probe_session, monkeypatch):
    """The vault has its own early exit, and the previous rule is NOT relaxed there: the phrase is recorded
    REDACTED. A secret never reaches the model, and that exit exists precisely because the entire turn was
    one."""
    value = "Tr3sM4rias!2024"
    said = f"mi contraseña de Netflix es {value}"
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    res = asyncio.run(probe.run_turn(said, sid=probe_session, ingest=False))

    assert (res.get("secret") or {}).get("n"), "este turno ya no toma la salida de la bóveda; el test no mide"
    blob = " ".join(m["content"] for m in _window(probe_session))
    assert value not in blob, "un secreto llegó a la ventana conversacional"
    assert "Netflix" in blob, "se redactó de más: la ventana perdió DE QUÉ hablaba el operador"


# ── and the provider failure has to be SAID ─────────────────────────────────────────────────────────────
# The other half of the same asymmetry between channels: when faced with a broken provider, voice degrades with an
# honest phrase, marks the cooldown, and records health. The text channel swallowed it whole — no cooldown, no
# health, not a word. That is why the measured transcript has THREE consecutive turns without a response: a headline with no
# balance remained the headline because nobody said so. The cooldown is SHARED deliberately, so reporting
# here is what allows the OTHER channel to take over.

def test_a_provider_failure_in_the_text_channel_marks_the_cooldown(fresh_db, probe_session, monkeypatch):
    seen: list[tuple] = []
    from nucleo.flash import provider_chain as pc
    monkeypatch.setattr(pc, "note_failure", lambda text, *a, **kw: seen.append((text, kw.get("role"))))
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)

    asyncio.run(probe.run_turn("Resérvame mesa en Casa Lucio.", sid=probe_session, ingest=False))

    assert seen, "el canal de texto se tragó el fallo del proveedor"
    assert "1113" in seen[0][0], "se reportó, pero sin el error que clasifica el motivo"
    assert seen[0][1] == pc.ROLE_VOICE, "la cadena del FlashBrain es la que sirve también al texto"


def test_and_it_records_the_health_so_the_operator_can_SEE_it(fresh_db, probe_session, monkeypatch):
    """“Visible status, not silent”: a mute turn with nothing on the indicator is indistinguishable from a hang."""
    seen: list[tuple] = []
    from voice import health_state
    monkeypatch.setattr(health_state, "record", lambda *a, **kw: seen.append(a))
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)

    asyncio.run(probe.run_turn("Resérvame mesa en Casa Lucio.", sid=probe_session, ingest=False))

    assert seen and seen[0][0] == "llm"


def test_the_failure_still_comes_back_as_a_failure(fresh_db, probe_session, monkeypatch):
    """Reporting cannot change the contract: the caller still receives `ok: False` with its error and spec.
    The harness and frontend read exactly that."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    res = asyncio.run(probe.run_turn("hola", sid=probe_session, ingest=False))

    assert res["ok"] is False
    assert "1113" in res["error"]
    assert res.get("spec")
