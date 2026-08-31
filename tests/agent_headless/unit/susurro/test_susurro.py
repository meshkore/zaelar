"""Tests for «Susurro» (V2-053 F1): deterministic friction, closed catalog, applicators, and engine cycle."""
import asyncio
import json

from nucleo.susurro import apply as sus_apply
from nucleo.susurro import catalog, engine, friction


# ── friction ──────────────────────────────────────────────────────────────────────────────────────────────
def test_complaint_strong_es():
    assert friction.is_complaint("te he dicho que abras el reloj y no lo has hecho")
    assert friction.is_complaint("no era eso, me refería a la otra canción")
    assert friction.is_complaint("¿me estás escuchando? llevas un rato sin responder")
    assert friction.is_complaint("te lo he pedido tres veces ya")


def test_complaint_strong_en():
    assert friction.is_complaint("I already told you to open the clock")
    assert friction.is_complaint("that's not what I asked for")


def test_complaint_esta_mal_no_es_asi():
    # "eso está mal, no es así" = clear complaint (2 weak signals → triggers). Gap found in the general test.
    assert friction.is_complaint("eso está mal, no es así")


def test_complaint_false_positives():
    # legitimate uses that are NOT complaints (precision > recall)
    assert not friction.is_complaint("ponla otra vez, me encanta esa canción")
    assert not friction.is_complaint("abre el widget del reloj")
    assert not friction.is_complaint("qué tiempo hace hoy en Soria")
    assert not friction.is_complaint("sí")
    assert not friction.is_complaint("no está mal la canción")      # praise, NOT a complaint
    assert not friction.is_complaint("así es, correcto")            # agreement, NOT a complaint


def test_complaint_present_continuous():
    # "te lo estoy preguntando otra vez" = frustration from repetition (gap found in the e2e suite)
    assert friction.is_complaint("¿qué tiempo hará mañana? te lo estoy preguntando otra vez")
    assert friction.is_complaint("te lo estoy pidiendo por segunda vez")


def test_repeated_request():
    prev = ["abre el widget de la agenda de hoy"]
    assert friction.repeated_request("abre el widget de la agenda de hoy por favor", prev)
    assert not friction.repeated_request("sí", prev)                  # short = never a repetition
    assert not friction.repeated_request("pon música de Sabina", prev)


def test_system_friction_map():
    assert friction.system_friction("alert")
    assert friction.system_friction("rail", "🛤 fail music")
    assert friction.system_friction("", topic="worker.stuck")
    assert not friction.system_friction("brain", "reply")


def test_risky_decision_v2061():
    # ITV case: a DATA-OP (agenda.drop → data_done) WITHOUT escalation on a real-world order → risk (audit)
    assert friction.risky_decision({"data_done": True, "clarify": True})
    assert friction.risky_decision({"data_done": True})
    # V2-081: a simple canvas SHOW/CLOSE (widget_acted WITHOUT data_done) is NOT a risk — opening/closing/showing a
    # widget is never a real-world action reflected locally (2026-08-01 incident: a close triggered Susurro →
    # it over-escalated a "show the message" request → junk widget). Only data MUTATION counts.
    assert not friction.risky_decision({"widget_acted": True})
    assert not friction.risky_decision({"widget_acted": True, "clarify": True})
    # already escalated (the correct heavyweight path) or pure conversation → no risk
    assert not friction.risky_decision({"escalated": True, "data_done": True})
    assert not friction.risky_decision({})
    assert not friction.risky_decision(None)
    # BUG 2026-07-25: an OPEN confirm gate (data_done BUT confirm_opened=true) is NOT a risk — the action is
    # pending the operator's Yes/No, not falsely executed. Susurro must not reroute it to a worker.
    assert not friction.risky_decision({"data_done": True, "confirm_opened": True})


