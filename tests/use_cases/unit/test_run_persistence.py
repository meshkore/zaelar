"""Una tanda interrumpida NO puede tirar los veredictos que ya se habían ganado.

Medido el 2026-08-20: una tanda de verify de 6 casos se cortó a los ~12 minutos, con
`cancel-subscription-before-charge__es` ya conducido Y JUZGADO — y el marcador seguía mostrando la corrida
anterior, porque el único `record()` estaba DESPUÉS del bucle y nunca llegó a ejecutarse. Se perdió todo lo
que la tanda había ganado, incluido el veredicto que por fin mostraba la conducta CORRECTA (admitir que no
puede entrar en la cuenta del operador en vez de fingirlo).

En un bucle desatendido las tandas duran decenas de minutos y una interrupción no es exótica: es un portátil
que se duerme, un tick matado, un crash. Y el coste no es solo el tiempo — es gasto real de LLM ya pagado.
"""
from __future__ import annotations

import inspect
import re

from tests.use_cases.e2e.agent import run as R, status as statusmod


def test_the_ledger_is_written_INSIDE_the_scenario_loop():
    """La afirmación estructural: el `record()` tiene que estar dentro del bucle que recorre los escenarios,
    no después. Se comprueba por SANGRÍA porque es lo que distingue las dos posiciones — el nombre de la
    función es el mismo en ambas."""
    src = inspect.getsource(R.walk) if hasattr(R, "walk") else inspect.getsource(R)
    calls = [ln for ln in src.split("\n") if "statusmod.record(" in ln]
    assert calls, "nadie escribe el marcador"
    inside = [ln for ln in calls if len(ln) - len(ln.lstrip()) >= 8]
    assert inside, ("el único `record()` está al nivel de la función, o sea DESPUÉS del bucle: una tanda "
                    "interrumpida perdería todos sus veredictos")


def test_and_it_records_ONE_scenario_at_a_time():
    """`record()` solo toca los escenarios que recibe («una tanda de uno no puede parecer que invalidó a los
    otros cuatro», dice su propia docstring), así que la llamada de dentro del bucle debe pasar SOLO el último
    resultado. Pasarle `results` entero re-escribiría el `last_run` de todos en cada vuelta."""
    src = inspect.getsource(R)
    inside = [ln.strip() for ln in src.split("\n")
              if "statusmod.record(" in ln and (len(ln) - len(ln.lstrip())) >= 8]
    assert inside
    assert any(re.search(r"record\(results\[-1:\]", ln) for ln in inside), inside


def test_no_batch_wide_record_rewrites_last_run_afterwards():
    """`last_run` es un campo que se usa para decidir qué veredictos son de ANTES de un cambio de entorno (se
    usó para retirar los 6 medidos con el motor en inglés). Un `record(results)` al final le pondría a todas
    las filas la hora de FIN de la tanda, que no es cuando corrió cada caso."""
    src = inspect.getsource(R)
    top_level = [ln for ln in src.split("\n")
                 if "statusmod.record(" in ln and 0 < (len(ln) - len(ln.lstrip())) < 8]
    assert not top_level, f"queda un record() de tanda completa que pisaría los last_run: {top_level}"


def test_record_of_one_leaves_the_other_rows_untouched(tmp_path, monkeypatch):
    """La conducta en la que se apoya todo lo anterior, afirmada de verdad y no leída de una docstring."""
    monkeypatch.setattr(statusmod, "BOARD_PATH", tmp_path / "STATUS.md")
    monkeypatch.setattr(statusmod, "LEDGER_PATH", tmp_path / "status.json")

    def _res(sid, overall):
        return {"scenario": sid, "tier": 2, "run": {"transcript": [], "mechanism_report": {}},
                "verdict": {"overall": overall, "scores": {}, "veredicto": f"v-{sid}"}}

    statusmod.record([_res("caso-a", 5)], sandboxed=True)
    statusmod.record([_res("caso-b", 1)], sandboxed=True)
    led = statusmod.load()["scenarios"]
    assert set(led) == {"caso-a", "caso-b"}, "una tanda de uno no puede borrar la fila de la otra"
    assert led["caso-a"]["state"] == "PASS" and led["caso-b"]["state"] == "FAIL"
