"""When the permission gate rejects a command, the trace stored the reason and NOT what was attempted.

“Contains simple_expansion,” “Contains brace with quote character,” “uses the `&` background operator,” “cd
in '…' was blocked”—four different rejections on the night of 2026-08-28, and in all four the event said which
rule had been broken **and nothing about the command**. From the outside, that does not distinguish the two causes,
which call for opposite actions:

  · the worker wrote something strange on its own → it is behavior, and it is measured;
  · **our own prompt taught it to do so** → it is our fault, and it must be fixed in the prompt.

Two of the four were the latter (the `&` that the rule did not list, and the `cd` whose false premise came from
the command we taught it), and finding that out required reconstructing it by hand each time, reading session logs
and guessing. The system had the command right there in the `tool_use` and discarded it when pairing it with its result.

It is emitted only when the step FAILS: the command from a successful step is noise, and a row that always succeeds
stops being examined.
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
    """The sensitivity half: a row that always succeeds stops being examined, and the command from a healthy step is
    noise in an already dense flow."""
    v = _emitido(monkeypatch, {"text": "8 resultados", "is_error": False, "where": "web",
                               "tool": "Bash", "cmd": "python -m nucleo.nav_cli extract"})
    assert "cmd" not in v["extra"]


def test_sin_comando_no_se_inventa_un_campo_vacio(monkeypatch):
    """A `cmd: ""` in the flow reads as “nothing was attempted,” which is different from “we do not know.”"""
    v = _emitido(monkeypatch, {"text": "Traceback…", "is_error": True, "where": "web", "tool": "WebSearch"})
    assert "cmd" not in v["extra"]


def test_el_comando_va_acotado(monkeypatch):
    v = _emitido(monkeypatch, {"text": "Contains brace with quote character", "is_error": True,
                               "where": "sistema", "tool": "Bash", "cmd": "x" * 900})
    assert 0 < len(v["extra"]["cmd"]) <= 220


def test_la_sesion_GUARDA_el_comando_al_casar_el_paso_con_su_resultado():
    """The plumbing: if `claude_session` does not put it in the step's metadata, nothing ever gets here."""
    from pathlib import Path
    src = Path("nucleo/workers/claude_session.py").read_text(encoding="utf-8")
    assert '"cmd": str((tin or {}).get("command") or "")[:220]' in src, "el paso no guarda su comando"
    assert 'cmd=meta.get("cmd", "")' in src, "el resultado no recupera el comando de su paso"


def test_y_la_ANOMALIA_del_informe_lo_enseña():
    """Half the job, and the missing half was the reader's.

    The command reached the raw event, and the anomaly—which is what appears in the report and what the person who
    will fix it reads—was still saying only the broken rule. Measured on 2026-08-28, with the engine already storing it:
    `search-buy-bicycle__us` once again published “Contains simple_expansion” and nothing else.
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
    """A suffix that always appears stops being read, and “what was attempted: ``” says nothing."""
    import json
    from tests.use_cases.e2e.agent import verify as V
    ev = {"kind": "task", "cat": "worker",
          "payload": json.dumps({"kind": "task", "cat": "worker", "label": "· paso ⚠️ error",
                                 "text": "Traceback…", "is_error": True, "rel_ms": 1000, "span": "worker:1"})}
    interno = [a for a in V.audit([ev])["anomalies"] if a["clase"] == "error_interno"]
    assert interno and "lo que se intentó" not in interno[0]["que"]
