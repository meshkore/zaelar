"""Tests del ciclo de vida de widgets + confirmación de borrado (V2-017)."""
import asyncio
import json
import os

from widgets import confirm, lifecycle, runtime


def setup_function():
    confirm.reset()


# ── confirm.py ──────────────────────────────────────────────────────────────────────────────────────────
def test_confirm_request_pending_resolve():
    assert confirm.request("delete", "Meteo") == "meteo"           # normaliza a minúsculas
    assert "meteo" in confirm.pending()
    p = confirm.resolve("meteo", ok=True)
    assert p and p["widget_id"] == "meteo" and p["action"] == "delete"
    assert "meteo" not in confirm.pending()                        # resuelta → ya no pendiente
    assert confirm.resolve("meteo", ok=True) is None               # no hay nada que resolver dos veces


def test_confirm_resolve_without_id_picks_the_only_one():
    confirm.request("delete", "agenda")
    p = confirm.resolve("", ok=True)                               # la voz no siempre nombra el widget
    assert p and p["widget_id"] == "agenda"


def test_confirm_carries_data_op(monkeypatch):
    """V2-025: una acción irreversible de DATOS abre una confirmación que ACARREA la mutación — al resolver, el
    llamante la despacha por apply_action (nunca escala a código)."""
    op = {"action": "drop_project", "payload": {"projectId": "p1"}}
    assert confirm.request("data", "agenda", "¿Confirmas «drop_project»?", op=op) == "agenda"
    line = confirm.pending_line()
    assert "drop_project" in line                                  # el estado del cerebro nombra la acción
    p = confirm.resolve("agenda", ok=True)
    assert p and p["action"] == "data" and p["op"] == op           # la mutación sobrevive a la confirmación


def test_confirm_carries_the_asking_turns_trace(monkeypatch):
    """V2-090 addenda (2026-08-15): the operator's yes/no reply lands in its OWN turn/trace — a different flow
    than the one that asked, in the master's observability, unless the resolver adopts the asking turn's trace.
    `request()` must capture it so `resolve()` can hand it back."""
    from voice import trace
    trace.adopt("")
    tid = trace.begin("borra toda la agenda", origin="turno")
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})
    trace.adopt("")   # simulate the reply landing in a fresh turn, as the real provider does
    p = confirm.resolve("agenda", ok=True)
    assert p and p.get("trace_id") == tid
    trace.adopt("")


# ── orphaned/expired confirmations must not leave a flow stuck "EN CURSO" forever (2026-08-16) ────────────
# Real incident diagnosed live: "borra todos los datos de mi agenda." got split by the segmenter into TWO turns
# (a period-terminated fragment fired immediately, the continuation a moment later reopened as a fresh trace).
# Both asked to confirm the SAME widget's data-op; the second silently clobbered the first in `_PENDING`, and
# the first turn's flow — which had already decided, once, to stay open "while confirm pending" — never got
# revisited to close. It sat "EN CURSO" in the master forever, unanswerable, with no signal to the operator.
def test_a_second_ask_on_the_same_widget_closes_the_first_ones_flow(monkeypatch):
    from voice import observer, trace

    trace.adopt("")
    old_tid = trace.begin("borra toda la agenda", origin="turno")
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})

    trace.adopt("")
    new_tid = trace.begin("borra toda la agenda, pasados y futuros", origin="turno")
    confirm.request("data", "agenda", "¿Vacío la agenda entera (pasados y futuros)?",
                     op={"action": "clear_all", "payload": {}})

    closes = [e for e in observer.debug_events(kind="flow") if e.get("trace") == old_tid]
    assert closes, "the FIRST ask's flow never got an explicit close — it would show EN CURSO forever"
    assert closes[-1].get("reason") == "confirm_superseded"

    # the SECOND (live) confirmation is untouched — only the orphan got closed
    p = confirm.pending().get("agenda")
    assert p and p["trace_id"] == new_tid
    trace.adopt("")


def test_answering_the_same_widget_twice_in_a_row_does_not_close_its_own_live_flow():
    """Sanity: the normal single-ask path (no supersede) must not regress — `request()` with nothing pending
    yet closes nothing."""
    from voice import observer, trace

    trace.adopt("")
    tid = trace.begin("borra toda la agenda", origin="turno")
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})
    assert not [e for e in observer.debug_events(kind="flow") if e.get("trace") == tid]
    trace.adopt("")


