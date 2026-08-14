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
def test_delete_widget_removes_folder_and_tombstones(monkeypatch):
    wid = "tmptest_del_zz"
    folder = os.path.join(lifecycle.HERE, wid)
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

    monkeypatch.setattr(code, "_catalog_ids", lambda: ["meteo-tarragona"])

    async def _fake_delete(widget_id, src="system"):                                   # V2-039: procedencia
        return {"ok": True, "id": widget_id, "title": widget_id}

    created = {"called": False}

    def _fake_generate(*a, **k):
        created["called"] = True
        return {"ok": True, "id": "basura"}

    monkeypatch.setattr(lifecycle, "delete_widget", _fake_delete)
    from widgets import generator
    monkeypatch.setattr(generator, "generate_widget", _fake_generate)

    task = Task(id="1", request="borra el widget de meteo-tarragona", kind="code")
    wr = asyncio.run(code.run(task))
    assert wr.ok and wr.meta.get("deleted") is True
    assert created["called"] is False                              # NUNCA se llamó al generador


# ── FlashBrain: las tools de borrado están ofrecidas ──────────────────────────────────────────────────────
def test_router_offers_delete_tools():
    from nucleo.flash.router import TOOLS
    names = {t["function"]["name"] for t in TOOLS}
    assert {"delete_widget", "confirm_widget_delete"} <= names