# ── catalog ──────────────────────────────────────────────────────────────────────────────────────────────
def test_catalog_parse_tolerant():
    raw = '```json\n{"assessment":"x","corrections":[]}\n```'
    assert catalog.parse(raw) == {"assessment": "x", "corrections": []}
    assert catalog.parse("nada de json") is None


def test_catalog_validate_f1_and_downgrade():
    parsed = {"corrections": [
        {"type": "repair_say", "text": "Perdona, el dato correcto es X."},
        {"type": "repair_say", "text": "segunda (debe caer: máx 1)"},
        {"type": "finding", "severity": "P1", "area": "routing", "title": "t", "detail": "d", "proposal": "p"},
        {"type": "state_patch", "fields": {"topics": "x"}},           # future phase → downgraded finding
        {"type": "desconocido", "x": 1},                              # outside catalog → discarded
    ]}
    ok, down = catalog.validate(parsed)
    types = [c["type"] for c in ok]
    assert types == ["repair_say", "finding"]
    assert len(down) == 1 and down[0]["type"] == "finding" and "state_patch" in down[0]["detail"]


def test_catalog_validate_worker_action_f2():
    parsed = {"corrections": [
        {"type": "worker_action", "request": "cancela la cita de la ITV en la web donde se reservó",
         "reason": "trató una cancelación real como un borrado de agenda"},
        {"type": "worker_action", "request": "segunda (debe caer: máx 1)"},
        {"type": "repair_say", "text": "Perdona, me pongo a cancelarla de verdad."},
    ]}
    ok, _down = catalog.validate(parsed)
    wa = [c for c in ok if c["type"] == "worker_action"]
    assert len(wa) == 1 and "ITV" in wa[0]["request"]
    assert any(c["type"] == "repair_say" for c in ok)


# ── applicators ───────────────────────────────────────────────────────────────────────────────────────────
def test_apply_repair_say_pushes_brain_note():
    from voice import brain_notes
    brain_notes.drain()
    recs = sus_apply.apply_corrections([{"type": "repair_say", "text": "Perdona, era el jueves."}],
                                       reason="test")
    assert recs[0]["ok"]
    notes = brain_notes.drain()
    assert any("Perdona, era el jueves." in n and "[SISTEMA]" in n for n in notes)


def test_apply_finding_dedup(tmp_path):
    path = str(tmp_path / "findings.jsonl")
    f = {"type": "finding", "severity": "P2", "area": "routing", "title": "bug X", "detail": "d", "proposal": "p"}
    r1 = sus_apply.apply_corrections([f], reason="test", findings_path=path)
    r2 = sus_apply.apply_corrections([f], reason="test", findings_path=path)
    assert not r1[0]["dedup"] and r2[0]["dedup"]
    lines = open(path, encoding="utf-8").read().strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["title"] == "bug X"


def test_apply_worker_action_dispatches(monkeypatch):
    # F2 (V2-061): worker_action launches escalation through FlashBrain, with the request as the goal.
    from nucleo import dispatch
    from nucleo.flash import escalate
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    seen = {}
    monkeypatch.setattr(escalate, "escalate_to_slowbrain",
                        lambda req, **kw: seen.setdefault("req", req) and None or 77)
    recs = sus_apply.apply_corrections(
        [{"type": "worker_action", "request": "cancela la cita de la ITV en su web", "reason": "r"}],
        reason="riesgo")
    assert recs[0]["ok"] and str(recs[0]["child"]) == "77" and not recs[0]["dedup"]
    assert "ITV" in seen["req"]


