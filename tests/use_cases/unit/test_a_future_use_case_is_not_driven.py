"""Un caso de futuro se ESCRIBE hoy y no se CONDUCE hasta que sus tareas de roadmap estén hechas.

Regla del operador (2026-08-21): «todos los comportamientos que espero deben formar parte de un use case lo
más completito posible […] puedes vincular el use case a las tareas del roadmap, que son las que una vez
resueltas permitirán probar ese use case. Y así ahora mismo jamás lo ejecutarías, porque sabrías que esas
tareas están pendientes […] los use cases son el punto más alto de la pirámide».

Las dos mitades importan y se prueban por separado: **escribirlo** (la petición no se pierde, y quien cierre
la tarea tiene delante el caso que la prueba) y **no conducirlo** (una conversación entera para producir un
fallo que ya está escrito en su iniciativa, más una ronda duplicada archivada en el paraguas).

Y una tercera que no es obvia: **saltarlo NO puede ser en silencio**. Un caso que desaparece de la selección
sin explicación se lee como que no existe, que es justo lo contrario de lo que pide la regla.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tests.use_cases.e2e.agent import run as R, scenarios as SC, segments as G

INITIATIVES = Path(__file__).resolve().parents[3] / ".meshkore" / "roadmap" / "initiatives"


def _args(**kw):
    base = dict(scenario="all", verify=False, tier=None, locale="es", segment=None, limit=None,
                start_at=None, include_blocked=False, sandbox=False, lab="", no_file=True,
                stop_after_failures=0, rounds=1, allow_dirty=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _selected(monkeypatch, **kw) -> list[str]:
    got: list[str] = []
    monkeypatch.setattr(R, "_sandbox_groups", lambda chosen, a, **k: got.extend(s.id for s in chosen) or 0)
    monkeypatch.setattr(R, "_run_batch", lambda chosen, **k: got.extend(s.id for s in chosen) or 0)
    R.run(_args(sandbox=True, **kw))
    return got


def test_a_blocked_case_is_not_in_the_batch(monkeypatch):
    got = _selected(monkeypatch)
    assert "repeat-a-finished-search" not in got
    assert "candidates-already-known" not in got
    assert "change-the-criteria-not-the-search" not in got


def test_a_gate_LIFTS_when_its_mechanism_lands(monkeypatch):
    """El otro lado del trinquete, y es el que se olvida. `two-searches-two-sheets` estuvo gateado por
    V2-259 y dejó de estarlo el 2026-08-21 al aterrizar la iniciativa completa (`b8a1415` + `f3052f9`).
    Un gate que nadie retira convierte un caso construido en un caso que no se mide NUNCA, y el marcador
    no lo dice: la fila simplemente no aparece, igual que si no existiera."""
    got = _selected(monkeypatch)
    assert "two-searches-two-sheets" in got
    assert not G.blocked_by("two-searches-two-sheets")


def test_the_rest_of_the_catalog_is_untouched(monkeypatch):
    """SENSIBILIDAD, y es el lado caro: gatear de más encoge el paseo EN SILENCIO e invalida medidas que ya
    están en el marcador. El gate es por caso que lo DECLARA, nunca por el grupo `capability` entero."""
    got = _selected(monkeypatch)
    assert "three-tasks-at-once" in got
    assert "restaurant-tonight-madrid" in got
    blocked = {s.id for s in SC.all_scenarios() if G.blocked_by(s.id)}
    assert len(got) == len([s for s in SC.all_scenarios() if s.locale == "es"]) - len(
        [b for b in blocked if SC.registry()[b].locale == "es"])


def test_skipping_is_announced_with_the_tasks_that_gate_it(monkeypatch, capsys):
    _selected(monkeypatch)
    out = capsys.readouterr().out
    assert "caso(s) de FUTURO" in out
    assert "repeat-a-finished-search" in out
    assert "V2-260" in out


def test_include_blocked_forces_them_in(monkeypatch):
    """La escotilla existe porque el caso ES conducible — solo se sabe que va a fallar. Forzarlo es como se
    produce la evidencia que va en la iniciativa."""
    got = _selected(monkeypatch, include_blocked=True)
    assert "repeat-a-finished-search" in got


def test_every_gate_points_at_an_initiative_that_EXISTS():
    """Sin esto, renombrar una iniciativa deja el gate citando algo que no está — y un caso bloqueado por una
    tarea inexistente no se conduce NUNCA y nadie sabe qué hay que hacer para desbloquearlo.

    Se comprueba el PREFIJO (`V2-259`) y no la fase, porque la fase vive dentro del documento; lo que tiene
    que existir es el documento.
    """
    for scn in SC.all_scenarios():
        for ref in G.blocked_by(scn.id):
            num = ref.split()[0]
            hits = list(INITIATIVES.glob(f"{num}-*.md"))
            assert hits, f"{scn.id} bloqueado por {ref} y no existe ninguna iniciativa {num}-*.md"


def test_a_future_case_still_says_what_it_expects():
    """La mitad de ESCRIBIRLO: un caso gateado sin criterio es una nota, no un use case — y el día que se
    desbloquee habría que inventarse el listón, que es cuando se inventa a favor de lo que ya hace."""
    for scn in SC.all_scenarios():
        if not G.blocked_by(scn.id):
            continue
        assert len(scn.success_checks) > 400, scn.id
        assert len(scn.persona_brief) > 400, scn.id
        assert scn.opening_line.strip(), scn.id
