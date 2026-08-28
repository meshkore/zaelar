"""Cuando la puerta de permisos rechaza un comando, el rastro guardaba el motivo y NO lo que se intentó.

«Contains simple_expansion», «Contains brace with quote character», «uses the `&` background operator», «cd
in '…' was blocked» — cuatro rechazos distintos la noche del 2026-08-28, y en los cuatro el evento decía qué
regla se había roto **y nada del comando**. Desde fuera eso no distingue las dos causas, que piden acciones
opuestas:

  · el worker escribió algo raro por su cuenta → es conducta, y se mide;
  · **nuestro propio prompt se lo enseñó** → es culpa nuestra, y se arregla en el prompt.

Dos de las cuatro eran lo segundo (el `&` que la regla no listaba, el `cd` cuya premisa falsa venía del
comando que le enseñamos), y para averiguarlo hubo que reconstruirlo a mano cada vez, leyendo logs de sesión
y adivinando. El sistema tenía el comando delante en el `tool_use` y lo tiraba al casarlo con su resultado.

Solo se emite cuando el paso FALLA: el comando de un paso que sale bien es ruido, y una fila que sale siempre
deja de mirarse.
"""
from __future__ import annotations


class _Rec:
    task_id = "1"


class _Falso:
    _rec = _Rec()


def _emitido(monkeypatch, d: dict) -> dict:
    from nucleo.workers import session as S
    import voice.observer as OBS
    visto: dict = {}
    monkeypatch.setattr(OBS, "emit",
                        lambda kind, label, text="", role="", extra=None: visto.update(
                            {"label": label, "extra": dict(extra or {})}))
    S.WorkerSession._emit_step_result(_Falso(), d)
    return visto


def test_un_rechazo_dice_QUE_se_intento(monkeypatch):
    v = _emitido(monkeypatch, {"text": "Contains simple_expansion", "is_error": True, "where": "web",
                               "tool": "Bash", "cmd": "python -m nucleo.nav_cli extract $(cat q.txt)"})
    assert v["extra"]["cmd"] == "python -m nucleo.nav_cli extract $(cat q.txt)"
    assert v["extra"]["is_error"] is True


def test_un_paso_que_sale_BIEN_no_arrastra_su_comando(monkeypatch):
    """La mitad de sensibilidad: una fila que sale siempre deja de mirarse, y el comando de un paso sano es
    ruido en un flujo que ya es denso."""
    v = _emitido(monkeypatch, {"text": "8 resultados", "is_error": False, "where": "web",
                               "tool": "Bash", "cmd": "python -m nucleo.nav_cli extract"})
    assert "cmd" not in v["extra"]


def test_sin_comando_no_se_inventa_un_campo_vacio(monkeypatch):
    """Un `cmd: ""` en el flujo se lee como «se intentó nada», que es otra cosa que «no lo sabemos»."""
    v = _emitido(monkeypatch, {"text": "Traceback…", "is_error": True, "where": "web", "tool": "WebSearch"})
    assert "cmd" not in v["extra"]


def test_el_comando_va_acotado(monkeypatch):
    v = _emitido(monkeypatch, {"text": "Contains brace with quote character", "is_error": True,
                               "where": "sistema", "tool": "Bash", "cmd": "x" * 900})
    assert 0 < len(v["extra"]["cmd"]) <= 220


def test_la_sesion_GUARDA_el_comando_al_casar_el_paso_con_su_resultado():
    """La fontanería: si `claude_session` no lo mete en el meta del paso, aquí nunca llega nada."""
    from pathlib import Path
    src = Path("nucleo/workers/claude_session.py").read_text(encoding="utf-8")
    assert '"cmd": str((tin or {}).get("command") or "")[:220]' in src, "el paso no guarda su comando"
    assert 'cmd=meta.get("cmd", "")' in src, "el resultado no recupera el comando de su paso"


def test_y_la_ANOMALIA_del_informe_lo_enseña():
    """Media faena, y la mitad que faltaba era la del lector.

    El comando llegaba al evento crudo y la anomalía —que es lo que aparece en el informe y lo que lee quien
    va a arreglarlo— seguía diciendo solo la regla rota. Medido el 2026-08-28, con el motor ya guardándolo:
    `search-buy-bicycle__us` publicó «Contains simple_expansion» a secas otra vez.
    """
    import json
    from tests.use_cases.e2e.agent import verify as V
    ev = {"kind": "task", "cat": "worker",
          "payload": json.dumps({"kind": "task", "cat": "worker", "label": "· paso ⚠️ error",
                                 "text": "Contains simple_expansion", "is_error": True, "rel_ms": 1000,
                                 "span": "worker:1", "cmd": "python -m nucleo.nav_cli extract $(cat q.txt)"})}
    anomalias = V.audit([ev])["anomalies"]
    interno = [a for a in anomalias if a["clase"] == "error_interno"]
    assert interno and "lo que se intentó" in interno[0]["que"]
    assert "$(cat q.txt)" in interno[0]["que"]


def test_y_sin_comando_la_anomalia_no_arrastra_una_coletilla_vacia():
    """Una coletilla que sale siempre deja de leerse, y «lo que se intentó: ``» no dice nada."""
    import json
    from tests.use_cases.e2e.agent import verify as V
    ev = {"kind": "task", "cat": "worker",
          "payload": json.dumps({"kind": "task", "cat": "worker", "label": "· paso ⚠️ error",
                                 "text": "Traceback…", "is_error": True, "rel_ms": 1000, "span": "worker:1"})}
    interno = [a for a in V.audit([ev])["anomalies"] if a["clase"] == "error_interno"]
    assert interno and "lo que se intentó" not in interno[0]["que"]