def test_apply_worker_action_breaker_trips_after_max(monkeypatch):
    # Anti-loop guard (2026-07-26 audit): after _BREAKER_MAX successful escalations in the window, the circuit OPENS
    # and NO new worker_action is sent, even if text deduplication would not have caught it (different requests).
    from nucleo import dispatch
    from nucleo.flash import escalate
    sus_apply.breaker_reset()
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    fired = {"n": 0}

    def _go(req, **kw):
        fired["n"] += 1
        return 100 + fired["n"]
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", _go)
    try:
        reqs = ["cancela la cita de la ITV", "confirma el envío del paquete", "revisa el estado del pedido",
                "verifica que se completó la reserva"]
        recs = [sus_apply.apply_corrections(
            [{"type": "worker_action", "request": r, "reason": "r"}], reason="riesgo")[0] for r in reqs]
        assert fired["n"] == sus_apply._BREAKER_MAX             # solo las 3 primeras escalaron de verdad
        assert all(r["ok"] for r in recs[:sus_apply._BREAKER_MAX])
        assert recs[-1]["breaker"] is True and not recs[-1]["ok"] and not recs[-1]["dedup"]
    finally:
        sus_apply.breaker_reset()


def test_apply_worker_action_dedup_vs_active(monkeypatch):
    # Does NOT relaunch if there is already a live session with a very similar goal (hard deduplication).
    from nucleo import dispatch
    from nucleo.flash import escalate
    monkeypatch.setattr(dispatch, "active_sessions",
                        lambda: [{"id": "s1", "goal": "cancela la cita de la ITV en su web"}])
    fired = {"n": 0}

    def _no(*a, **k):
        fired["n"] += 1
        return 1
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", _no)
    recs = sus_apply.apply_corrections(
        [{"type": "worker_action", "request": "cancela la cita de la ITV en su web", "reason": "r"}],
        reason="riesgo")
    assert recs[0]["dedup"] and not recs[0]["ok"] and fired["n"] == 0


# ── semantic turn.completed topic (modularity seam) ─────────────────────────────────────────────────────
def test_turn_completed_topic():
    import bus
    from voice import observer

    async def run():
        sub = bus.subscribe("turn.completed")
        observer.turn_detail(system="SYS", window=[], tools=[{"function": {"name": "web_search"}}],
                             user="hola", decision={"searched": True})
        ev = await asyncio.wait_for(sub.get(), 2)
        assert ev["user"] == "hola" and ev["decision"]["searched"] and "web_search" in ev["tools"]
        bus.unsubscribe(sub)
    asyncio.run(run())


# ── engine: kill switch + complete cycle with fake LLM ─────────────────────────────────────────────────
def test_engine_killswitch_env(monkeypatch):
    monkeypatch.setenv("ZAELAR_SUSURRO", "0")
    assert not engine.enabled()
    monkeypatch.delenv("ZAELAR_SUSURRO")
    monkeypatch.setattr(engine, "_cfg", lambda: {"enabled": False})
    assert not engine.enabled()


