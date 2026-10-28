"""A REQUEST of the operator is never stored as a RESULT (refactor2710-11 T-01, V2-825 F1).

Measured 2026-10-27: the distiller stored «Pidió al asistente que capture su estilo… hasta dar el estilo por
capturado» as `memory/result`, and the next turn answered «¿has terminado?» with «Sí, está terminado» from that
pill — for an errand whose task row said `failed`. Only the circuit that judged an errand's end state knows it
was done; the operator's words never do.

The guard is the pill GRAMMAR at birth (`nucleo/memory_agent/writer.py`): whatever kind the model returns, a
distilled pill is never a `result`; a `result` is written only through `writer.result(...)` on a `met` verdict.
Checked through the REAL write path — the HTTP call is the only thing replaced — with requests in three languages
and three domains, so no wording carries the test.
"""
import asyncio
import json

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import queue as memqueue
from nucleo import memory_agent
from nucleo.memory_agent import writer
from nucleo.memory_agent.processor import distill, distill_config

_REQUESTS = [
    ("Captúrame mi estilo y no pares hasta darlo por capturado.",
     "Pidió al asistente que capture su estilo hasta darlo por capturado (27 de octubre de 2026)."),
    ("Book me a table for two at a quiet place on Saturday.",
     "Asked the assistant to book a table for two on Saturday 31 October 2026."),
    ("Busca'm un fuster que pugui venir dijous.",
     "Va demanar a l'assistent que li busqui un fuster per dijous 29 d'octubre de 2026."),
]


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _model_says(monkeypatch, pill_text: str, kind: str) -> None:
    """The provider answers with ONE pill of `kind` — the rest of the path (parse, gates, writer) is the real one."""
    reply = json.dumps([{"text": pill_text, "dest": "long", "kind": kind, "importance": 0.6, "ttl_days": None,
                         "slot": None, "change": "none", "concepts": [], "state_patch": {}}])

    async def _post(rung_url, payload, timeout_s):
        return {"choices": [{"message": {"content": reply}, "finish_reason": "stop"}], "usage": {}}
    monkeypatch.setattr(distill, "_post", _post)
    monkeypatch.setattr(distill_config, "enabled", lambda: True)
    monkeypatch.setattr(distill_config, "rung_chain", lambda: [("https://api.example.test/v1", "m")])


def _ingest(utterance: str) -> None:
    async def scenario():
        await memapi.start()
        await memory_agent.ingest_utterance(utterance, role="operator")
        await memqueue.get_queue().join()
        await memapi.stop()
    asyncio.run(scenario())


def _kinds() -> dict[str, str]:
    return {r["text"]: r["kind"] for r in memdb.get_db().query("SELECT text, kind FROM memories WHERE valid=1")}


@pytest.mark.parametrize("utterance, pill", _REQUESTS, ids=["es-style", "en-booking", "ca-trade"])
def test_a_request_the_model_labels_a_result_is_stored_as_a_request(fresh_db, monkeypatch, utterance, pill):
    _model_says(monkeypatch, pill, "result")
    _ingest(utterance)
    kinds = _kinds()
    assert pill in kinds, f"the request itself must still be kept (it is an errand he gave): {kinds}"
    assert kinds[pill] == "request", f"a request was stored as {kinds[pill]!r} — the next turn reads it as done"
    assert "result" not in kinds.values()


def test_the_distiller_is_never_told_to_write_a_result():
    from nucleo.memory_agent.processor import distill_prompt
    assert 'kind="result"' not in distill_prompt._SYSTEM and "kind=result" not in distill_prompt._SYSTEM


def test_a_result_is_written_only_on_a_met_verdict(fresh_db):
    async def scenario():
        await memapi.start()
        refused = [await writer.result("Encontró tres carpinteros en Soria.", task_id="t1", verdict=v)
                   for v in ("failed", "partial", "", "interrumpido")]
        written = await writer.result("Encontró tres carpinteros en Soria.", task_id="t2", verdict="met")
        await memqueue.get_queue().join()
        await memapi.stop()
        return refused, written
    refused, written = asyncio.run(scenario())
    assert refused == [False] * 4 and written is True
    rows = memdb.get_db().query("SELECT kind, meta FROM memories WHERE valid=1 AND kind='result'")
    assert len(rows) == 1 and json.loads(rows[0]["meta"])["verdict"] == "met"


def test_a_stored_request_is_shown_as_an_errand_not_as_something_known_about_him(fresh_db):
    from memory import writer as memwriter
    memwriter.insert_memory("Vive en Soria.", kind="fact", level="long", weight=0.9, importance=0.9)
    memwriter.insert_memory(_REQUESTS[0][1], kind="request", level="long", weight=0.9, importance=0.9)
    block, _op, stats = memapi.compose_state()
    known = block.split("[Lo que sabes de él")[1].split("[Encargos")[0]
    assert "capture su estilo" not in known and stats["errand_count"] == 1


def test_an_old_distilled_result_is_relabelled_a_request_and_a_circuit_result_is_kept(fresh_db):
    """The defect's pill is ON DISK in installs that ran before the grammar: migration v10 relabels the rows the
    distiller wrote (`meta.path='llm'`) and leaves the ones a worker wrote. Provenance decides, never wording."""
    from memory import writer as memwriter
    asked = memwriter.insert_memory(_REQUESTS[0][1], kind="result", level="long", meta={"source": "typed", "path": "llm"})
    done = memwriter.insert_memory("[tarea web] carpinteros → tres en Soria", kind="result", level="mid",
                                   meta={"source": "worker:t9"})
    db = memdb.get_db()
    db.execute("PRAGMA user_version=9")
    memdb.reset_db()
    kinds = {r["id"]: r["kind"] for r in memdb.get_db().query("SELECT id, kind FROM memories")}
    assert kinds[asked] == "request" and kinds[done] == "result"
