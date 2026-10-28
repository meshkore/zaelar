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


def test_the_guard_is_what_keeps_it_out_disarm(fresh_db, monkeypatch):
    """DISARM: with the grammar's demotion switched off, the same model reply lands as a `result` — so the test
    above is held by `writer.distilled_kind`, not by the fixture."""
    monkeypatch.setattr(writer, "distilled_kind", lambda raw: str(raw or "fact"))
    _model_says(monkeypatch, _REQUESTS[0][1], "result")
    _ingest(_REQUESTS[0][0])
    assert _kinds().get(_REQUESTS[0][1]) == "result"


def test_the_distiller_is_never_told_to_write_a_result():
    from nucleo.memory_agent.processor import distill_prompt
    assert 'kind="result"' not in distill_prompt._SYSTEM and "kind=result" not in distill_prompt._SYSTEM


def test_a_result_is_written_only_when_the_worker_delivered(fresh_db):
    """Delivered = `met`, or an errand whose end state was undeclared / unreadable (a trip plan, a report): its
    deliverable is kept, stamped with that verdict. Failed, cancelled or parked errands write nothing."""
    async def scenario():
        await memapi.start()
        refused = [await writer.result("Encontró tres carpinteros en Soria.", task_id="t1", verdict=v)
                   for v in ("unmet", "gave_up", "skipped", "retrying", "cannot", "asked", "")]
        written = [await writer.result(f"Plan de viaje a Lisboa ({v}).", task_id=f"t-{v}", verdict=v)
                   for v in ("met", "undeclared", "unverifiable")]
        await memqueue.get_queue().join()
        await memapi.stop()
        return refused, written
    refused, written = asyncio.run(scenario())
    assert refused == [False] * 7 and written == [True] * 3
    rows = memdb.get_db().query("SELECT kind, meta FROM memories WHERE valid=1 AND kind='result'")
    assert sorted(json.loads(r["meta"])["verdict"] for r in rows) == ["met", "undeclared", "unverifiable"]


def test_a_stored_request_is_shown_as_an_errand_not_as_something_known_about_him(fresh_db):
    from memory import writer as memwriter
    memwriter.insert_memory("Vive en Soria.", kind="fact", level="long", weight=0.9, importance=0.9)
    memwriter.insert_memory(_REQUESTS[0][1], kind="request", level="long", weight=0.9, importance=0.9)
    block, _op, stats = memapi.compose_state()
    known = block.split("[Lo que sabes de él")[1].split("[Encargos")[0]
    assert "capture su estilo" not in known and stats["errand_count"] == 1
    errands = block.split("[Encargos")[1]
    line = next(ln for ln in errands.splitlines() if "capture su estilo" in ln)
    assert line.startswith("· pidió: ") and line.endswith("[sin resultado registrado]"), line


def test_an_unverified_delivery_is_shown_as_delivered_not_as_done(fresh_db):
    from memory import writer as memwriter
    memwriter.insert_memory("[tarea web] plan de viaje a Lisboa → tres días", kind="result", level="long",
                            weight=0.9, importance=0.9, meta={"source": "worker:t1", "verdict": "undeclared"})
    memwriter.insert_memory("[tarea web] carpinteros → tres en Soria", kind="result", level="long",
                            weight=0.9, importance=0.9, meta={"source": "worker:t2", "verdict": "met"})
    block, _op, _stats = memapi.compose_state()
    lines = block.split("[Encargos")[1].splitlines()
    assert any(ln.startswith("· entregado, sin verificar: [tarea web] plan de viaje") for ln in lines), lines
    assert any(ln.startswith("· [tarea web] carpinteros") for ln in lines), lines


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


@pytest.mark.parametrize("verdict, kept", [("met", True), ("undeclared", True), ("unverifiable", True),
                                           ("unmet", False), ("gave_up", False)])
def test_a_finished_worker_writes_its_result_only_through_the_door(fresh_db, monkeypatch, verdict, kept):
    """`workers/session.py` delivers a successful errand: its pill goes through `writer.result`, so a worker that
    SAID it was done while the circuit judged it unmet leaves no `result` behind."""
    from types import SimpleNamespace
    from nucleo.workers import session
    monkeypatch.setattr(session, "operator_safe_summary", lambda s: s)
    rec = SimpleNamespace(task_id=f"w-{verdict}", kind="web", goal="carpinteros en Soria", ok=True,
                          verdict=verdict, result_summary="tres carpinteros en Soria")

    async def scenario():
        await memapi.start()
        await session._deliver(rec)
        await memqueue.get_queue().join()
        await memapi.stop()
    asyncio.run(scenario())
    assert ("result" in _kinds().values()) is kept, _kinds()