def test_engine_audit_cycle(monkeypatch, tmp_path):
    from nucleo.susurro import client

    fake = {"assessment": "el cerebro rápido abrió el widget equivocado",
            "corrections": [
                {"type": "repair_say", "text": "Perdona, antes abrí el widget equivocado; ya está el bueno."},
                {"type": "finding", "severity": "P2", "area": "routing", "title": "reloj vs agenda",
                 "detail": "d", "proposal": "p"},
            ]}

    async def fake_llm(doc):
        assert "FRICCIÓN" in doc
        return json.dumps(fake, ensure_ascii=False), {"model": "test", "ms": 1, "request": {"messages": []}}

    async def run():
        import bus

        from voice import brain_notes
        # The machine this runs on must not decide the result (testmap node 7.10). This test's wait for the
        # audit is bounded at 2 s, and with `auto` the first memory read in the process can spend longer than
        # that just loading a real embedding backend — which is nothing this test is about. Two other tests in
        # this same file already pin it for the same reason; this one was the omission, and it showed up as a
        # reproducible failure only once the local Ollama stopped serving `embeddinggemma` and the fallback to
        # fastembed started paying an ONNX load. Verified at HEAD with no product change in the tree.
        monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
        engine.reset()
        brain_notes.drain()
        monkeypatch.setattr(engine, "_cfg", lambda: {"enabled": True, "cooldown_s": 0.0,
                                                     "window_turns": 2, "pulse_turns": 0, "model": "test"})
        # PREREQUISITE since 2026-08-13: without a conversation in the window, no audit is performed (see
        # `window.has_conversation`: with an empty window, the auditor FILLS it with examples from its own prompt and
        # ended up dispatching a worker to cancel an appointment nobody requested). The buffer is seeded explicitly.
        from memory import api as _mapi
        # REAL SHAPE of `recent_window`: role/content chat messages (NOT u/a pairs — that is the metadata shape in the
        # DB). Mocks with the wrong shape are what allowed the dead auditor of 2026-08-14 to pass.
        monkeypatch.setattr(_mapi, "recent_window",
                            lambda limit=8: [{"role": "user", "content": "te he dicho que abras la agenda y no lo has hecho"},
                                             {"role": "assistant", "content": "abrí el reloj"}])
        monkeypatch.setattr(client, "audit_llm", fake_llm)
        monkeypatch.setattr(sus_apply, "FINDINGS_PATH", str(tmp_path / "f.jsonl"))
        engine.start()
        try:
            bus.emit_sync("turn.completed", {"user": "te he dicho que abras la agenda y no lo has hecho",
                                             "decision": {}, "trace": "Ttest"})
            for _ in range(40):                       # bounded wait for the async cycle
                await asyncio.sleep(0.05)
                if engine.status()["audits"] >= 1:
                    break
            st = engine.status()
            assert st["audits"] == 1 and st["corrections_applied"] == 2, st
            notes = brain_notes.drain()
            assert any("widget equivocado" in n for n in notes)
            assert (tmp_path / "f.jsonl").exists()
        finally:
            await engine.stop()
            engine.reset()
    asyncio.run(run())


def test_engine_risky_triggers_worker_action(monkeypatch, tmp_path):
    # V2-061 e2e: RISK turn (widget action without escalation, WITHOUT operator complaint) → Susurro audits on its
    # own and REROUTES with worker_action (the ITV case: «hay que cancelarlo» → calendar drop + false «hecho»).
    from nucleo import dispatch
    from nucleo.flash import escalate as _esc
    from nucleo.susurro import client

    fake = {"assessment": "trató una cancelación real como un borrado de agenda",
            "corrections": [
                {"type": "worker_action", "request": "cancela la cita de la ITV en la web donde se reservó y "
                 "bórrala luego de la agenda", "reason": "dijo hecho sin ejecutar la cancelación real"},
                {"type": "repair_say", "text": "Perdona, me pongo a cancelar la ITV de verdad ahora."},
            ]}

    async def fake_llm(doc):
        return json.dumps(fake, ensure_ascii=False), {"model": "test", "ms": 1, "request": {"messages": []}}

    async def run():
        import bus

        from voice import brain_notes
        engine.reset()
        brain_notes.drain()
        monkeypatch.setattr(engine, "_cfg", lambda: {"enabled": True, "cooldown_s": 0.0, "window_turns": 2,
                                                     "pulse_turns": 0, "model": "test", "audit_consequential": True})
        # The conversation must exist AND ANCHOR the action: `worker_action` is the only correction that ACTS on the
        # world, and since 2026-08-13 requires the request to mention something present in the window.
        from memory import api as _mapi
        monkeypatch.setattr(_mapi, "recent_window",
                            lambda limit=8: [{"role": "user", "content": "hay que cancelar la cita de la ITV, la reservé en su web"},
                                             {"role": "assistant", "content": "hecho, la he quitado de la agenda"}])
        monkeypatch.setattr(client, "audit_llm", fake_llm)
        monkeypatch.setattr(sus_apply, "FINDINGS_PATH", str(tmp_path / "f.jsonl"))
        monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
        dispatched = {}
        monkeypatch.setattr(_esc, "escalate_to_slowbrain",
                            lambda req, **kw: dispatched.setdefault("req", req) and None or 99)
        engine.start()
        try:
            bus.emit_sync("turn.completed", {"user": "hay que cancelarlo",
                                             "decision": {"data_done": True, "clarify": True}, "trace": "Titv"})
            for _ in range(40):
                await asyncio.sleep(0.05)
                if engine.status()["audits"] >= 1:
                    break
            assert engine.status()["audits"] == 1
            assert "ITV" in dispatched.get("req", "")               # re-ruteó al worker correcto
            assert any("cancelar la ITV" in n for n in brain_notes.drain())   # and notified the operator
        finally:
            await engine.stop()
            engine.reset()
    asyncio.run(run())


