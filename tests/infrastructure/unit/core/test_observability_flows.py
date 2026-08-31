"""
CORRELATION ID + identity + session (2026-08-09).

What is tested is the contract that makes observability ANALYZABLE: an operator stimulus and everything it
triggers share the same flow identifier, each event states which installation and work session it came from,
and that this is QUERYABLE through indexed columns instead of scanning JSON.

The reference case is the one provided by the operator: «show me the weather in Soria» → FlashBrain decision →
web search → widget opening. Four events, four pieces, ONE flow.
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """A clean DB per test + the bus sink connected. `ZAELAR_DB` is the same isolation knob that the in-memory
    tests already use: the operator's real database is never written to."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    import bus
    from bus import log as _log

    _log._conn = None
    _log.detach(bus)
    _log.attach(bus)

    from observability import identity as _ident
    _ident._user["id"] = None
    _ident._session["id"] = None
    yield _log
    _log.detach(bus)
    _log._conn = None


def _settle():
    time.sleep(0.25)      # the bus sink writes on the publishing thread; allow time for cross-loop delivery


def test_a_whole_flow_shares_one_correlation_id(wired):
    from observability import flows, identity
    from voice import trace
    from voice.observer import emit

    identity.begin_session("test")
    tid = trace.begin("enséñame el tiempo en Soria")
    emit("brain", "decide", extra={"brain_ms": 420, "model": "deepseek-v4-flash",
                                   "prompt_tokens": 4700, "completion_tokens": 120})
    emit("search", "web_search «tiempo Soria»")
    emit("widget", "show", extra={"id": "meteo-soria", "src": "flash"})
    _settle()

    got = flows.flows(limit=5)
    assert got, "no se registró ningún flujo"
    f = got[0]
    assert f["corr_id"] == tid
    assert f["events"] == 4, "el evento raíz + los tres derivados deben caer en el MISMO flujo"
    assert set((f["families"] or "").split(",")) == {"flash", "widget"}
    assert f["tokens_in"] == 4700 and f["tokens_out"] == 120
    assert f["errors"] == 0

    detail = flows.flow(tid)
    assert [e["kind"] for e in detail] == ["trace", "brain", "search", "widget"], "orden cronológico del flujo"
    assert detail[1]["ms"] == 420.0, "la duración real sube del payload a su columna"


def test_a_new_request_is_a_new_flow(wired):
    """A new operator request—even if it MODIFIES the previous result—opens its own flow: this makes it possible
    to compare «the first search» with «the correction» instead of seeing them as one mass."""
    from observability import flows
    from voice import trace
    from voice.observer import emit

    t1 = trace.begin("busca vuelos a Roma")
    emit("brain", "busca")
    t2 = trace.begin("no, mejor a Lisboa")
    emit("brain", "busca")
    _settle()

    assert t1 != t2
    ids = {f["corr_id"] for f in flows.flows(limit=5)}
    assert {t1, t2} <= ids


def test_every_event_carries_installation_and_session(wired):
    from observability import flows, identity
    from voice.observer import emit

    identity.begin_session("test")
    emit("brain", "hola")
    _settle()

    s = flows.stats()
    assert s["events"] >= 1
    assert s["with_user"] == s["events"], "un evento sin instalación no se puede atribuir nunca después"
    assert s["with_session"] == s["events"], "ni sin sesión de trabajo"


def test_local_user_id_is_a_random_uuid_and_persists(wired, tmp_path):
    """Random, non-sequential UUID4: it does not identify anyone by itself and cannot collide with that of another
    installation."""
    import uuid

    from observability import identity

    uid = identity.user_id()
    uuid.UUID(uid)                                   # raises if it is not a valid UUID
    assert uuid.UUID(uid).version == 4
    identity._user["id"] = None                      # simulates a process restart
    assert identity.user_id() == uid, "la identidad de la instalación debe sobrevivir al reinicio"


def test_an_environment_provided_user_id_wins(wired, monkeypatch):
    from observability import identity

    monkeypatch.setenv("ZAELAR_USER_ID", "acct_42")
    identity._user["id"] = None
    assert identity.user_id() == "acct_42"


