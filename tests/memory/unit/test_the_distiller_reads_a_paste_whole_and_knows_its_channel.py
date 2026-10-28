"""V2-802 T-01/T-04/T-05 · What the distiller is SHOWN decides what it can store.

Measured: the operator pasted an email draft whose signature (full name, project, contact address) sat at the end,
and memory stored the errand but not one identity value. The distiller saw the first 600 characters of the turn —
it was never shown the signature — and its input called every line «Turno del operador», a spoken turn, so nothing
told it a document was in front of it. Every row was stamped `source: voice`, typed or not. And the assistant's
own name never reached it, so «Vale, Johnny, …» produced «the email to Johnny of <company>».

Asserted here on the INPUT the model receives and the ROW the writer stores — deterministic. Whether the real
model then extracts the signature is the live use case of V2-802, not this file.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import queue as memqueue
from nucleo.memory_agent.processor import distill, distill_config, distill_prompt
from nucleo import memory_agent

_SIGNATURE = "Ana Ruiz · Cerámica Norte · contacto@ceramica.example"
_DOC_EN = ("Hi team, following up on our call. " * 90) + "\nBest regards,\n" + _SIGNATURE
_DOC_ES = ("Hola, os escribo para concretar la reserva del jueves. " * 60) + "\nUn saludo,\n" + _SIGNATURE


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEMORY_RERANK", "off")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()
    mememb.reset()


def _render(text: str, channel: str, state: dict | None = None) -> str:
    tok = distill_prompt.CHANNEL.set(channel)
    try:
        return distill_prompt.render(text, state or {})
    finally:
        distill_prompt.CHANNEL.reset(tok)


@pytest.mark.parametrize("doc", [_DOC_EN, _DOC_ES], ids=["en", "es"])
def test_the_end_of_a_long_paste_reaches_the_distiller(doc):
    assert len(doc) > 2500, "the case must be longer than what the distiller is shown"
    shown = _render(doc, "typed")
    assert _SIGNATURE in shown, "the signature at the END of a pasted document never reached the distiller"
    assert len(shown) < len(doc) + 2500, "the input is bounded — a paste must not ship whole without limit"


def test_the_input_declares_its_channel():
    spoken, written = _render("me llamo Ana", "voice"), _render("me llamo Ana", "typed")
    assert spoken != written, "a typed line and a spoken one reach the distiller indistinguishable"
    assert "PEGADO" in written and "documento" in written, written[-300:]
    assert "STT" in spoken, spoken[-200:]


def test_the_distiller_knows_the_assistants_own_name():
    shown = _render("Vale, Johnny, envíale el borrador a Acme Reservas.", "voice", {"assistant_name": "Johnny"})
    assert "TU NOMBRE (el asistente): Johnny" in shown, "a vocative to the assistant reads as a third party"


def test_a_claim_about_our_past_exchanges_is_not_stored_as_a_fact():
    """T-04: «I gave you my name yesterday» was stored as «On Oct 25 he gave the assistant his name» — a claim made
    true by being written down. The prompt rule is the only place this lives (the judgement is the model's)."""
    assert "LO QUE DICE DE VUESTRAS CONVERSACIONES NO es un hecho" in distill_prompt._SYSTEM


def _ingest(text: str, channel: str | None) -> list[str]:
    seen: list[str] = []

    async def _process(_t, state=None):
        seen.append(distill_prompt.CHANNEL.get())
        return [{"text": "Le encanta el pádel.", "dest": "long", "kind": "pref", "importance": 0.7,
                 "ttl_days": None, "slot": None, "change": "none", "concepts": [], "state_patch": {}}]

    async def scenario():
        await memapi.start()
        kw = {} if channel is None else {"channel": channel}
        await memory_agent.ingest_utterance(text, role="operator", **kw)
        await memqueue.get_queue().join()
        await memapi.stop()

    mp_process, mp_enabled = distill.process, distill_config.enabled
    distill.process, distill_config.enabled = _process, (lambda: True)
    try:
        asyncio.run(scenario())
    finally:
        distill.process, distill_config.enabled = mp_process, mp_enabled
    return seen


@pytest.mark.parametrize("channel, expected", [("typed", "typed"), ("voice", "voice"), (None, "voice")])
def test_the_row_records_the_channel_it_came_by(channel, expected):
    seen = _ingest("Me encanta el pádel, juego los martes.", channel)
    assert seen == [expected], f"the distiller was told {seen}, the turn came by {expected}"
    rows = memdb.get_db().query("SELECT json_extract(meta,'$.source') AS s FROM memories "
                                "WHERE valid=1 AND kind != 'concept' AND text LIKE '%pádel%'")
    assert [r["s"] for r in rows] == [expected], [dict(r) for r in rows]
    assert distill_prompt.CHANNEL.get() == "voice", "the channel leaked past the turn that set it"


def test_the_typed_mark_is_exact_per_line():
    """The voice provider asks `attention.typed_line(text)`: the line he typed is «typed», a line SPOKEN right after
    it is not — `was_typed()`'s 45 s window would have stamped both."""
    from voice import attention
    saved = {k: attention._state.get(k) for k in ("typed_at", "typed_pending", "typed_text")}
    try:
        attention.note_typed(now=1000.0, text="Un saludo, Ana Ruiz")
        assert attention.typed_line("Un saludo, Ana Ruiz", now=1001.0)
        assert not attention.typed_line("pon algo de música", now=1002.0)
        assert not attention.typed_line("Un saludo, Ana Ruiz", now=1100.0)
    finally:
        attention._state.update(saved)