def test_engine_cooldown_skips(monkeypatch):
    async def run():
        import bus
        engine.reset()
        monkeypatch.setattr(engine, "_cfg", lambda: {"enabled": True, "cooldown_s": 9999,
                                                     "window_turns": 2, "pulse_turns": 0})
        engine._last_audit_ts = __import__("time").time()      # as if it had just audited
        engine.start()
        try:
            bus.emit_sync("turn.completed", {"user": "te he dicho que no era eso", "decision": {}, "trace": "T2"})
            await asyncio.sleep(0.2)
            assert engine.status()["audits"] == 0
            assert engine.status()["triggers_skipped"] >= 1
        finally:
            await engine.stop()
            engine.reset()
    asyncio.run(run())


# ── INCIDENT 2026-08-13: the auditor INVENTED a real-world action ─────────────────────────────────────────────
# The «stuck worker (no events)» friction trigger fired with an EMPTY conversation buffer. The assembler omits empty
# sections without saying they are missing, so the window contained 1,643 characters WITHOUT a conversation. The auditor
# filled that void with the EXAMPLE from its own system prompt (the V2-061 ITV case), stated as fact that «the operator
# requested cancellation of a real appointment» and, with worker_action enabled, DISPATCHED A WORKER to cancel it.
# An irreversible action born from a hallucination, without the operator saying a word.
def test_no_conversation_no_audit(monkeypatch):
    """First defense: a CONVERSATION auditor does not weigh in when there is no conversation. Abstaining is free."""
    from memory import api as _mapi
    from nucleo.susurro import window as _win
    monkeypatch.setattr(_mapi, "recent_window", lambda limit=8: [])
    assert _win.has_conversation() is False
    # The REAL shape returned by `recent_window` (chat messages). This test used to say `{"u":…,"a":…}` —the shape of
    # the DB METADATA, not the return value—so it passed while in production the window was ALWAYS empty and Susurro
    # never audited. See `test_window_reads_the_real_recent_window_shape` below.
    monkeypatch.setattr(_mapi, "recent_window",
                        lambda limit=8: [{"role": "user", "content": "hola"},
                                         {"role": "assistant", "content": "buenas"}])
    assert _win.has_conversation() is True
    # …and the legacy u/a pair is still tolerated (an old record must not disable the auditor).
    monkeypatch.setattr(_mapi, "recent_window", lambda limit=8: [{"u": "hola", "a": "buenas"}])
    assert _win.has_conversation() is True


def test_the_engine_skips_the_audit_when_there_is_nothing_to_audit(monkeypatch, tmp_path):
    """And the cycle does NOT call the LLM: if it did, it could invent things again."""
    from memory import api as _mapi
    from nucleo.susurro import client

    called = {"n": 0}

    async def fake_llm(doc):
        called["n"] += 1
        return "{}", {"model": "test", "ms": 1, "request": {"messages": []}}

    async def run():
        import bus
        engine.reset()
        monkeypatch.setattr(engine, "_cfg", lambda: {"enabled": True, "cooldown_s": 0.0, "window_turns": 2,
                                                    "pulse_turns": 0, "model": "test"})
        monkeypatch.setattr(_mapi, "recent_window", lambda limit=8: [])       # EMPTY window
        monkeypatch.setattr(client, "audit_llm", fake_llm)
        monkeypatch.setattr(sus_apply, "FINDINGS_PATH", str(tmp_path / "f.jsonl"))
        engine.start()
        try:
            bus.emit_sync("worker.stuck", {"id": "1", "trace": "T"})
            for _ in range(20):
                await asyncio.sleep(0.05)
            assert called["n"] == 0, "audited without a conversation → it could invent things"
            assert engine.status()["audits"] == 0
        finally:
            await engine.stop()
            engine.reset()
    asyncio.run(run())


