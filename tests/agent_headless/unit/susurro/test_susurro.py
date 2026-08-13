"""Tests del «Susurro» (V2-053 F1): fricción determinista, catálogo cerrado, aplicadores y ciclo del engine."""
import asyncio
import json

from nucleo.susurro import apply as sus_apply
from nucleo.susurro import catalog, engine, friction


# ── fricción ──────────────────────────────────────────────────────────────────────────────────────────────
def test_complaint_strong_es():
    assert friction.is_complaint("te he dicho que abras el reloj y no lo has hecho")
    assert friction.is_complaint("no era eso, me refería a la otra canción")
    assert friction.is_complaint("¿me estás escuchando? llevas un rato sin responder")
    assert friction.is_complaint("te lo he pedido tres veces ya")


def test_complaint_strong_en():
    assert friction.is_complaint("I already told you to open the clock")
    assert friction.is_complaint("that's not what I asked for")


def test_complaint_esta_mal_no_es_asi():
    # "eso está mal, no es así" = queja clara (2 señales débiles → dispara). Gap detectado en el test general.
    assert friction.is_complaint("eso está mal, no es así")


def test_complaint_false_positives():
    # usos legítimos que NO son queja (precisión > recall)
    assert not friction.is_complaint("ponla otra vez, me encanta esa canción")
    assert not friction.is_complaint("abre el widget del reloj")
    assert not friction.is_complaint("qué tiempo hace hoy en Soria")
    assert not friction.is_complaint("sí")
    assert not friction.is_complaint("no está mal la canción")      # elogio, NO queja
    assert not friction.is_complaint("así es, correcto")            # acuerdo, NO queja


def test_complaint_present_continuous():
    # "te lo estoy preguntando otra vez" = frustración de repetir (gap detectado en la batería e2e)
    assert friction.is_complaint("¿qué tiempo hará mañana? te lo estoy preguntando otra vez")
    assert friction.is_complaint("te lo estoy pidiendo por segunda vez")


def test_repeated_request():
    prev = ["abre el widget de la agenda de hoy"]
    assert friction.repeated_request("abre el widget de la agenda de hoy por favor", prev)
    assert not friction.repeated_request("sí", prev)                  # corto = nunca repetición
    assert not friction.repeated_request("pon música de Sabina", prev)


def test_system_friction_map():
    assert friction.system_friction("alert")
    assert friction.system_friction("rail", "🛤 fail music")
    assert friction.system_friction("", topic="worker.stuck")
    assert not friction.system_friction("brain", "reply")


def test_risky_decision_v2061():
    # caso ITV: una DATA-OP (agenda.drop → data_done) SIN escalar sobre una orden del mundo real → riesgo (audita)
    assert friction.risky_decision({"data_done": True, "clarify": True})
    assert friction.risky_decision({"data_done": True})
    # V2-081: un simple SHOW/CLOSE de canvas (widget_acted SIN data_done) NO es riesgo — abrir/cerrar/mostrar un
    # widget nunca es una acción del mundo reflejada en local (incidente 2026-08-01: un close disparó a Susurro →
    # sobre-escaló un "muestra el mensaje" → widget basura). Solo la MUTACIÓN de datos cuenta.
    assert not friction.risky_decision({"widget_acted": True})
    assert not friction.risky_decision({"widget_acted": True, "clarify": True})
    # ya escaló (camino pesado correcto) o charla pura → sin riesgo
    assert not friction.risky_decision({"escalated": True, "data_done": True})
    assert not friction.risky_decision({})
    assert not friction.risky_decision(None)
    # BUG 2026-07-25: un confirm-gate ABIERTO (data_done PERO confirm_opened=true) NO es riesgo — la acción está
    # pendiente del Sí/No del operador, no ejecutada en falso. Susurro no debe re-rutearla a un worker.
    assert not friction.risky_decision({"data_done": True, "confirm_opened": True})


# ── catálogo ──────────────────────────────────────────────────────────────────────────────────────────────
def test_catalog_parse_tolerant():
    raw = '```json\n{"assessment":"x","corrections":[]}\n```'
    assert catalog.parse(raw) == {"assessment": "x", "corrections": []}
    assert catalog.parse("nada de json") is None