def test_an_expired_confirmation_closes_its_flow_and_queues_a_notice(monkeypatch):
    """The 90s TTL sweep must not just vanish the entry: the flow closes (so the master stops showing it as
    active) AND the expiry gets queued so `nucleo/loop.py` can tell the operator (2026-08-16)."""
    from voice import observer, trace

    trace.adopt("")
    tid = trace.begin("borra toda la agenda", origin="turno")
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})
    trace.adopt("")

    confirm._PENDING["agenda"]["ts"] -= (confirm._TTL + 1)   # simulate 90s+ of silence
    confirm._sweep()

    assert "agenda" not in confirm.pending()
    closes = [e for e in observer.debug_events(kind="flow") if e.get("trace") == tid]
    assert closes and closes[-1].get("reason") == "confirm_expired"

    notices = confirm.drain_expired_notices()
    assert len(notices) == 1
    assert notices[0]["widget_id"] == "agenda"
    assert notices[0]["question"] == "¿Vacío la agenda entera?"
    assert confirm.drain_expired_notices() == [], "drain must consume, never re-deliver the same notice twice"


def test_confirm_classify_reply_es_en():
    assert confirm.classify_reply("sí, bórralo") == "yes"
    assert confirm.classify_reply("vale adelante") == "yes"
    assert confirm.classify_reply("no, déjalo") == "no"
    assert confirm.classify_reply("cancela eso") == "no"
    assert confirm.classify_reply("yes do it") == "yes"
    assert confirm.classify_reply("¿qué tiempo hace?") is None     # no es una respuesta sí/no
    # ambiguo "no, mejor sí" → gana el último mencionado
    assert confirm.classify_reply("no mejor si") == "yes"


# ── lifecycle.delete_widget (integración: crea una carpeta de widget temporal y la borra) ─────────────────
def test_delete_widget_removes_folder_and_tombstones(tmp_path, monkeypatch):
    # V2-515: a DELETABLE widget lives in the generated root — a folder inside the repo would now be
    # (correctly) protected as engine source and hidden instead of removed.
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets import paths as _paths
    wid = "tmptest_del_zz"
    folder = os.path.join(_paths.generated_root(), wid)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "manifest.json"), "w") as f:
        json.dump({"id": wid, "title": "Prueba", "whenToUse": "test"}, f)
    with open(os.path.join(folder, "widget.js"), "w") as f:
        f.write("export function render(){}")
    runtime.invalidate()

    written = {}
    emitted = []
    monkeypatch.setattr(lifecycle, "_mem_write", lambda text, importance: written.update(text=text, imp=importance))
    monkeypatch.setattr(lifecycle, "_emit_widget",
                        lambda action, w, src="system": emitted.append((action, w)))   # V2-039: procedencia

    try:
        res = asyncio.run(lifecycle.delete_widget(wid))
        assert res["ok"] is True and res["id"] == wid
        assert not os.path.isdir(folder)                           # carpeta borrada del disco
        assert ("delete", wid) in emitted                          # cierra la tarjeta en el canvas
        assert "DELETED" in written["text"] and wid in written["text"]   # memory tombstone (history)
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        runtime.invalidate()


def test_delete_widget_unknown_is_safe():
    res = asyncio.run(lifecycle.delete_widget("no_existe_xyz"))
    assert res["ok"] is False


# ── code.py: una petición de BORRADO nunca debe CREAR (era el bug) ────────────────────────────────────────
def test_code_delete_never_creates(monkeypatch):
    from nucleo.agentes import code
    from nucleo.dispatch import Task

    # 2026-08-31: resolves against the REAL shipped catalog (the operator's personal meteo widget left it)

    async def _fake_delete(widget_id, src="system"):                                   # V2-039: procedencia
        return {"ok": True, "id": widget_id, "title": widget_id}

    created = {"called": False}

    def _fake_generate(*a, **k):
        created["called"] = True
        return {"ok": True, "id": "basura"}

    monkeypatch.setattr(lifecycle, "delete_widget", _fake_delete)
    from widgets import generator
    monkeypatch.setattr(generator, "generate_widget", _fake_generate)

    task = Task(id="1", request="borra el widget del reloj", kind="code")
    wr = asyncio.run(code.run(task))
    assert wr.ok and wr.meta.get("deleted") is True
    assert created["called"] is False                              # NUNCA se llamó al generador


# ── FlashBrain: las tools de borrado están ofrecidas ──────────────────────────────────────────────────────
def test_router_offers_delete_tools():
    from nucleo.flash.router import TOOLS
    names = {t["function"]["name"] for t in TOOLS}
    assert {"delete_widget", "confirm_widget_delete"} <= names
