"""Un worker MIRANDO EL MENÚ no es un worker que se ha estrellado.

Medido el 2026-08-28 en `weekend-plan-barcelona__es`: la ronda se archivó con dos anomalías `error_interno`
y el juez escribió que «el worker falló técnicamente al extraer el precio». Lo que el worker había hecho de
verdad era lanzar `nav_cli` y `worker_bridge` SIN subcomando — argparse contesta con un bloque `usage:` y
**código 2**, así que una sonda de descubrimiento nos llega vestida exactamente igual que una caída. Dos de
los cuatro fallos marcados de aquella ronda eran el modelo leyendo el menú, y la nota de mecanismo lo pagó.

Es el instrumento acusando al producto, que es el único error que una herramienta de medida no puede
permitirse: un fallo falso manda a un agente a arreglar algo que nunca pasó, y cuesta más que el defecto.

La regla —y por qué ésta y no «el código 2 da igual»— es que **el argumento que falta sea `cmd` mismo**:
entonces nadie eligió subcomando y alguien está leyendo la carta. Un argumento mal en un subcomando REAL
(`nav_cli click` sin ref) también dice «arguments are required» y también sale con 2, y ése SÍ es una llamada
rota: se hizo un pedido y no se pudo servir.
"""
from __future__ import annotations

from nucleo.workers.probes import is_menu_probe

_BARE_NAV = ("usage: nav_cli [-h] {snapshot,look,navigate,open,goto,click,type,select_option,click_at,"
             "type_at,scroll,press,extract,visit} ... nav_cli: error: the following arguments are required: cmd")
_BARE_BRIDGE = ("usage: worker_bridge [-h] {ask,wait,act,say} ... worker_bridge: error: the following "
                "arguments are required: cmd")


def test_las_dos_sondas_reales_de_la_ronda():
    """Copiadas literalmente del log de `weekend-plan-barcelona__es`, no reescritas a mano."""
    assert is_menu_probe(_BARE_NAV)
    assert is_menu_probe(_BARE_BRIDGE)


def test_una_llamada_rota_de_verdad_sigue_siendo_un_error():
    """La mitad de sensibilidad, y la que importa: se hizo un pedido y no se pudo servir."""
    roto = ("usage: nav_cli click [-h] ref ... nav_cli click: error: the following arguments are "
            "required: ref")
    assert not is_menu_probe(roto)


def test_una_cli_ajena_no_es_asunto_nuestro():
    """De un `usage:` de otro binario no sabemos nada, y adivinar sería inventarse una medición."""
    assert not is_menu_probe("usage: ffmpeg [-h] ... error: the following arguments are required: cmd")


def test_un_error_normal_no_se_ablanda():
    for txt in ("Traceback (most recent call last): ConnectionRefusedError",
                "Exit code 1 · timeout after 30s", "", "usage: nav_cli [-h] {snapshot}"):
        assert not is_menu_probe(txt), txt


def test_el_emisor_deja_de_marcarlo_como_error(monkeypatch):
    """La fontanería: sin esto la clasificación existe y nadie la usa.

    El emisor es lo que alimenta `is_error`, y de ahí salen las anomalías del auditor, el contador de errores
    del span y lo que el juez lee. Un solo punto, a propósito.
    """
    from nucleo.workers import session as S

    vistos: list[dict] = []

    class _Rec:
        task_id = "1"

    class _Falso:
        _rec = _Rec()

    import voice.observer as OBS
    monkeypatch.setattr(OBS, "emit",
                        lambda kind, label, text="", role="", extra=None: vistos.append(
                            {"label": label, "is_error": (extra or {}).get("is_error")}))

    S.WorkerSession._emit_step_result(_Falso(), {"text": _BARE_NAV, "is_error": True, "where": "web"})
    S.WorkerSession._emit_step_result(_Falso(), {"text": "Traceback: boom", "is_error": True, "where": "web"})

    assert vistos[0]["is_error"] is False and "⚠️" not in vistos[0]["label"], "la sonda no es una avería"
    assert vistos[1]["is_error"] is True and "⚠️" in vistos[1]["label"], "y una avería lo sigue siendo"
