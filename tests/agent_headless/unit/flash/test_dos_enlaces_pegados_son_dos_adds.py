"""V2-391 — «UNA data-op por turno» convirtió dos enlaces pegados en una alucinación.

El tope era deliberado y su motivo está medido: el modelo pequeño DUPLICA un `add_meeting` (cita doble) o
ENUMERA acciones ante «muéstrame la agenda» (done/drop/snooze). Las dos siguen bloqueadas.

Lo que no contemplaba es que a veces VARIAS son la petición. Medido en `build-a-video-playlist-from-links`
(2026-08-27 13:36), y la cadena entera empieza ahí:

    tester  Te paso un par de vídeos: …dQw4w9WgXcQ y …9bZkp7q19f0 — móntame una lista con ellos.
    zaelar  Voy a cargar esos dos vídeos en tu lista de YouTube.
    …
    tester  Perfecto, ahora pásala al siguiente, porfa.
    zaelar  Hecho.
    tester  ¿Y qué está sonando ahora?
    zaelar  Ahora está sonando «PSY - GANGNAM STYLE (강남스타일) M/V».

`add` admite un vídeo, así que dos enlaces son dos llamadas, y solo entró la primera (`widget_ops: add: 1`).
El `next` se encontró un solo vídeo, el widget devolvió «No hay más vídeos» y el turno anunció el segundo
igualmente — el título lo sabía por la URL, no por la lista. 1/5 en resultado por una alucinación que empieza
siendo un tope nuestro.

El criterio nuevo es MÁS ESTRECHO que el viejo donde importa: solo se amplía a misma acción con payloads
distintos, y aquí abajo solo llegan las FAST (una acción irreversible es CONFIRM y sigue pidiendo el sí).

La regla vive en `nucleo/flash/data_ops.py` y no en `router_guards` por el trinquete de fichero-dios: lo que
importa es que la decisión sea UNA, no en qué fichero está.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import data_ops as RG


def _op(wid, act, **payload):
    return {"widget_id": wid, "action": act, "payload": payload}


# ── el criterio ─────────────────────────────────────────────────────────────────────────────────────────────

def test_dos_enlaces_DISTINTOS_entran_los_dos():
    """El caso que se rompía: misma acción, payloads distintos."""
    a, b = _op("youtube", "add", url="dQw4w9WgXcQ"), _op("youtube", "add", url="9bZkp7q19f0")
    assert RG.admite_data_op(a, []) is True
    assert RG.admite_data_op(b, [a]) is True


def test_un_duplicado_EXACTO_se_colapsa():
    """La cita doble, que es por lo que existía el tope."""
    a = _op("agenda", "add_meeting", title="dentista", date="2026-09-03")
    assert RG.admite_data_op(dict(a), [a]) is False


def test_otra_ACCION_sobre_el_mismo_widget_no_entra():
    """La enumeración: «muéstrame la agenda» → done/drop/snooze. Solo la primera."""
    a = _op("agenda", "done", item=1)
    assert RG.admite_data_op(_op("agenda", "drop", item=1), [a]) is False


def test_otro_WIDGET_sigue_siendo_otra_cosa():
    """La restricción es por widget: tocar dos widgets distintos no es enumerar sobre uno."""
    a = _op("youtube", "add", url="x")
    assert RG.admite_data_op(_op("musica", "play", query="algo"), [a]) is True


def test_hay_TECHO():
    """Cinco enlaces de una vez es una petición; cincuenta es un modelo roto."""
    ya = [_op("youtube", "add", url=f"v{i}") for i in range(RG.MAX_DATA_OPS)]
    assert RG.admite_data_op(_op("youtube", "add", url="uno-mas"), ya) is False


def test_una_op_SIN_widget_o_SIN_accion_no_entra():
    assert RG.admite_data_op({"action": "add"}, []) is False
    assert RG.admite_data_op({"widget_id": "youtube"}, []) is False


# ── el canal de TEXTO lo ejecuta ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def rail(monkeypatch):
    """El testigo apunta a `brain_action` desde V2-394: `dispatch_tag` se traga el resultado, así que dejó de
    usarse para poder saber si la op ocurrió. Lo que este fichero mide —cuántas entran y cuáles— no cambia."""
    despachadas = []

    async def _brain_action(wid, act, payload):
        despachadas.append({"id": wid, "data": {"action": act, "payload": payload}})
        return {"ok": True}

    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    from widgets import actions as _wa
    monkeypatch.setattr("nucleo.flash.frontend.action_mode", lambda wid, act: _wa.FAST)
    return despachadas


def _llamadas(*ops):
    return [{"name": "widget_data", "args": o} for o in ops]


def test_el_canal_de_texto_despacha_los_DOS_enlaces(rail):
    from nucleo.flash import widget_data_turn as WDT
    parte = asyncio.run(WDT.execute(_llamadas(_op("youtube", "add", url="dQw4w9WgXcQ"),
                                              _op("youtube", "add", url="9bZkp7q19f0"))))
    assert len(rail) == 2, "dos enlaces pegados son dos adds"
    assert [d["data"]["payload"]["url"] for d in rail] == ["dQw4w9WgXcQ", "9bZkp7q19f0"]
    assert parte["executed"] == "widget_data" and len(parte["ops"]) == 2


def test_lo_DESCARTADO_se_dice(rail):
    """Un parte que solo cuenta lo que salió bien es cómo sobrevive un «Hecho.» que no lo es."""
    from nucleo.flash import widget_data_turn as WDT
    dup = _op("agenda", "add_meeting", title="dentista")
    parte = asyncio.run(WDT.execute(_llamadas(dup, dict(dup))))
    assert len(rail) == 1
    assert parte["descartadas"] == 1


def test_una_accion_que_pide_PERMISO_sigue_sin_ejecutarse(monkeypatch, rail):
    """La frontera que NO se mueve: lo irreversible es CONFIRM y sigue necesitando el sí del operador."""
    from widgets import actions as _wa

    from nucleo.flash import widget_data_turn as WDT
    monkeypatch.setattr("nucleo.flash.frontend.action_mode", lambda wid, act: _wa.CONFIRM)
    parte = asyncio.run(WDT.execute(_llamadas(_op("agenda", "borrar_todo"))))
    assert rail == []
    assert parte["executed"] == "widget_data_skipped"


def test_el_parte_conserva_la_forma_singular_de_antes(rail):
    """`widget`/`act` los leen el informe y los guardas anteriores: cambiarlos por una lista rompería la
    lectura sin avisar."""
    from nucleo.flash import widget_data_turn as WDT
    parte = asyncio.run(WDT.execute(_llamadas(_op("youtube", "add", url="x"))))
    assert parte["widget"] == "youtube" and parte["act"] == "add"


# ── y la VOZ usa el MISMO criterio ──────────────────────────────────────────────────────────────────────────

def test_la_voz_decide_con_el_MISMO_guarda():
    """Si cada canal se trae el suyo, divergen — que es cómo esta clase de fallo sobrevive (V2-176)."""
    from pathlib import Path
    src = Path("voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "_data_ops.admite_data_op(args, _data_ops_hechas)" in src
    assert '"widget_data" in _tool_fired:\n                    return' not in src