def test_catalog_validate_f1_and_downgrade():
    parsed = {"corrections": [
        {"type": "repair_say", "text": "Perdona, el dato correcto es X."},
        {"type": "repair_say", "text": "segunda (debe caer: máx 1)"},
        {"type": "finding", "severity": "P1", "area": "routing", "title": "t", "detail": "d", "proposal": "p"},
        {"type": "state_patch", "fields": {"topics": "x"}},           # fase futura → finding degradado
        {"type": "desconocido", "x": 1},                              # fuera de catálogo → descartado
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


# ── aplicadores ───────────────────────────────────────────────────────────────────────────────────────────
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
    # F2 (V2-061): worker_action lanza la escalada por la vía del FlashBrain, con el request como goal.
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
    # Guard anti-bucle (auditoría 2026-07-26): tras _BREAKER_MAX escaladas OK en la ventana, el circuito se ABRE
    # y NINGÚN worker_action nuevo sale, aunque el dedup de texto no lo hubiera pillado (requests distintos).
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
    # NO relanza si ya hay una sesión viva con un objetivo muy similar (dedup duro).
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


# ── topic semántico turn.completed (costura de modularidad) ─────────────────────────────────────────────
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


# ── engine: kill-switch + ciclo completo con LLM falso ──────────────────────────────────────────────────
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
        engine.reset()
        brain_notes.drain()
        monkeypatch.setattr(engine, "_cfg", lambda: {"enabled": True, "cooldown_s": 0.0,
                                                     "window_turns": 2, "pulse_turns": 0, "model": "test"})
        # PRECONDICIÓN desde 2026-08-13: sin conversación en la ventana no se audita (ver
        # `window.has_conversation`: con la ventana vacía el auditor RELLENA con los ejemplos de su propio prompt y
        # llegó a despachar un worker a cancelar una cita que nadie pidió). El buffer se siembra explícitamente.
        from memory import api as _mapi
        monkeypatch.setattr(_mapi, "recent_window",
                            lambda limit=8: [{"u": "te he dicho que abras la agenda y no lo has hecho",
                                              "a": "abrí el reloj"}])
        monkeypatch.setattr(client, "audit_llm", fake_llm)
        monkeypatch.setattr(sus_apply, "FINDINGS_PATH", str(tmp_path / "f.jsonl"))
        engine.start()
        try:
            bus.emit_sync("turn.completed", {"user": "te he dicho que abras la agenda y no lo has hecho",
                                             "decision": {}, "trace": "Ttest"})
            for _ in range(40):                       # espera acotada al ciclo async
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
    # V2-061 e2e: turno de RIESGO (acción de widget sin escalar, SIN queja del operador) → Susurro audita por su
    # cuenta y RE-RUTEA con worker_action (el caso ITV: «hay que cancelarlo» → drop de agenda + «hecho» falso).
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
        # La conversación tiene que estar Y tiene que ANCLAR la acción: `worker_action` es la única corrección que
        # ACTÚA sobre el mundo, y desde 2026-08-13 exige que la petición hable de algo presente en la ventana.
        from memory import api as _mapi
        monkeypatch.setattr(_mapi, "recent_window",
                            lambda limit=8: [{"u": "hay que cancelar la cita de la ITV, la reservé en su web",
                                              "a": "hecho, la he quitado de la agenda"}])
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
            assert any("cancelar la ITV" in n for n in brain_notes.drain())   # y avisó al operador
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
        engine._last_audit_ts = __import__("time").time()      # como si acabara de auditar
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


# ── INCIDENTE 2026-08-13: el auditor INVENTÓ una acción sobre el mundo ─────────────────────────────────────────
# Saltó la fricción «worker encallado (sin eventos)» con el buffer conversacional VACÍO. El ensamblador omite las
# secciones vacías sin decir que faltan, así que la ventana salió de 1.643 caracteres SIN conversación. El auditor
# rellenó ese vacío con el EJEMPLO de su propio prompt de sistema (el caso ITV de V2-061), afirmó como hecho «el
# operador pidió cancelar una cita real» y, con worker_action habilitado, DESPACHÓ UN WORKER a cancelar la cita.
# Una acción irreversible nacida de una alucinación, sin que el operador hubiera dicho una palabra.
def test_no_conversation_no_audit(monkeypatch):
    """Primera defensa: un auditor de CONVERSACIONES no opina cuando no hay conversación. Abstenerse es gratis."""
    from memory import api as _mapi
    from nucleo.susurro import window as _win
    monkeypatch.setattr(_mapi, "recent_window", lambda limit=8: [])
    assert _win.has_conversation() is False
    monkeypatch.setattr(_mapi, "recent_window", lambda limit=8: [{"u": "hola", "a": "buenas"}])
    assert _win.has_conversation() is True


def test_the_engine_skips_the_audit_when_there_is_nothing_to_audit(monkeypatch, tmp_path):
    """Y el ciclo NO llama al LLM: si llamara, volvería a poder inventar."""
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
        monkeypatch.setattr(_mapi, "recent_window", lambda limit=8: [])       # ventana VACÍA
        monkeypatch.setattr(client, "audit_llm", fake_llm)
        monkeypatch.setattr(sus_apply, "FINDINGS_PATH", str(tmp_path / "f.jsonl"))
        engine.start()
        try:
            bus.emit_sync("worker.stuck", {"id": "1", "trace": "T"})
            for _ in range(20):
                await asyncio.sleep(0.05)
            assert called["n"] == 0, "auditó sin conversación → puede inventar"
            assert engine.status()["audits"] == 0
        finally:
            await engine.stop()
            engine.reset()
    asyncio.run(run())


def test_an_action_that_is_not_in_the_window_is_never_executed():
    """Segunda defensa (en profundidad): aun CON ventana, la única corrección que ACTÚA sobre el mundo exige
    ANCLAJE. Si la petición no habla de nada que esté en la ventana auditada, viene de fuera de la conversación —
    del prompt de sistema, de otra sesión, de donde sea — y no se ejecuta.

    Fail-OPEN sin ventana con la que comparar (no rompe lo que ya funcionaba), fail-CLOSED cuando hay ventana."""
    from nucleo.susurro.apply import _grounded
    win = ("=== CONVERSACIÓN RECIENTE ===\nOPERADOR: móntame un viaje a Ibiza con ferry y hotel\n"
           "  ZAELAR: me pongo con ello")
    assert _grounded("busca el ferry a Ibiza y el hotel", win) is True
    # la INVENCIÓN del incidente: nada de esto está en la ventana
    assert _grounded("cancela la cita de la ITV del 15 de junio en el sistema externo donde se reservó", win) is False
    assert _grounded("cualquier cosa", "") is True          # sin ventana → fail-open


def test_an_ungrounded_action_is_reported_not_silently_dropped(monkeypatch, tmp_path):
    """Descartarla en silencio la volvería invisible: el operador no sabría que su auditor está inventando. Queda
    el registro con `ungrounded` y su evento — estado VISIBLE, no silencioso."""
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
