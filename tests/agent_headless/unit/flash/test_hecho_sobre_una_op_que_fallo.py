"""V2-394 — «Hecho.» sobre una data-op que el widget RECHAZÓ.

`widget_data_turn` despachaba por `dispatch_tag`, que **se traga el resultado y devuelve `None`** — así que el
turno no podía saber si la operación había ocurrido, y la boca decía `data_ack` («Hecho.») pasara lo que
pasara. Es el caso GENERAL de lo que V2-380 (música) y V2-383 (vídeo) cerraron por separado, y la razón está
escrita palabra por palabra en el docstring de `video_turn.execute` desde ese mismo día.

Medido en `build-a-video-playlist-from-links` (2026-08-27 14:09), con la evidencia que V2-390 acababa de
añadir — sin ella esto no se podía ni ver:

    [action       ] youtube.load  ok
    [action_failed] youtube.load  no_video      «No encontré ese vídeo.»
    [action       ] youtube.load  ok
    [action       ] youtube.next  ok
    [action_failed] youtube.next  end_of_list   «No hay más vídeos en la lista.»

Dos operaciones fallaron y el turno dijo «Hecho.» a las dos. Veredicto: resultado **2/5**, «falsifica el
estado de la cola de reproducción… impidiendo que el usuario sepa que la lista está rota». Sexta vez que una
frase enlatada NUESTRA es la que miente (V2-176, V2-209, V2-377, V2-380, V2-383).
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
    """Sustituye el rail por un testigo que puede DECIR QUE NO — que es lo que antes no llegaba."""
    visto = {"ops": [], "respuestas": {}}

    async def _brain_action(wid, act, payload):
        visto["ops"].append((wid, act, payload))
        return visto["respuestas"].get(act, {"ok": True})

    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    from widgets import actions as _wa
    monkeypatch.setattr("nucleo.flash.frontend.action_mode", lambda wid, act: _wa.FAST)
    return visto


# ── el turno se ENTERA ──────────────────────────────────────────────────────────────────────────────────────

def test_el_rail_devuelve_el_resultado_y_ya_no_se_pierde(rail):
    """El guarda que habría bastado: `dispatch_tag` devuelve None por contrato, así que con él la pregunta
    «¿ocurrió?» no tenía respuesta posible."""
    rail["respuestas"]["next"] = {"ok": False, "error": "end_of_list",
                                  "message": "No hay más vídeos en la lista."}
    parte = asyncio.run(WDT.execute([_op("youtube", "next")]))
    assert parte["executed"] == "widget_data_failed"
    assert "No hay más vídeos" in parte["message"]


def test_se_usa_brain_action_y_NO_dispatch_tag():
    """Una guarda de fuente porque es la línea entera del defecto: volver a `dispatch_tag` reabre el agujero
    sin que falle nada — devolvería None y todo saldría «bien»."""
    import ast
    arbol = ast.parse(Path("nucleo/flash/widget_data_turn.py").read_text(encoding="utf-8"))
    # Las dos formas: `_w.dispatch_tag(...)` es un Attribute y `_brain_action(...)`, importado con alias, es un
    # Name. Recoger solo una deja el guarda mirando a medias — y salió rojo por eso mismo al escribirlo.
    llamadas = {n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
                for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, (ast.Attribute, ast.Name))}
    # ⚠️ Sobre las LLAMADAS, no sobre el texto: el comentario del módulo NOMBRA `dispatch_tag` para explicar por
    # qué no se usa, así que un guarda por substring sale rojo leyendo su propia explicación. Tercera vez hoy con
    # esta trampa (V2-380 `extract=None`, V2-392 `active_when`).
    assert "dispatch_tag" not in llamadas, "se traga el resultado: con él no se puede saber si ocurrió"
    assert "_brain_action" in llamadas or "brain_action" in llamadas


def test_una_op_que_SALE_BIEN_sigue_saliendo_bien(rail):
    parte = asyncio.run(WDT.execute([_op("youtube", "add", url="x")]))
    assert parte["executed"] == "widget_data" and parte["ops"] == [{"widget": "youtube", "act": "add"}]
    assert "fallidas" not in parte


def test_una_BUENA_y_una_MALA_en_el_MISMO_turno_conserva_las_dos(rail):
    """Quedarse con la buena es cómo un «Hecho.» a medias pasa por completo — y es el caso REAL de la ronda:
    dos enlaces pegados, uno cargó y el otro devolvió `no_video`.

    ⚠️ Escrito primero como DOS ejecuciones separadas, el desarme («no apuntes las fallidas») se aplicó y NO
    mordió: así nunca se produce una parte con éxito Y fallo dentro, que es justo lo que el guarda dice medir.
    """
    llamadas = {"n": 0}

    async def _brain_action(wid, act, payload):
        llamadas["n"] += 1
        if llamadas["n"] == 2:                      # el SEGUNDO enlace es el que no existe
            return {"ok": False, "error": "no_video", "message": "No encontré ese vídeo."}
        return {"ok": True}

    import widgets.server_api as _sa
    _sa.brain_action = _brain_action
    parte = asyncio.run(WDT.execute([_op("youtube", "add", url="dQw4w9WgXcQ"),
                                     _op("youtube", "add", url="9bZkp7q19f0")]))
    assert parte["executed"] == "widget_data"           # una SÍ entró
    assert len(parte["ops"]) == 1
    assert parte["fallidas"] and "No encontré" in parte["fallidas"][0]["message"]


# ── y la BOCA lo dice ───────────────────────────────────────────────────────────────────────────────────────

def _boca(parte):
    """La decisión REAL, no una copia (V2-199)."""
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
    """La otra dirección: sin esto, arreglar la mentira deja al turno sin poder decir que sí lo hizo."""
    assert _boca({"executed": "widget_data", "ops": [{"widget": "agenda", "act": "add_meeting"}]}) == "Hecho."


def test_un_turno_que_NO_es_data_op_conserva_su_ack():
    assert _boca({"executed": "play_video", "ok": True}) == "Hecho."


# ── el cableado ─────────────────────────────────────────────────────────────────────────────────────────────

def test_la_boca_del_fallo_va_ANTES_del_ack_generico():
    """`widget_data` cae en una rama que dice «Hecho.» siempre; si la nueva va detrás, no se alcanza nunca."""
    src = Path("nucleo/flash/probe.py").read_text(encoding="utf-8")
    i_fallo = src.index('elif action == "widget_data" and isinstance(return_extra_exec, dict)')
    i_ack = src.index('elif action in ("widget_data", "confirm_task_no"):')
    assert i_fallo < i_ack


# ── V2-463 — la referencia al item VIAJA por el canal de texto ──────────────────────────────────────────
def test_el_item_de_la_tool_llega_al_widget(monkeypatch):
    """La tool declara `item` como argumento propio y este camino lo TIRABA: solo pasaba `payload`, así que
    «ponme la 1, la del Spider» llegaba al visor como un select sin item — tres fallos medidos en una ronda,
    con el modelo diciendo «te la dejo puesta» encima."""
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
    # Resuelto por `refs` a un id real si hay items en pantalla; si no, el texto crudo viaja en el campo
    # del id — lo que NO puede pasar es que el widget reciba un select vacío.
    assert any(str(v).strip() for k, v in (visto.get("payload") or {}).items()), visto


# ── V2-467 — la referencia cae donde el MANIFEST dice, no en una clave inventada ────────────────────────
def test_la_referencia_aterriza_en_la_clave_que_el_widget_LEE(monkeypatch):
    """Defecto medido (2026-08-28, `build-a-video-playlist-from-links`): el operador pegó dos enlaces de
    YouTube, el modelo llamó a `add` con la referencia y el payload salió `{"item": "<enlaces>"}` — pero
    `youtube.add` lee `url`, así que contestó «dime qué vídeo añado» con los dos enlaces delante. Con
    `imagenes.select` no se había visto porque su clave se llama, justamente, `item`.
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
    """Data-driven a propósito: la alternativa era una tabla por widget, que es justo lo que este árbol no
    quiere. La primera clave del payload es, por convención de todos los manifests, el dato principal."""
    from nucleo.flash.widget_data_turn import _primera_clave
    assert _primera_clave("youtube", "add") == "url"
    assert _primera_clave("imagenes", "select") == "item"
    assert _primera_clave("musica", "add_to_playlist") == "playlist"
    assert _primera_clave("noexiste", "nada") == ""


def test_un_payload_que_YA_trae_el_dato_no_se_pisa(monkeypatch):
    """La mitad de sensibilidad: si el modelo puso bien el payload, la referencia no puede sobrescribirlo."""
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
