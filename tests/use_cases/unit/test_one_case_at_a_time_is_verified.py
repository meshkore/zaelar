"""“Reset” must be a verified FACT, not a line that is printed regardless (2026-08-24).

Operator rule, with four sheets for different cases stacked on the screen: *“we do one, we close, we
continue with another”*. The harness was already resetting between cases—and observability confirms it:
`session RESET` and `widget close` appear at every boundary—but it then ran `time.sleep(2.0)` and printed
“engine reset (with no previous work or canvas)” NO MATTER WHAT HAPPENED.

Both halves were wrong:

  · the two seconds were an invented number. Measured that same day in the 16:20 batch, a research worker
    from the PREVIOUS case was still emitting widget events after the reset;
  · and the line is an ASSERTION, in exactly the place where the operator reads it and relies on it to know
    that the next case is measured on its own. One that nobody checked.

Now it waits for both observable signals—live work and saved cards—to reach zero, with a
LIMIT (not a fixed wait), and what is printed is what was found. If it is not clean, the batch CONTINUES: a
worker that takes time to die costs less than losing the measurement. What cannot happen is measuring it by
silencing it.
"""
import inspect

from tests.use_cases.e2e.agent import probe_client as pc
from tests.use_cases.e2e.agent import run as runmod


def _viva(goal: str) -> dict:
    """A session as served by `/api/tasks`. `status` is NOT decoration: it is what distinguishes live work from
    a completed row, and omitting it from a fixture would let a filter that filters nothing pass."""
    return {"id": "1", "status": "running", "goal": goal}


def _stub(monkeypatch, tasks_seq, items_seq):
    """Serve a sequence of reads: this tests that it WAITS, rather than merely looking once."""
    t = list(tasks_seq); i = list(items_seq)
    monkeypatch.setattr(pc, "live_tasks", lambda: t.pop(0) if len(t) > 1 else t[0])
    monkeypatch.setattr(pc, "canvas_items", lambda: i.pop(0) if len(i) > 1 else i[0])


def test_vuelve_EN_CUANTO_esta_limpio(monkeypatch):
    """The budget is a limit, not a wait: an engine that is already clean must not cost 25 s per case."""
    _stub(monkeypatch, [[]], [[]])
    st = pc.settle_after_reset(budget_s=5.0, poll_s=0.01)
    assert st["clean"] is True and st["waited_s"] < 1.0


def test_ESPERA_a_que_muera_el_trabajo_del_caso_anterior(monkeypatch):
    """The measured situation: the reset has already happened and the previous worker remains alive for a little longer."""
    _stub(monkeypatch, [[_viva("el caso de antes")], [_viva("el caso de antes")], []], [[]])
    st = pc.settle_after_reset(budget_s=5.0, poll_s=0.01)
    assert st["clean"] is True, "tiene que volver a mirar, no rendirse en la primera lectura"


def test_una_TARJETA_que_sobrevive_tampoco_es_limpio(monkeypatch):
    """It is not enough for the work to die: a saved card reappears as soon as someone reloads."""
    _stub(monkeypatch, [[]], [[{"id": "results::abc"}]])
    st = pc.settle_after_reset(budget_s=0.05, poll_s=0.01)
    assert st["clean"] is False and st["items"] == ["results::abc"]


def test_si_no_se_limpia_DICE_QUE_QUEDO_VIVO(monkeypatch):
    """A “not clean” result without names sends someone to inspect a log; the harness already has the answer at hand."""
    _stub(monkeypatch, [[_viva("buscar un hotel en Sevilla para el finde")]], [[]])
    st = pc.settle_after_reset(budget_s=0.05, poll_s=0.01)
    assert st["clean"] is False
    assert st["tasks"] and "hotel" in st["tasks"][0]


def _codigo_del_lote() -> str:
    """The `_run_batch` code WITHOUT comments.

    The tests below look for markers in the source, and a comment can HIDE a marker: on 2026-08-25,
    V2-328 quoted the line “engine clean in 0.0s…” inside a comment to document the defect, and the two
    guards in this file turned red because their `index()` found the QUOTE before the `print`.
    No behavior had changed. Removing comments anchors the markers where they matter: in the code.
    """
    return "\n".join(l for l in inspect.getsource(runmod._run_batch).splitlines()
                      if not l.strip().startswith("#"))


def test_NO_para_la_tanda_cuando_no_se_limpia():
    """Explicit decision: warn and continue. Stopping for a slow worker costs more than the warning."""
    src = _codigo_del_lote()
    i = src.index("settle_after_reset")
    tramo = src[i:i + 1200]
    assert "el motor NO quedó limpio" in tramo
    assert "break" not in tramo.split("except Exception")[0], (
        "advertir no puede convertirse en abandonar la tanda")


def test_la_linea_tranquilizadora_YA_NO_se_imprime_a_ciegas():
    """The exact defect: the assertion was outside any condition."""
    src = _codigo_del_lote()
    assert "time.sleep(2.0)" not in src, "un número inventado no es una comprobación"
    i = src.index("motor limpio en")
    # the good line lives INSIDE the branch that checked that it is clean
    assert 'if st["clean"]:' in src[:i]


def test_solo_cuenta_como_vivo_lo_que_ESTA_vivo(monkeypatch):
    """A session marked COMPLETED in the registry cannot block the next case from starting for 25 s each time.

    The filter is deliberately applied in the harness rather than delegated to the engine: `active_sessions()`
    went unfiltered until V2-115, and that gap represented already-finished tasks as “in progress”. Tying the
    wait to a registry that has already failed this way once is waiting for it to fail again."""
    monkeypatch.setattr(pc, "live_tasks", lambda: [
        {"id": "1", "status": "done", "goal": "ya terminó"},
        {"id": "3", "status": "cancelled", "goal": "parada"},
    ])
    monkeypatch.setattr(pc, "canvas_items", lambda: [])
    st = pc.settle_after_reset(budget_s=0.05, poll_s=0.01)
    assert st["clean"] is True, "done y cancelled no son trabajo vivo"


def test_una_sesion_ESPERANDO_al_operador_sigue_siendo_trabajo_vivo(monkeypatch):
    """`needs_input` is a task stopped in front of a question, not a dead task: it still holds things up."""
    monkeypatch.setattr(pc, "live_tasks", lambda: [{"id": "9", "status": "needs_input", "goal": "esperando"}])
    monkeypatch.setattr(pc, "canvas_items", lambda: [])
    st = pc.settle_after_reset(budget_s=0.05, poll_s=0.01)
    assert st["clean"] is False
