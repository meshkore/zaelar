#
# Tests del CRITERIO DE RITMO / NO-PROGRESO agente-agente (V2-073). Run: .venv/bin/pytest connectors/meshkore/test_pace.py -q
#
# El «criterio humano» en código: cuando un agente externo de menos capacidad se embucla (repite variando la
# redacción, o suelta frases de bloqueo) y no sigue el hilo, hay que PARAR y cederle el turno, no bombardearle.
# Con el operador la conversación siempre fluye; esto es SOLO para el canal agente-agente. Cubre la detección
# (frases de bloqueo + casi-repetición) con los mensajes REALES con los que zalo se atascó, y la progresión del
# veredicto (seguir → ceder el turno → callar).
#
import pytest

from connectors.meshkore import capsule


# ── frases de BLOQUEO (no-avance) — con los mensajes reales de zalo ─────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "⛔ Estamos en fase **Definición** aún. No puedo discutir **Diseño** hasta que cerremos la fase actual.",
    "No puedo discutir Desarrollo hasta que cerremos la fase actual.",
    "un momento, consultando con el equipo",
    "sigo esperando la validación",
    "todavía no puedo avanzar con eso",
    "estamos en fase de definición",
    # bloqueado-por-dependencia (revisión charla zalo↔Poli, 2026-07-26)
    "Poli sigue caído (503). Sin materia prima de expertos, mi respuesta es incompleta.",
    "Poli no respondió",
    "Error: can't reach Poli — Network connection lost",
    "Sin su input no puedo verificar cobertura ni avanzar con tuneo.",
])
def test_looks_stuck_true(text):
    assert capsule.looks_stuck(text)


@pytest.mark.parametrize("text", [
    "Los features son: log-returns, ATR relativo y volumen normalizado.",
    "Propongo 3 estados HMM: trend, range, volatile. ¿Lo cerramos?",
    "he subido el backtest al repo, revisa el sharpe",
])
def test_looks_stuck_false(text):
    assert not capsule.looks_stuck(text)


# ── casi-repetición (reescritura para esquivar el match exacto) ─────────────────────────────────────────────────
def test_near_repeat_detects_reworded():
    recent = ["Estamos en fase Definición aún, no puedo discutir Diseño hasta cerrar la fase actual"]
    assert capsule.near_repeat(
        "Aún estamos en la fase Definición y no puedo discutir el Diseño hasta que cerremos la fase actual", recent)


def test_near_repeat_false_on_new_content():
    recent = ["Estamos en fase Definición, no puedo discutir Diseño"]
    assert not capsule.near_repeat("Los features son returns, ATR y volumen; ¿cerramos la definición?", recent)


def test_near_repeat_ignores_tiny_messages():
    assert not capsule.near_repeat("ok", ["ok vale"])          # mensajes muy cortos no se juzgan


# ── advanced() = ¿aporta o se embucla? ──────────────────────────────────────────────────────────────────────────
def test_advanced_true_on_substantive_new():
    assert capsule.advanced("Propongo cerrar con 4 features y risk fijo del 1%.", ["hola", "¿qué tal?"])


def test_advanced_false_on_stuck():
    assert not capsule.advanced("⛔ Estamos en fase Definición, no puedo discutir Diseño", [])


def test_advanced_false_on_near_repeat():
    recent = ["no puedo discutir diseño hasta cerrar la definicion actual del proyecto"]
    assert not capsule.advanced("no puedo discutir el diseno hasta que cerremos la definicion actual del proyecto", recent)


# ── progresión del veredicto de ritmo (seguir → ceder turno → callar) ───────────────────────────────────────────
def test_pace_verdict_progression():
    m = capsule.PACE_HANDBACK_AT
    assert capsule.stall_verdict(0, m - 1, m=m) == "seguir"     # aún no
    assert capsule.stall_verdict(0, m, m=m) == "asertivo"       # cede el turno (hand-back)
    assert capsule.stall_verdict(0, 2 * m, m=m) == "callar"     # sigue sin avanzar → silencio


def test_handback_directive_is_pause_not_pile_on():
    d = capsule.PACE_HANDBACK.lower()
    assert "no añadas más ideas" in d or "no anadas mas ideas" in d
    assert "espera" in d or "listo" in d
