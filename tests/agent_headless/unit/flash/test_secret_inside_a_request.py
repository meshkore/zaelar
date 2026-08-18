"""V2-141 (`pay-known-bill__es`, round 2) — a secret spoken INSIDE a request must not swallow the request.

The transcript ends with the operator handing over exactly what zaelar had asked him for — invoice number,
amount and IBAN — and receiving `(sin respuesta)`. Nothing after his bank details. The cause is not the model:
both channels intercept a detected secret DETERMINISTA before the model sees it (V2-060, and that invariant
stands: a secret value never reaches an LLM), but the intercept then consumed the WHOLE turn.

That is right when the turn IS the secret and wrong when the secret rides inside a request — which is the only
way an IBAN normally gets spoken at all. And for money it is worse than losing the request: the confirm-gate
lives further down the turn, so a payment order carrying its own IBAN could never reach the gate that exists to
stop it.

Second measured cause in the same run: `danger.is_dangerous("¿Puedes pagarla antes del día 5?")` was False. The
polite way to give an order in Spanish is a question with a modal, and there the verb is an infinitive with the
pronoun glued on — the same blind spot that already cost «resérvame» and «págala», one verb mood further along.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import secrets
from nucleo import danger
from nucleo.flash import probe
from nucleo.flash import vault_carrier as vc


IBAN_TURN = ("Vale, aquí van: número de factura es 000123456789, el importe es 57,32€, "
             "y el IBAN para la transferencia es ES12 1234 5678 9012 3456 7890.")
SECRET_ONLY_TURN = "el IBAN es ES12 1234 5678 9012 3456 7890"


class _Client:
    async def stream(self, *_a, **_kw):
        yield "Antes de mover un euro necesito que me lo confirmes."


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


# ── the shape predicate ─────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "mi contraseña de Netflix es Hunter2!x",
    SECRET_ONLY_TURN,
    "apunta mi tarjeta 4539 1488 0343 6467",
])
def test_a_turn_that_is_only_a_secret_is_recognised_as_such(text):
    assert vc.secret_is_the_whole_turn(text, secrets.detect(text)) is True


@pytest.mark.parametrize("text", [
    IBAN_TURN,
    "te paso el IBAN ES12 1234 5678 9012 3456 7890 y haz la transferencia de 57,32 euros antes del día 5",
])
def test_a_secret_riding_inside_a_request_is_not(text):
    assert vc.secret_is_the_whole_turn(text, secrets.detect(text)) is False


def test_no_secret_at_all_is_never_the_whole_turn():
    assert vc.secret_is_the_whole_turn("hola, qué tal", []) is False


# ── the probe channel, which is the one the use cases run on ────────────────────────────────────────────────
def test_the_request_survives_and_the_secret_does_not(fresh_db, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _Client)
    res = asyncio.run(probe.run_turn(IBAN_TURN, sid="t-v141-a", ingest=False))
    probe._SESSIONS.pop("t-v141-a", None)
    assert res["ok"] is True
    assert res["action"] != "vault_need_create"          # the turn was NOT consumed…
    assert res["reply"]                                  # …and the operator got an answer
    assert "ES12 1234 5678 9012 3456 7890" not in " ".join(
        m.get("content", "") for m in probe._session("t-v141-a").window)   # the value never survives


def test_a_turn_that_is_only_a_secret_still_short_circuits(fresh_db, monkeypatch):
    """The interception is right for its own case — and it answers with a SENTENCE now, not «(secreto
    cifrado)», which is a stage direction the harness reads as an empty turn and nobody can say out loud."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _Client)
    res = asyncio.run(probe.run_turn(SECRET_ONLY_TURN, sid="t-v141-b", ingest=False))
    probe._SESSIONS.pop("t-v141-b", None)
    assert res["action"] in ("vault_save", "vault_need_create")
    reply = " ".join(res["reply"]) if isinstance(res["reply"], list) else str(res["reply"])
    assert reply.strip()
    assert not reply.strip().startswith("(")


# ── the gate that could never fire ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "¿Puedes pagarla antes del día 5?",       # the exact turn from the transcript
    "¿podrías comprarlo?",
    "¿me lo compras?",
    "¿me la cancelas?",
    "¿puedes cancelarla?",
    "¿puedes enviarle el mensaje?",
    "can you pay it before the 5th?",
])
def test_a_polite_question_is_still_an_irreversible_order(text):
    assert danger.is_dangerous(text) is True


@pytest.mark.parametrize("text", [
    "¿puedes buscarme un hotel?",
    "¿puedes decirme la hora?",
    "¿me pones música?",
    "¿puedes mirar el precio?",
    "no quiero comprarlo",          # MENTIONS the action, does not order it
    "pagarlo sale caro",
    "recuérdame pagarla el día 5",  # a note, not an order — the reminder clipping still holds
])
def test_and_a_plain_question_is_still_a_plain_question(text):
    assert danger.is_dangerous(text) is False


@pytest.mark.parametrize("text,money", [
    ("¿Puedes pagarla antes del día 5?", True),
    ("¿podrías comprarlo?", True),
    ("¿me la cancelas?", False),          # irreversible, but it costs nothing
    ("¿puedes enviarle el mensaje?", False),
])
def test_money_stays_a_strict_subset(text, money):
    assert danger.moves_money(text) is money
    if money:
        assert danger.is_dangerous(text) is True
