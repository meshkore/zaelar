"""A recall says where each line came from, and the conversation record is one of its sources (V2-802 T-06,
V2-803 T-01/T-02).

The incident: a worker spent minutes «reviewing memory in depth» through `mem_cli recall`, which printed `- text`
and nothing else. It could not tell an inbound Brokerly email from a fact the operator dictated, it reported «it is on
record» on a row with no source behind it, and it never reached the place the truth was — the previous night's
conversation, kept verbatim in the `conv` buffer that no recall path read.

Pinned here:
  · every recalled row carries id, created, level, kind, source and lane, and the digest prints them on its line;
  · ONE reader returns the operator's own past conversation for a window and/or a query, oldest first, with time,
    who said it and the work session (from the event log, which observability owns);
  · a worker reaches it through the same route and CLI (`mem_cli history`), bounded by hours and size;
  · the lanes come back in order — his memory, what was said, what others wrote — and can be filtered.
"""
import time

import pytest

from bus import log as buslog
from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    buslog.close()
    memdb.reset_db()
    memdb.get_db()
    yield
    buslog.close()
    memdb.reset_db()


def _turn(u: str, a: str, ago_s: int) -> int:
    mid = memwriter.insert_memory(f"Operador: {u} · zaelar: {a}", kind="conv", level="short", importance=0.2,
                                  ttl_days=2.0, meta={"source": "conv", "u": u, "a": a})
    memdb.get_db().execute("UPDATE memories SET created=? WHERE id=?", (int(time.time()) - ago_s, mid))
    return mid


def _session_event(session_id: str, ago_s: int) -> None:
    conn = buslog._connect()
    conn.execute("INSERT INTO events (ts_ms, topic, payload, session_id) VALUES (?, 'observer', '{}', ?)",
                 ((time.time() - ago_s) * 1000.0, session_id))
    conn.commit()


def test_the_reader_returns_his_conversation_verbatim_with_time_and_who(fresh_db):
    _turn("pon a mi nombre la reserva, Lucía Ferrer", "Hecho, a nombre de Lucía Ferrer", 10 * 3600)
    _turn("old talk about the boat", "noted", 5 * 86400)                    # outside a 24 h window
    lines = memapi.conversation(hours=24)
    assert [(ln["who"], ln["text"]) for ln in lines] == [
        ("operator", "pon a mi nombre la reserva, Lucía Ferrer"),
        ("assistant", "Hecho, a nombre de Lucía Ferrer")]
    assert lines[0]["at"] and lines[0]["ts"]


@pytest.mark.parametrize("said,asked,other", [
    ("mi teléfono de contacto es el 600 123 456", "teléfono", "reserva una mesa para dos"),
    ("my flight to Lisbon leaves at 7am on Friday", "flight Lisbon", "remind me to water the plants"),
])
def test_a_query_narrows_the_window_and_no_match_is_not_found(fresh_db, said, asked, other):
    _turn(said, "ok", 3 * 3600)
    _turn(other, "ok", 2 * 3600)
    hit = memapi.conversation(hours=24, query=asked)
    assert [ln["text"] for ln in hit if ln["who"] == "operator"] == [said]
    assert memapi.conversation(hours=24, query="zzqx inexistente") == []


def test_the_reader_is_bounded_and_keeps_the_newest(fresh_db):
    for i in range(30):
        _turn(f"turno {i}", "ok", (30 - i) * 60)
    lines = memapi.conversation(hours=24, limit=5)
    ops = [ln["text"] for ln in lines if ln["who"] == "operator"]
    assert ops == [f"turno {i}" for i in range(25, 30)]


def test_a_cleared_conversation_stays_cleared(fresh_db):
    mid = _turn("algo que se borró con el reset", "ok", 600)
    memdb.get_db().execute("UPDATE memories SET valid=0 WHERE id=?", (mid,))
    assert memapi.conversation(hours=24) == []