def test_reconnecting_does_not_split_the_work_session(wired):
    """A repeated `start` (reconnection, light reset) REUSES the session: splitting it in two would invalidate any
    measurement of «how long the session lasted and what it did»."""
    from observability import identity

    a = identity.begin_session("voice")["id"]
    b = identity.begin_session("voice")["id"]
    assert a == b

    identity.end_session("power_off")
    c = identity.begin_session("voice")["id"]
    assert c != a, "tras cerrarla de verdad, arrancar el agente abre una sesión NUEVA"


def test_hand_published_events_are_stamped_too(wired):
    """`observer.emit` is NOT the only gateway: the loop heartbeat and the `memory.updated` bridge build their
    dict manually and publish it directly to the topic. They were skipping the stamp—50 of 66 rows from the first
    real startup had no session—and an event without a session can no longer be attributed afterward. The stamp
    lives in `bus/sse.py::publish`, which is the single gateway."""
    from bus import sse as _sse
    from observability import identity

    identity.begin_session("test")
    ev = {"kind": "memory", "label": "updated"}     # dict built manually, like the memory.updated bridge
    _sse.publish(ev)
    # Check the PUBLISHED event, not the row: the stamp occurs on publication, so the test does not depend on
    # whether that specific kind is persisted (the heartbeat, for example, is deliberately discarded).
    assert ev["sid"] == identity.session_id()
    assert ev["uid"] == identity.user_id()
    assert ev["cat"] == "memory", "la familia también se deriva: sin ella la fila cae en «Sin clasificar»"


# ── THE EVIDENCE: what the outside world brought (2026-08-10) ─────────────────────────────────────────────────
# Until now, the QUESTION and DECISION were recorded, not the PROOF: a search was reduced to «7 results» and
# what the model actually read was lost. This makes it possible to audit that the system SEARCHED, but never
# whether it searched WELL—the question that matters («do the results support what it answered?») was
# unverifiable afterward.
def test_the_evidence_of_a_search_is_kept_with_its_sources():
    from observability import evidence

    ev = evidence.web_results([
        {"title": "El Tiempo: Soria", "url": "https://www.aemet.es/x", "snippet": "31 grados"},
        {"title": "Meteored", "url": "https://www.tiempo.com/soria.htm", "snippet": "máxima 37"},
    ])
    assert [i["u"] for i in ev["items"]] == ["https://www.aemet.es/x", "https://www.tiempo.com/soria.htm"], \
        "la URL es lo que permite VOLVER a la fuente y comprobar: nunca se recorta fuera"
    assert ev["omitted"] == 0


def test_the_evidence_has_a_budget_and_says_what_it_left_out():
    """Without a limit, a search with long snippets would weigh more than the rest of the turn combined. And a
    SILENT truncation would be worse than truncation: an auditor would believe that was all there was."""
    from observability import evidence

    many = [{"title": f"r{i}", "url": f"https://e/{i}", "snippet": "x" * 400} for i in range(30)]
    ev = evidence.web_results(many)
    assert len(ev["items"]) <= evidence.MAX_ITEMS
    assert ev["omitted"] == 30 - len(ev["items"]) > 0
    assert all(len(i["s"]) <= evidence.MAX_SNIPPET for i in ev["items"])
    assert sum(len(i["t"]) + len(i["u"]) + len(i.get("s", "")) for i in ev["items"]) <= evidence.TOTAL


def test_clipping_marks_the_cut():
    from observability import evidence

    assert evidence.clip("abcdefghij", 5).endswith("…"), "un texto recortado tiene que PARECER recortado"
    assert evidence.clip("abc", 50) == "abc"
    assert evidence.clip(None, 10) == ""            # best-effort: evidence must never bring down the emitter


def test_a_worker_tool_result_is_recorded(wired):
    """The CLI stream's `tool_result` entries were discarded as «ruido interno», along with the only thing that
    makes it possible to audit a worker: what it requested was visible, never what it was told. A worker bringing
    junk and another bringing the exact data left THE SAME trace."""
    from observability import flows
    from voice.observer import emit

    emit("task", "web ↩", text="Tour 2026: ganó Vingegaard", extra={"id": "7", "evidence": True,
                                                                    "span": "worker:7"})
    _settle()
    # Find THE EVENT ITSELF, not «the last one in the table». `rows[-1]` tied this test to nobody else
    # emitting a `task` afterward, and the store is SHARED: on 2026-08-25 it failed once in the full run
    # and passed on its own and when the suite was repeated. A test that depends on the order in which the
    # others run does not measure what it claims to measure, and its failure cannot distinguish a regression
    # from a coincidence.
    rows = [e for e in flows.events(limit=50) if e["kind"] == "task"]
    assert rows, "el resultado de una tool tiene que quedar registrado"
    mio = [e for e in rows if e.get("span") == "worker:7"]
    assert mio, "…y atribuido a SU actor, o no se puede agrupar por quién lo hizo"