def test_an_action_that_is_not_in_the_window_is_never_executed():
    """Second defense (in depth): even WITH a window, the only correction that ACTS on the world requires
    GROUNDING. If the request does not mention anything in the audited window, it comes from outside the conversation —
    from the system prompt, another session, wherever — and is not executed.

    Fail-OPEN without a window for comparison (does not break what already worked), fail-CLOSED when a window exists."""
    from nucleo.susurro.apply import _grounded
    win = ("=== CONVERSACIÓN RECIENTE ===\nOPERADOR: móntame un viaje a Ibiza con ferry y hotel\n"
           "  ZAELAR: me pongo con ello")
    assert _grounded("busca el ferry a Ibiza y el hotel", win) is True
    # the incident's INVENTION: none of this is in the window
    assert _grounded("cancela la cita de la ITV del 15 de junio en el sistema externo donde se reservó", win) is False
    assert _grounded("cualquier cosa", "") is True          # without a window → fail-open


def test_an_ungrounded_action_is_reported_not_silently_dropped(monkeypatch, tmp_path):
    """Silently discarding it would make it invisible: the operator would not know their auditor is inventing things. The
    record and its event remain with `ungrounded` — VISIBLE state, not silent."""
    from nucleo import dispatch
    from nucleo.flash import escalate as _esc
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    fired = {}
    monkeypatch.setattr(_esc, "escalate_to_slowbrain", lambda req, **kw: fired.setdefault("req", req) or 1)
    sus_apply.breaker_reset()
    out = sus_apply.apply_corrections(
        [{"type": "worker_action", "request": "cancela la cita de la ITV del 15 de junio a las 10:00"}],
        reason="worker encallado (sin eventos)", window="OPERADOR: móntame un viaje a Ibiza con ferry y hotel",
        findings_path=str(tmp_path / "f.jsonl"))
    assert fired == {}, "se ejecutó una acción que no estaba en la ventana"
    assert out and out[0]["ok"] is False and out[0]["ungrounded"] is True


# ── WINDOW↔MEMORY CONTRACT (2026-08-14) — the test that DOES catch the dead auditor ─────────────────────────
# `window.conversation_block` leía `u`/`user`/`a`/`assistant`; `memory.recent_window` devuelve `role`/`content`.
# Result: block ALWAYS empty → `has_conversation()` ALWAYS False → **Susurro never audited**, and the timeline reported
# it as legitimate abstention («audit OMITTED (window without conversation)») across 16 turns of live conversation. It was
# discovered while auditing session b70a45d0, where it detected the real failure SIX times and stayed silent all six.
#
# Why nothing caught it: ALL tests above mock `recent_window` — and mocked it with the DB METADATA shape
# (`{"u":…, "a":…}`), not the RETURN shape. Mock and code mutually confirmed each other while both were wrong about
# reality. It is the same family as the `_DATA_DIR` that did not exist in the YouTube test: a guard that appears to
# protect but does not.
#
# This test mocks NOTHING: it writes to the REAL conversation buffer through the real path and reads through the real
# function. If either side of the contract changes, this fails here.
def test_window_reads_the_real_recent_window_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    from memory import api as memory
    from memory import db as memdb
    from memory import embeddings as mememb
    from nucleo.susurro import window as _win

    memdb.reset_db()
    memdb.get_db()
    mememb.reset()
    try:
        assert _win.has_conversation() is False, "base vacía: sin conversación de verdad"

        # EXACTLY as the voice provider writes it (nucleo.py: kind='conv' + meta.source/u/a).
        memory.write("Operador: vacía la agenda entera · zaelar: hecho",
                     kind="conv", level="short", importance=0.2, ttl_days=2.0,
                     meta={"source": "conv", "u": "vacía la agenda entera", "a": "hecho"})

        win = memory.recent_window(limit=8) or []
        assert win, "el buffer conversacional real no devolvió nada"
        # The contract, explicitly: these are CHAT MESSAGES, not per-turn pairs.
        assert {"role", "content"} <= set(win[0]), f"shape inesperado de recent_window: {sorted(win[0])}"

        block = _win.conversation_block(8)
        assert "vacía la agenda entera" in block, "la ventana no ve lo que el operador dijo"
        assert "hecho" in block, "la ventana no ve lo que zaelar respondió"
        assert _win.has_conversation() is True, "con conversación viva, Susurro TIENE que poder auditar"
    finally:
        memdb.reset_db()
        mememb.reset()