def test_provenance_names_the_source_of_each_row(fresh_db):
    fact = memwriter.insert_memory("su número es el 600123456", kind="fact", level="long", meta={"source": "voice"})
    msg = memwriter.insert_memory("[email] Brokerly: abre tu cuenta", kind="msg",
                                  meta={"source": "email", "entity": "Brokerly"})
    p = memapi.provenance([fact, msg])
    assert p[fact]["source"] == "voice" and p[fact]["lane"] == "memory" and p[fact]["level"] == "long"
    assert p[msg]["source"] == "email" and p[msg]["entity"] == "Brokerly" and p[msg]["lane"] == "message"
    assert p[fact]["created"][:4].isdigit()


def test_the_recall_route_returns_lanes_in_order_with_provenance(fresh_db):
    from server import memory_routes as routes
    _session_event("sess-abc12345", 3 * 3600 + 5)
    fact = memwriter.insert_memory("Reserva en Casa Lumbre para dos el sábado", kind="result", level="long",
                                   meta={"source": "worker:t1"})
    memwriter.insert_memory("[email] Casa Lumbre: confirma tu reserva", kind="msg",
                            meta={"source": "email", "entity": "Casa Lumbre"})
    _turn("reserva en Casa Lumbre para dos", "Reservado en Casa Lumbre", 3 * 3600)
    res = routes._recall_sync("reserva Casa Lumbre", 8, "all", "", 0)
    lanes = [m["lane"] for m in res["memories"]]
    assert lanes == sorted(lanes, key=["memory", "conversation", "message"].index), lanes
    assert {"memory", "conversation", "message"} <= set(lanes)
    first = res["memories"][0]
    assert first["id"] == fact and first["source"] == "worker:t1" and first["created"]
    conv = [m for m in res["memories"] if m["lane"] == "conversation"]
    assert conv[0]["session"] == "sess-abc12345" and conv[0]["who"] == "operator"
    digest = res["text"].splitlines()
    assert digest[0].startswith(f"- [{first['created']} · memory/result · worker:t1]")
    assert any("conversation · session sess-abc · operator] reserva en Casa Lumbre" in ln for ln in digest)
    assert any("message · email · Casa Lumbre]" in ln for ln in digest)


def test_the_recall_route_filters_by_lane_and_by_source(fresh_db):
    from server import memory_routes as routes
    memwriter.insert_memory("Reserva en Casa Lumbre", kind="result", level="long", meta={"source": "voice"})
    memwriter.insert_memory("[email] Casa Lumbre: confirma", kind="msg", meta={"source": "email", "entity": "Casa Lumbre"})
    memwriter.insert_memory("[whatsapp] Ana: Casa Lumbre mola", kind="msg", meta={"source": "whatsapp", "entity": "Ana"})
    _turn("hablamos de Casa Lumbre", "sí", 600)
    only_msgs = routes._recall_sync("Casa Lumbre", 8, "messages", "", 0)["memories"]
    assert only_msgs and {m["lane"] for m in only_msgs} == {"message"}
    only_wa = routes._recall_sync("Casa Lumbre", 8, "whatsapp", "", 0)["memories"]
    assert [m["entity"] for m in only_wa] == ["Ana"]
    history = routes._recall_sync("", 8, "conversation", "", 24)["memories"]
    assert [m["text"] for m in history] == ["hablamos de Casa Lumbre", "sí"]


def test_mem_cli_history_reaches_the_conversation_lane(monkeypatch, capsys):
    from nucleo.cli import mem as mem_cli
    sent = {}

    def _post(path, payload, timeout=20.0):
        sent.update(path=path, payload=payload)
        return {"text": "- [2026-10-25T23:40+02:00 · conversation · session abcd1234 · operator] la reserva"}
    monkeypatch.setattr(mem_cli, "_post", _post)
    assert mem_cli.main(["history", "--hours", "12", "reserva"]) == 0
    assert sent["path"] == "/api/memory/recall"
    assert sent["payload"]["source"] == "conversation" and sent["payload"]["hours"] == 12.0
    assert "session abcd1234 · operator] la reserva" in capsys.readouterr().out
