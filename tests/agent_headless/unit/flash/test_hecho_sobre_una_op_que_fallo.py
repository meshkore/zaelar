"""V2-394 — “Hecho.” for a data-op that the widget REJECTED.

`widget_data_turn` dispatched through `dispatch_tag`, which **swallows the result and returns `None`** — so the
turn could not tell whether the operation had occurred, and the voice said `data_ack` (“Hecho.”) regardless of
what happened. This is the GENERAL case of what V2-380 (music) and V2-383 (video) closed separately, and the
reason has been written word for word in the docstring of `video_turn.execute` since that same day.

Measured in `build-a-video-playlist-from-links` (2026-08-27 14:09), using the evidence V2-390 had just
added — without it, this could not even be seen:

    [action       ] youtube.load  ok
    [action_failed] youtube.load  no_video      «No encontré ese vídeo.»
    [action       ] youtube.load  ok
    [action       ] youtube.next  ok
    [action_failed] youtube.next  end_of_list   «No hay más vídeos en la lista.»

Two operations failed and the turn said “Hecho.” for both. Verdict: score **2/5**, “falsifies the
state of the playback queue… preventing the user from knowing that the list is broken.” Sixth time that one of
OUR canned phrases is the one lying (V2-176, V2-209, V2-377, V2-380, V2-383).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nucleo.flash import widget_data_turn as WDT


def _op(wid, act, **payload):
    return {"name": "widget_data", "args": {"widget_id": wid, "action": act, "payload": payload}}


@pytest.fixture
def rail(monkeypatch):
    """Replace the rail with a witness that can SAY NO — which is what did not get through before."""
    visto = {"ops": [], "respuestas": {}}

    async def _brain_action(wid, act, payload):
        visto["ops"].append((wid, act, payload))
        return visto["respuestas"].get(act, {"ok": True})

    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    from widgets import actions as _wa
    monkeypatch.setattr("nucleo.flash.frontend.action_mode", lambda wid, act: _wa.FAST)
    return visto


# ── the turn FINDS OUT ──────────────────────────────────────────────────────────────────────────────────────

def test_el_rail_devuelve_el_resultado_y_ya_no_se_pierde(rail):
    """The guard that would have sufficed: `dispatch_tag` returns None by contract, so with it the question
    “did it happen?” had no possible answer."""
    rail["respuestas"]["next"] = {"ok": False, "error": "end_of_list",
                                  "message": "No hay más vídeos en la lista."}
    parte = asyncio.run(WDT.execute([_op("youtube", "next")]))
    assert parte["executed"] == "widget_data_failed"
    assert "No hay más vídeos" in parte["message"]


def test_se_usa_brain_action_y_NO_dispatch_tag():
    """A source guard because it is the entire defect in one line: switching back to `dispatch_tag` reopens the hole
    without anything failing — it would return None and everything would look “fine”."""
    import ast
    arbol = ast.parse(Path("nucleo/flash/widget_data_turn.py").read_text(encoding="utf-8"))
    # The two forms: `_w.dispatch_tag(...)` is an Attribute and `_brain_action(...)`, imported with an alias, is a
    # Name. Collecting only one leaves the guard looking at half the picture — and it failed for that very reason when written.
    llamadas = {n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
                for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, (ast.Attribute, ast.Name))}
    # ⚠️ About CALLS, not text: the module comment NAMES `dispatch_tag` to explain why it is not used, so a
    # substring guard fails while reading its own explanation. Third time today with this trap
    # (V2-380 `extract=None`, V2-392 `active_when`).
    assert "dispatch_tag" not in llamadas, "se traga el resultado: con él no se puede saber si ocurrió"
    assert "_brain_action" in llamadas or "brain_action" in llamadas


def test_una_op_que_SALE_BIEN_sigue_saliendo_bien(rail):
    parte = asyncio.run(WDT.execute([_op("youtube", "add", url="x")]))
    assert parte["executed"] == "widget_data" and parte["ops"] == [{"widget": "youtube", "act": "add"}]
    assert "fallidas" not in parte


def test_una_BUENA_y_una_MALA_en_el_MISMO_turno_conserva_las_dos(rail):
    """Keeping the successful one is how a half-“Hecho.” gets through completely — and it is the REAL case from the run:
    two pasted links, one loaded and the other returned `no_video`.

    ⚠️ Initially written as TWO separate executions, the teardown (“do not record the failures”) took effect and did NOT
    bite: this never produces a part with both success AND failure inside, which is exactly what the guard claims to measure.
    """
    llamadas = {"n": 0}

    async def _brain_action(wid, act, payload):
        llamadas["n"] += 1
        if llamadas["n"] == 2:                      # the SECOND link is the one that does not exist
            return {"ok": False, "error": "no_video", "message": "No encontré ese vídeo."}
        return {"ok": True}

    import widgets.server_api as _sa
    _sa.brain_action = _brain_action
    parte = asyncio.run(WDT.execute([_op("youtube", "add", url="dQw4w9WgXcQ"),
                                     _op("youtube", "add", url="9bZkp7q19f0")]))
    assert parte["executed"] == "widget_data"           # one DID get through
    assert len(parte["ops"]) == 1
    assert parte["fallidas"] and "No encontré" in parte["fallidas"][0]["message"]


# ── and the VOICE says it ───────────────────────────────────────────────────────────────────────────────────

def _boca(parte):
    """The REAL decision, not a copy (V2-199)."""
    return WDT.spoken_for(parte, "Hecho.")


def test_si_FALLO_no_se_dice_Hecho():
    salida = _boca({"executed": "widget_data_failed", "message": "No hay más vídeos en la lista."})
    assert salida.startswith("No he podido")
    assert "Hecho." not in salida
    assert "No hay más vídeos" in salida


def test_un_fallo_SIN_motivo_no_se_queda_mudo():
    assert "el widget no lo aceptó" in _boca({"executed": "widget_data_failed"})


def test_si_una_de_dos_fallo_se_DICE_aunque_la_otra_saliera(): 
    salida = _boca({"executed": "widget_data", "ops": [{"widget": "youtube", "act": "add"}],
                    "fallidas": [{"message": "No encontré ese vídeo."}]})
    assert "pero una no" in salida and "No encontré" in salida


def test_una_data_op_LIMPIA_conserva_su_ack():
    """The other direction: without this, fixing the lie leaves the turn unable to say that it did do it."""
    assert _boca({"executed": "widget_data", "ops": [{"widget": "agenda", "act": "add_meeting"}]}) == "Hecho."


def test_un_turno_que_NO_es_data_op_conserva_su_ack():
    assert _boca({"executed": "play_video", "ok": True}) == "Hecho."


# ── the wiring ─────────────────────────────────────────────────────────────────────────────────────────────

def test_la_boca_del_fallo_va_ANTES_del_ack_generico():
    """`widget_data` falls into a branch that always says “Hecho.”; if the new one comes afterward, it is never reached."""
    src = Path("nucleo/flash/probe.py").read_text(encoding="utf-8")
    i_fallo = src.index('elif action == "widget_data" and isinstance(return_extra_exec, dict)')
    i_ack = src.index('elif action in ("widget_data", "confirm_task_no"):')
    assert i_fallo < i_ack


# ── V2-463 — the item reference TRAVELS through the text channel ─────────────────────────────────────────
def test_el_item_de_la_tool_llega_al_widget(monkeypatch):
    """The tool declares `item` as its own argument and this path was THROWING it away: it only passed `payload`, so
    “ponme la 1, la del Spider” reached the viewer as a select with no item — three failures measured in one run,
    with the model additionally saying “te la dejo puesta”."""
    import asyncio
    visto = {}

    async def _brain_action(wid, action, payload):
        visto.update({"wid": wid, "action": action, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)
    from nucleo.flash import widget_data_turn as W
    asyncio.run(W.execute([{"name": "widget_data",
                            "args": {"widget_id": "imagenes", "action": "select",
                                     "item": "la 1, la del Spider"}}]))
    assert visto.get("action") == "select"
    # Resolved by `refs` to a real id if there are items on screen; otherwise the raw text travels in the id
    # field — what must NOT happen is for the widget to receive an empty select.
    assert any(str(v).strip() for k, v in (visto.get("payload") or {}).items()), visto


# ── V2-467 — the reference lands where the MANIFEST says, not in an invented key ─────────────────────────
def test_la_referencia_aterriza_en_la_clave_que_el_widget_LEE(monkeypatch):
    """Measured defect (2026-08-28, `build-a-video-playlist-from-links`): the operator pasted two YouTube
    links, the model called `add` with the reference, and the payload came out as `{"item": "<enlaces>"}` — but
    `youtube.add` reads `url`, so it replied “dime qué vídeo añado” with both links in front of it. With
    `imagenes.select` it had not been seen because its key is, precisely, called `item`.
    """
    import asyncio
    visto = {}

    async def _brain_action(wid, action, payload):
        visto.update({"wid": wid, "action": action, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)
    from nucleo.flash import widget_data_turn as W
    enlaces = "https://www.youtube.com/watch?v=dQw4w9WgXcQ y https://youtu.be/9bZkp7q19f0"
    asyncio.run(W.execute([{"name": "widget_data",
                            "args": {"widget_id": "youtube", "action": "add", "item": enlaces}}]))
    assert visto["payload"].get("url") == enlaces, f"cayó en la clave equivocada: {visto['payload']}"
    assert "item" not in visto["payload"], "«item» no existe para esta acción — el widget no lo lee"


def test_la_clave_se_LEE_del_manifest_y_no_de_una_tabla():
    """Data-driven on purpose: the alternative was a table per widget, which is exactly what this tree does not
    want. The first payload key is, by convention across all manifests, the primary data."""
    from nucleo.flash.widget_data_turn import _primera_clave
    assert _primera_clave("youtube", "add") == "url"
    assert _primera_clave("imagenes", "select") == "item"
    assert _primera_clave("musica", "add_to_playlist") == "playlist"
    assert _primera_clave("noexiste", "nada") == ""


def test_un_payload_que_YA_trae_el_dato_no_se_pisa(monkeypatch):
    """The other half of the safeguard: if the model populated the payload correctly, the reference cannot overwrite it."""
    import asyncio
    visto = {}

    async def _brain_action(wid, action, payload):
        visto.update(payload)
        return {"ok": True}

    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)
    from nucleo.flash import widget_data_turn as W
    asyncio.run(W.execute([{"name": "widget_data",
                            "args": {"widget_id": "youtube", "action": "add",
                                     "item": "algo suelto", "payload": {"url": "https://youtu.be/ok"}}}]))
    assert visto.get("url") == "https://youtu.be/ok"


# ── V2-467 — the card opens where the data lands, including the generic case ─────────────────────────────
def test_una_data_op_que_ESCRIBE_abre_su_tarjeta(monkeypatch):
    """Measured in `build-a-video-playlist-from-links`: the model executed `name_list` and the report marked
    “WRITTEN BUT NEVER OPENED” — the operator saw nothing, so “done” was invisible. It is the same
    decision as V2-463 (the media rails already had it), applied to the general case: a data-op that writes
    is exactly what the frontend already uses to repaint an open card."""
    import asyncio
    emitted: list[tuple] = []

    async def _brain_action(wid, action, payload):
        return {"ok": True}

    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        emitted.append((kind, label, (extra or {}).get("id"))))
    from nucleo.flash import widget_data_turn as W
    asyncio.run(W.execute([{"name": "widget_data",
                            "args": {"widget_id": "youtube", "action": "name_list",
                                     "payload": {"name": "la de la tarde"}}}]))
    assert ("widget", "show", "youtube") in emitted


def test_una_op_que_el_widget_RECHAZA_no_abre_nada(monkeypatch):
    """The other half of the safeguard: opening a card for a change that did not occur is showing a box that
    contradicts what was just said."""
    import asyncio
    emitted: list[tuple] = []

    async def _brain_action(wid, action, payload):
        return {"ok": False, "error": "no lo acepto"}

    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        emitted.append((kind, label, (extra or {}).get("id"))))
    from nucleo.flash import widget_data_turn as W
    asyncio.run(W.execute([{"name": "widget_data",
                            "args": {"widget_id": "youtube", "action": "name_list"}}]))
    assert not [e for e in emitted if e[1] == "show"]
