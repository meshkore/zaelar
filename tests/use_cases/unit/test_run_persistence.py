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


# ── una tanda que no midió NADA no puede pasar por una re-prueba ───────────────────────────────────────────
def test_a_batch_that_measured_nothing_is_reported_and_files_NOTHING(monkeypatch):
    """El fallo que enseñó esto: un SANDBOX HUÉRFANO (`python -m server`, PPID 1) que un lote matado dejó
    atrás se quedó con el puerto del sandbox, así que cada `run.py --verify` posterior moría al arrancar en
    menos de un segundo. `_runner_alive()` no lo ve —busca un proceso `…agent.run`, no el motor que el lote levanta— así
    que el tick seguía lanzando tandas imposibles y luego LEÍA EL VEREDICTO ANTERIOR del marcador y actuaba
    sobre él: logueaba «re-probado» para un caso que nadie corrió y, peor, `rotate_failure` habría archivado
    una iniciativa describiendo una corrida de hace una hora como si fuera evidencia nueva.

    Evidencia RANCIA es peor que ninguna: el agente que arregla no puede distinguirla.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import status as statusmod, tick as T

    filed: list[str] = []
    logged: list[str] = []
    ledger = {"scenarios": {"cheapest-monitor": {"state": "FAIL", "overall": 1, "last_run": "2026-08-20 01:21",
                                                 "verdict": "veredicto VIEJO"}}}
    monkeypatch.setattr(T, "_log", lambda m: logged.append(m))
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": "cheapest-monitor", "slug": "cheapest-monitor",
                                      "task": Path("T999-uc-cheapest-monitor-verify.md")}])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: None)
    monkeypatch.setattr(T.I, "rotate_failure", lambda r, **kw: filed.append("ROTATE") or {})
    monkeypatch.setattr(T.I, "file_failure", lambda r, **kw: filed.append("FILE") or {})
    monkeypatch.setattr(T.I, "close_on_pass", lambda *a, **kw: filed.append("CLOSE"))
    monkeypatch.setattr(T.I, "note_inconclusive", lambda *a, **kw: filed.append("INCONCLUSIVE"))
    monkeypatch.setattr(statusmod, "load", lambda: ledger)          # el marcador NO cambia: nada se midió
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")
    monkeypatch.setattr(T, "_run", lambda args, timeout_s: (1, "murió al arrancar el sandbox"))

    out = T._retest_pending()
    assert out["unrun"] == ["cheapest-monitor"]
    assert filed == [], f"actuó sobre un veredicto rancio: {filed}"
    said = " ".join(logged)
    assert "NO SE MIDIERON" in said
    # Los DOS puertos de sandbox, y leídos de la tabla (V2-459): el huérfano se queda con el del idioma de
    # la tanda que lo dejó, y el que lee el log no sabe cuál fue. Antes decía «43918» a pelo, un número que
    # desde V2-459 no usa nadie — un rastro que manda a mirar donde no hay nada es peor que ninguno.
    from tests.platform import ports as PORTS
    for _p in (PORTS.SANDBOX_ES, PORTS.SANDBOX_US):
        assert str(_p) in said, "el log tiene que decir DÓNDE mirar, o el siguiente lo diagnostica de cero"


def test_but_a_batch_that_DID_measure_is_acted_on_normally(monkeypatch):
    """La mitad de sensibilidad: sin esto, «no actúes sobre lo rancio» y «no actúes nunca» pasan igual, y el
    bucle dejaría de cerrar iniciativas y de abrir sucesoras — o sea de funcionar.

    El caso tiene que ser EJECUTABLE y NO agrupado, o la rama que gana es otra: la primera versión de este test
    usaba `cheapest-monitor`, que acababa de entrar en `GROUPED`, así que la rama de agrupados hacía `continue`
    correctamente y el test leía ese acierto como el fallo que buscaba.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import initiative as I2, scenarios as SC2, segments as SG2
    from tests.use_cases.e2e.agent import status as statusmod, tick as T

    sid = next(s.id for s in SC2.all_scenarios()
               if SG2.is_completable(s.id) and I2.GROUPED.get(SG2.bare(s.id)) is None)

    filed: list[str] = []
    ledger = {"scenarios": {sid: {"state": "FAIL", "overall": 1, "last_run": "2026-08-20 01:21"}}}
    monkeypatch.setattr(T, "_log", lambda m: None)
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": sid, "slug": sid,
                                      "task": Path(f"T999-uc-{sid}-verify.md")}])
    monkeypatch.setattr(T.I, "find_initiative", lambda s_: None)
    monkeypatch.setattr(T.I, "rotate_failure", lambda r, **kw: filed.append("ROTATE") or {})
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    def _run(args, timeout_s):
        # la tanda SÍ mide: mueve el `last_run`, como hace `record()` por escenario
        ledger["scenarios"][sid]["last_run"] = "2026-08-20 02:10"
        return (1, "")

    monkeypatch.setattr(T, "_run", _run)
    monkeypatch.setattr(statusmod, "load", lambda: ledger)

    out = T._retest_pending()
    assert out["unrun"] == []
    assert filed == ["ROTATE"], "una medición NUEVA sí tiene que mover la iniciativa"
