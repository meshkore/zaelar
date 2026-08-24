"""El plató se limpia ANTES de CADA caso — también antes del primero.

Hasta 2026-08-21 el reset entre casos vivía tras un `if results:`, o sea que solo corría a partir del
SEGUNDO. En una tanda de un solo caso no corría nunca, y en el plató —que es persistente a propósito: mismo
puerto, se mira en vivo— eso significa que **el primer caso de cada ronda heredaba el canvas, las tareas y los
workers de la ronda ANTERIOR**. El operador cargó el test ES y lo primero que vio fue pantalla sucia de la
corrida de antes.

La regla que pidió es exactamente lo que `hard_reset()` hace y lo que NO hace: mata el trabajo vivo y borra el
canvas, y deja EN PIE la memoria y el estado (`/reset/hard`, no `/api/reset/full` con `wipe_memory`). Los dos
lados se comprueban aquí, porque «limpiar más» es la regresión fácil: borrar memoria exigiría matar el proceso
y, además, los casos de descubrimiento siembran preferencias que tienen que sobrevivir al reset.
"""
from __future__ import annotations

import inspect

from tests.use_cases.e2e.agent import (config, probe_client, report as reportmod, run as R,
                                       scenarios as SC, status as statusmod)


def _s(sid: str):
    return SC.UseCaseScenario(id=sid, locale="es", tier=2, persona_brief="p", opening_line="o",
                              success_checks="s")


def _batch(monkeypatch, tmp_path, ids: list[str]) -> list[str]:
    """Corre `_run_batch` de verdad con el mundo exterior desarmado, y devuelve el ORDEN de lo que pasó.

    Se llama a la función REAL en vez de comprobar la fuente: un guarda de `grep` seguiría verde el día que
    alguien vuelva a meter el reset detrás de una condición, que es justo el fallo que esto cierra.
    """
    order: list[str] = []
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(probe_client, "hard_reset", lambda: order.append("reset") or {})
    monkeypatch.setattr(R.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(R, "_run_scenario", lambda scn, **k: (
        order.append(f"run:{scn.id}") or {"scenario": scn.id, "tier": scn.tier, "channel": "probe",
                                          "run": {}, "verdict": {"overall": 5}}))
    # El marcador y el informe son artefactos VIVOS del operador: un test unitario no los toca (conftest ya
    # aísla lo suyo, esto cierra los dos que quedan por fuera).
    monkeypatch.setattr(statusmod, "record", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "attach_workspaces", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "summary_line", lambda: "")
    monkeypatch.setattr(reportmod, "build", lambda *a, **k: tmp_path / "r.md")
    # EL SELLO DEL ÁRBOL, FIJADO. `_run_batch` lo relee entre casos desde V2-282 (una tanda dura horas y las
    # guardas de arranque no ven lo que pasa durante), así que sin fijarlo estos tests preguntan por el estado
    # de git de la máquina que los corre: verdes con el árbol limpio, rojos con una edición en curso. Es el
    # «un test verde por el ENTORNO» que el conftest raíz ya persigue por el idioma y por la config.
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "fijo", "dirty": [], "n_dirty": 0})
    R._run_batch([_s(i) for i in ids], sandboxed=True, args_no_file=True)
    return order


def test_the_first_case_of_a_batch_also_starts_clean(monkeypatch, tmp_path):
    assert _batch(monkeypatch, tmp_path, ["uno"]) == ["reset", "run:uno"]


def test_every_case_gets_its_own_reset_and_it_comes_first(monkeypatch, tmp_path):
    assert _batch(monkeypatch, tmp_path, ["a", "b", "c"]) == [
        "reset", "run:a", "reset", "run:b", "reset", "run:c"]


def test_a_failed_reset_does_not_lose_the_batch(monkeypatch, tmp_path):
    """El reset es best-effort: un motor que no contesta al reset deja el caso sucio, no la tanda muerta."""
    def boom():
        raise RuntimeError("motor mudo")
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(probe_client, "hard_reset", boom)
    monkeypatch.setattr(R.time, "sleep", lambda *_a, **_k: None)
    ran: list[str] = []
    monkeypatch.setattr(R, "_run_scenario", lambda scn, **k: (
        ran.append(scn.id) or {"scenario": scn.id, "tier": scn.tier, "channel": "probe",
                               "run": {}, "verdict": {"overall": 5}}))
    monkeypatch.setattr(statusmod, "record", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "attach_workspaces", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "summary_line", lambda: "")
    monkeypatch.setattr(reportmod, "build", lambda *a, **k: tmp_path / "r.md")
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "fijo", "dirty": [], "n_dirty": 0})
    R._run_batch([_s("a"), _s("b")], sandboxed=True, args_no_file=True)
    assert ran == ["a", "b"]


def test_the_reset_that_runs_is_the_one_that_keeps_memory():
    """CONTRAPESO, y es el lado por el que esto se rompe «mejorándolo».

    `hard_reset()` pega a `/reset/hard`. `/api/reset/full` con `wipe_memory` es OTRO endpoint: exige matar el
    proceso (SQLite en uso) y se llevaría por delante las preferencias que los casos de descubrimiento
    siembran ANTES de hablar — el caso mediría al destilador de memoria y lo reportaría como que el agente no
    razona. Si alguien cambia el endpoint «para limpiar del todo», esto se pone rojo.
    """
    body = inspect.getsource(probe_client.hard_reset)
    call = [ln.strip() for ln in body.splitlines() if "_post(" in ln]
    assert call == ['return _post("/reset/hard", {}, timeout=60.0)'], call
