"""Una acción que el turno DECIDIÓ y el sistema tiró tiene que llegar al juez.

Es la diferencia entre los dos diagnósticos que desde un transcript se ven idénticos: «el agente no lo
intentó» y «el agente lo intentó y le tiraron la acción». Equivocarse costó tres días — V2-133 abrió ocho
casos de «zaelar narra un progreso que no ocurre» cuando el FlashBrain SÍ había llamado a
`escalate_to_slowbrain` y sus argumentos llegaron cortados (V2-171). Un juez que no puede ver esto no
distingue, así que elige el que se lee peor.

Todos los tests fijan la FORMA REAL del evento, que es donde esto se rompe sin hacer ruido: `observer.emit`
hace `ev.update(extra)`, o sea que `extra` queda APLANADO en el payload, y el payload llega como STRING JSON
desde la API de observabilidad. Un lector que busque `e["extra"]["tool"]` no encuentra nada y reporta «cero
acciones descartadas», que es indistinguible de una corrida sana.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import verify as V


def _real_event(tool: str = "show_widget", reason: str = "cortada por el tope de tokens",
                finish: str = "length") -> dict:
    """Un evento tal y como lo devuelve `/api/observability/events`, no como se emite en proceso."""
    return {"kind": "tool_dropped", "cat": "flash",
            "payload": json.dumps({"kind": "tool_dropped", "label": "⚠️ acción descartada",
                                   "text": f"{tool}: {reason}", "cat": "flash",
                                   "tool": tool, "reason": reason, "finish_reason": finish})}


def test_reads_the_shape_the_observability_api_actually_returns():
    got = V.dropped_actions([_real_event()])
    assert got == [{"tool": "show_widget", "reason": "cortada por el tope de tokens",
                    "finish_reason": "length"}]


def test_and_the_two_other_shapes_read_the_same():
    """Anidada bajo `extra` y en-proceso: el mismo hecho no puede depender de por dónde entró el evento."""
    nested = [{"kind": "tool_dropped", "payload": {"extra": {"tool": "a", "reason": "b"}}}]
    inproc = [{"kind": "tool_dropped", "extra": {"tool": "a", "reason": "b"}}]
    assert V.dropped_actions(nested)[0]["tool"] == "a"
    assert V.dropped_actions(inproc)[0]["tool"] == "a"


def test_an_unrelated_event_is_not_a_dropped_action():
    """La mitad de sensibilidad: sin esto, «lee los descartes» y «lo declara todo un descarte» pasan igual."""
    assert V.dropped_actions([{"kind": "brain", "payload": "{}"},
                              {"kind": "search", "payload": json.dumps({"tool": "web_search"})}]) == []


def test_a_broken_payload_does_not_take_the_run_down():
    """Fail-open: esto es recogida de evidencia para el juez, nunca una puerta que pueda tirar una corrida."""
    assert V.dropped_actions([{"kind": "tool_dropped", "payload": "no-es-json{{"}]) == [
        {"tool": "", "reason": "", "finish_reason": ""}]
    assert V.dropped_actions([]) == []


def test_it_reaches_the_mechanism_report_and_the_judge():
    """Que el helper acierte no sirve de nada si el informe no lo lleva: es el fallo de «la verdad existe y no
    llega al sitio donde se decide» que ya se repitió en V2-145/V2-150 y en V2-171."""
    rep = V.mechanism_report([_real_event()], expected_signals=[])
    assert rep["dropped_actions"] == [{"tool": "show_widget",
                                       "reason": "cortada por el tope de tokens",
                                       "finish_reason": "length"}]

    from tests.use_cases.e2e.agent.judge import mechanism_facts
    txt = mechanism_facts(rep)
    assert "ACCIÓN(ES) QUE ZAELAR SÍ DECIDIÓ" in txt
    assert "show_widget" in txt
    assert "no acuses a zaelar de no intentarlo" in txt


def test_and_says_nothing_when_no_action_was_dropped():
    from tests.use_cases.e2e.agent.judge import mechanism_facts
    rep = V.mechanism_report([{"kind": "brain", "payload": "{}"}], expected_signals=[])
    assert rep["dropped_actions"] == []
    assert "ACCIÓN(ES) QUE ZAELAR SÍ DECIDIÓ" not in mechanism_facts(rep)