# ── conversational-buffer recency (V2-105 follow-up, 2026-08-17) ───────────────────────────────────────────
# `memory.recent_window` is a SINGLE global buffer (no session_id, no per-line trace) with a 2-day TTL — on
# purpose, it's the FlashBrain's own continuity across reconnects. Confirmed with real data: a use_cases test
# session's "Vale, avísame." turn triggered friction, and the auditor received — with no age marker at all — a
# REAL operator conversation from 11 HOURS earlier (a World Cup ball's price) mixed into the same "recent
# conversation" block, and escalated it as if it were the pending request of THIS moment, attached to the test
# session's trace. `turn_ring`/`event_ring` already had a recency cutoff (`recency_window_s`) for an identical
# prior incident ("a scenario diagnosed a different EARLIER one's failure"); this was the one section of the
# document that gap didn't cover.
def test_conversation_block_drops_entries_older_than_since_ts(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    import time as _time
    from memory import api as memory
    from memory import db as memdb
    from memory import embeddings as mememb
    from nucleo.susurro import window as _win

    memdb.reset_db()
    db = memdb.get_db()
    mememb.reset()
    try:
        memory.write("Operador: cuánto vale el balón del mundial · zaelar: lo miro",
                     kind="conv", level="short", importance=0.2, ttl_days=2.0,
                     meta={"source": "conv", "u": "cuánto vale el balón del mundial", "a": "lo miro"})
        # Backdate it 11h — same gap as the real incident. `memory.write` always stamps "now"; there's no
        # override, so the test does what a passing 11h really means: move `created` back directly.
        eleven_hours_ago = _time.time() - 11 * 3600
        db.execute("UPDATE memories SET created=?, updated=? WHERE json_extract(meta,'$.source')='conv'",
                  (eleven_hours_ago, eleven_hours_ago))

        memory.write("Operador: búscame un hotel para dentro de 15 días · zaelar: me pongo con ello",
                     kind="conv", level="short", importance=0.2, ttl_days=2.0,
                     meta={"source": "conv", "u": "búscame un hotel para dentro de 15 días",
                           "a": "me pongo con ello"})

        # WITHOUT a cutoff (default, since_ts=0.0): sees both — unchanged behavior, nothing broken.
        block_all = _win.conversation_block(8)
        assert "balón" in block_all and "hotel" in block_all

        # WITH the same cutoff engine.py already uses for turn_ring/event_ring (recency_window_s, default
        # 180s): the ball entry drops out, the freshly-written hotel one stays.
        cut = _time.time() - 180
        block_recent = _win.conversation_block(8, since_ts=cut)
        assert "balón" not in block_recent, "an 11h-old entry must not read as friction from RIGHT NOW"
        assert "hotel" in block_recent, "the genuinely recent entry must not disappear"
        assert _win.has_conversation(8, since_ts=cut) is True
    finally:
        memdb.reset_db()
        mememb.reset()
