"""nucleo/flash/probe.py::run_turn — lo que el operador dijo tiene que quedar en la ventana AUNQUE el turno
falle (V2-167/V2-176, medido dos veces).

Medido el 2026-08-19 en `restaurant-tonight-madrid` y otra vez el 2026-08-20 en `book-hotel-night-known__es`.
La ventana se escribía SOLO al final del turno (paso (f) de `run_turn`), así que cualquier salida temprana
perdía la frase que acababa de decirse. Cuando la llamada al proveedor fallaba, el turno devolvía `ok: False`
—ninguna respuesta— y la petición se iba con él. Verbatim de la corrida:

    TESTER  Resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio.
    ZAELAR  (sin respuesta)
    ...
    TESTER  Oye, ¿lo conseguiste?
    ZAELAR  Sobre lo de las entradas para El Rey León en Madrid — ese encargo quedó bloqueado.
    TESTER  No, hablo de la mesa para 2 en Casa Lucio...
    ZAELAR  no tengo constancia de ese encargo en mi estado — no me habías pedido que reservara una mesa

El juez lo puntuó como «alucinación de contexto» y «gaslighting al usuario». No era ninguna de las dos: era
VERDAD, y la causa era nuestra. El único encargo que el motor conocía era el del caso anterior del mismo lote
(la memoria sobrevive al reset entre casos a propósito, y el arnés lo sella en la evidencia).

`dialog.push_user` ya llevaba escrito este principio para la voz —«lo que el operador dijo OCURRIÓ; cancelar la
RESPUESTA no borra la FRASE»— y el canal de texto llamaba a esa MISMA función en el único punto donde no podía
servir de nada.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import probe
from voice import brain_notes


class _BrokenFastClient:
    """Stub: el proveedor revienta a mitad del stream — sin fondos, rate limit, conexión cortada."""

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
    """La forma importa tanto como el hecho: una línea de usuario SIN respuesta detrás se lee como «a esa no
    contesté», que es exactamente lo que pasó. Un marcador inventado diría menos y podría mentir."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    asyncio.run(probe.run_turn("Resérvame mesa en Casa Lucio.", sid=probe_session, ingest=False))

    win = _window(probe_session)
    assert win, "la ventana quedó vacía"
    assert win[-1]["role"] == "user"


def test_the_second_request_does_not_erase_the_first_one(fresh_db, probe_session, monkeypatch):
    """Dos turnos fallidos seguidos: el operador insistió, y las dos cosas que dijo ocurrieron."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    asyncio.run(probe.run_turn("Resérvame mesa en Casa Lucio.", sid=probe_session, ingest=False))
    asyncio.run(probe.run_turn("Oye, ¿lo conseguiste?", sid=probe_session, ingest=False))

    users = [m["content"] for m in _window(probe_session) if m["role"] == "user"]
    assert "Resérvame mesa en Casa Lucio." in users
    assert "Oye, ¿lo conseguiste?" in users


def test_a_normal_turn_records_the_line_exactly_once(fresh_db, probe_session, monkeypatch):
    """La otra mitad: registrarlo pronto Y al final no puede duplicar la frase. Un modelo pequeño viendo la
    misma frase dos veces es justo lo que V2-032 midió que lo degrada."""

    class _Talks:
        async def stream(self, *_a, **_kw):
            yield "Voy con ello."

    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _Talks)
    said = "Resérvame mesa en Casa Lucio."
    asyncio.run(probe.run_turn(said, sid=probe_session, ingest=False))

    users = [m["content"] for m in _window(probe_session) if m["role"] == "user"]
    assert users.count(said) == 1, f"la frase entró {users.count(said)} veces"


def test_the_window_stays_bounded_across_failed_turns(fresh_db, probe_session, monkeypatch):
    """El recorte también vivía en el paso (f), así que registrar pronto sin recortar dejaría la ventana
    creciendo sin techo justo en el camino que más se repite: el proveedor caído."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    for i in range(probe._WINDOW_MAX + 6):
        asyncio.run(probe.run_turn(f"petición número {i}", sid=probe_session, ingest=False))

    assert len(_window(probe_session)) <= probe._WINDOW_MAX


def test_a_turn_that_was_ONLY_a_secret_never_puts_the_secret_in_the_window(
        fresh_db, probe_session, monkeypatch):
    """La bóveda tiene su propia salida temprana, y ahí la regla anterior NO se relaja: la frase se registra
    REDACTADA. Un secreto jamás llega al modelo, y esa salida existe precisamente porque el turno entero era
    uno."""
    value = "Tr3sM4rias!2024"
    said = f"mi contraseña de Netflix es {value}"
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    res = asyncio.run(probe.run_turn(said, sid=probe_session, ingest=False))

    assert (res.get("secret") or {}).get("n"), "este turno ya no toma la salida de la bóveda; el test no mide"
    blob = " ".join(m["content"] for m in _window(probe_session))
    assert value not in blob, "un secreto llegó a la ventana conversacional"
    assert "Netflix" in blob, "se redactó de más: la ventana perdió DE QUÉ hablaba el operador"


# ── y el fallo del proveedor tiene que DECIRSE ─────────────────────────────────────────────────────────────
# La otra mitad de la misma asimetría entre canales: la voz, ante un proveedor roto, degrada con una frase
# honesta, marca el cooldown y registra la salud. El canal de texto se lo tragaba entero — ni cooldown, ni
# salud, ni una palabra. Por eso el transcript medido trae TRES turnos seguidos sin respuesta: un titular sin
# saldo seguía siendo el titular porque nadie lo dijo. El cooldown es COMPARTIDO a propósito, así que reportar
# aquí es lo que permite al OTRO canal relevarse.

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
    """«Estado visible, no silencioso»: un turno mudo sin nada en el semáforo es indistinguible de un cuelgue."""
    seen: list[tuple] = []
    from voice import health_state
    monkeypatch.setattr(health_state, "record", lambda *a, **kw: seen.append(a))
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)

    asyncio.run(probe.run_turn("Resérvame mesa en Casa Lucio.", sid=probe_session, ingest=False))

    assert seen and seen[0][0] == "llm"


def test_the_failure_still_comes_back_as_a_failure(fresh_db, probe_session, monkeypatch):
    """Reportar no puede cambiar el contrato: quien llama sigue recibiendo `ok: False` con su error y su spec.
    El arnés y el frontend leen justo eso."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _BrokenFastClient)
    res = asyncio.run(probe.run_turn("hola", sid=probe_session, ingest=False))

    assert res["ok"] is False
    assert "1113" in res["error"]
    assert res.get("spec")