# ── READING A SESSION: summary, cursor, and why NOT a time window ─────────────────────────────────────────────
def test_one_session_can_be_opened_and_summarised(wired):
    from observability import flows, identity
    from voice import trace
    from voice.observer import emit

    sid = identity.begin_session("test")["id"]
    trace.begin("ponme el tiempo")
    emit("brain", "decide", extra={"brain_ms": 100, "prompt_tokens": 500, "completion_tokens": 20})
    _settle()

    s = flows.session(sid)
    assert s and s["events"] >= 2 and s["flows"] >= 1
    assert s["tokens_in"] == 500
    assert flows.session("no-existe") == {}, "una sesión que no existe devuelve vacío, no una sesión fingida"


def test_the_cursor_never_repeats_nor_skips_an_event(wired):
    """`since_id` uses a monotonic key, not a time window: two events in the SAME millisecond are normal (the bus
    distributes quickly), and a time window would duplicate them or swallow one."""
    from observability import flows, identity
    from voice.observer import emit

    identity.begin_session("test")
    for i in range(5):
        emit("brain", f"e{i}")
    _settle()

    first = flows.events(limit=2)
    assert len(first) == 2
    nxt = flows.events(since_id=first[-1]["id"], limit=10)
    assert nxt and all(e["id"] > first[-1]["id"] for e in nxt), "nada anterior al cursor puede volver a salir"
    ids = [e["id"] for e in first + nxt]
    assert ids == sorted(ids) and len(ids) == len(set(ids)), "ni se repite ni se desordena"


def test_raw_events_carry_the_payload_untouched(wired):
    """An auditor needs the original, not our projection: evidence and everything that does not make it into
    columns lives in the payload."""
    import json

    from observability import flows, identity
    from voice.observer import emit

    identity.begin_session("test")
    emit("search", "🔎 resultados web", text="tiempo soria",
         extra={"evidence": {"items": [{"t": "AEMET", "u": "https://aemet.es"}], "omitted": 0}})
    _settle()
    row = [e for e in flows.events(limit=50) if e["kind"] == "search"][-1]
    payload = json.loads(row["payload"])
    assert payload["evidence"]["items"][0]["u"] == "https://aemet.es"


# ── THE LOCK: who can read the CONTENT ───────────────────────────────────────────────────────────────────────
# These routes were created for the local viewer and were open. At home it makes no difference; the SAME code
# runs in deployments where the port is reachable, and there «open» means that whoever finds the URL gets the
# conversations.
class _Req:
    def __init__(self, host="1.2.3.4", token=None):
        self.client = type("C", (), {"host": host})()
        self.headers = {"x-observability-token": token} if token else {}


def test_without_a_token_the_content_is_loopback_only(monkeypatch):
    from observability import api

    monkeypatch.delenv("ZAELAR_OBS_TOKEN", raising=False)
    assert api._allowed(_Req(host="127.0.0.1"))
    assert not api._allowed(_Req(host="203.0.113.9")), "sin token, desde fuera NO se lee el contenido"


def test_with_a_token_it_must_match(monkeypatch):
    from observability import api

    monkeypatch.setenv("ZAELAR_OBS_TOKEN", "s3cr3t")
    assert api._allowed(_Req(host="203.0.113.9", token="s3cr3t")), "con el token correcto se puede operar en remoto"
    assert not api._allowed(_Req(host="203.0.113.9", token="otro"))
    assert not api._allowed(_Req(host="127.0.0.1")), (
        "con token configurado, ni loopback pasa sin él: si no, un proceso local cualquiera de la máquina "
        "seguiría teniendo acceso libre al contenido")


def test_a_request_without_a_known_origin_is_denied(monkeypatch):
    """Fail-closed: if its origin cannot be determined, it is not served."""
    from observability import api

    monkeypatch.delenv("ZAELAR_OBS_TOKEN", raising=False)
    r = _Req()
    r.client = None
    assert not api._allowed(r)
