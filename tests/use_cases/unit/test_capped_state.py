"""Un caso cuya otra mitad exige la credencial del usuario NO es un fallo, y no puede seguir en el bucle.

Regla del operador (2026-08-20): «esos tests se marcarían como use cases especiales que requieren credenciales
y no los incluimos en nuestra batida». El motivo es material, no de gusto: hoy el producto no guarda logins de
usuario, y la vía que sí existe en local —abrir un navegador, que la persona se autentique, quedarse con las
cookies— es justo lo que un arnés de backend no puede simular. Puntuarlos FAIL dejaba filas rojas permanentes
y alimentaba al bucle de mejora con trabajo que nadie puede cerrar nunca.

La mitad ALCANZABLE se sigue puntuando entera: encontrar las opciones y ofrecerlas es el caso completable;
cerrar y pagar es el topado.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import status as S


def _r(sid: str, overall: int, mech: int = 4) -> dict:
    return {"scenario": sid, "tier": 1, "channel": "probe",
            "run": {"transcript": [], "mechanism_report": {}},
            "verdict": {"overall": overall, "veredicto": "x",
                        "scores": {"naturalidad": 5, "adaptacion": 5, "resultado": overall,
                                   "mecanismo": mech, "eficiencia": 4}}}


def test_a_credentialed_case_is_CAPPED_not_failed():
    """`book-hotel-night-known` necesita cuenta y tarjeta para cerrar la reserva: nunca podrá ser PASS aquí, y
    tampoco es justo llamarlo FAIL."""
    assert S._state(2, _r("book-hotel-night-known__es", 2)) == "CAPPED"


def test_and_still_CAPPED_when_it_behaves_perfectly():
    """El tope no depende de la nota: un 5 topado es «llegó hasta donde se puede llegar», no un aprobado."""
    assert S._state(5, _r("cancel-subscription-before-charge__es", 5)) == "CAPPED"


def test_a_completable_case_is_untouched():
    """Sensibilidad: si el estado nuevo se comiera los casos normales, el marcador dejaría de medir el producto."""
    assert S._state(5, _r("build-workout-tracker-widget", 5)) == "PASS"
    assert S._state(2, _r("build-workout-tracker-widget", 2)) == "FAIL"


def test_the_mechanism_gate_still_applies_to_completable_cases():
    assert S._state(4, _r("build-workout-tracker-widget", 4, mech=2)) == "FAIL"


def test_INFRA_still_wins_over_the_cap():
    """Un arnés que se murió no midió nada, y de un caso topado tampoco: sigue siendo INFRA, no un tope."""
    r = _r("book-hotel-night-known__es", 2)
    r["run"]["crashed"] = True
    assert S._state(2, r) == "INFRA"


def test_the_board_excludes_capped_from_the_pass_fail_count(tmp_path, monkeypatch):
    """Lo que el operador pidió de verdad: que no interfieran. Se comprueba en el texto del tablero."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([_r("build-workout-tracker-widget", 5), _r("book-hotel-night-known__es", 2)], sandboxed=True)
    board = (tmp_path / "STATUS.md").read_text()
    assert "1 passing · 0 failing" in board, board[board.find("passing") - 60:board.find("passing") + 40]
    assert "scenarios we can actually finish" in board
    assert "1 🔒 capped" in board
    assert "book-hotel-night-known__es" in board
