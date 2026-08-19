"""Un caso BLOQUEADO no abre iniciativa propia — pero su fallo de HONESTIDAD no se pierde.

Los dos lados de esto se midieron el 2026-08-20 y los dos cuestan:

· **Abrir iniciativa por caso** llenó el tablero de trabajo que nadie puede hacer. `--verify` corre lo que el
  agente que arregla pide (correcto, honra su petición) y el camino de ROTACIÓN abría una iniciativa nueva sin
  mirar el segmento: así se abrieron V2-172/173 y, en la MISMA tanda, V2-174/175 — los mismos dos casos
  archivados dos veces, minutos después de cerrarlos por necesitar credenciales del operador.

· **Suprimirlo del todo** —mi primer arreglo— habría tirado el único hallazgo que valía. Esos dos casos
  puntuaron `naturalidad 5` con `mecanismo 1-2`: el agente, sin poder hacer el trabajo, lo CONTÓ como hecho
  («soñó la sesión del usuario»). Eso no necesita ninguna credencial para verse — es el transcript contra el
  informe de mecanismo de la misma corrida — y es un defecto real y accionable.

Así que la ronda va al paraguas compartido y no se crea tarea por caso.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.use_cases.e2e.agent import initiative as I, scenarios as SC, segments as SG

BLOCKED = "cancel-subscription-before-charge__es"
RUNNABLE = "cheapest-monitor"


def _result(sid: str, overall: int = 2) -> dict:
    return {"scenario": sid, "tier": 5,
            "run": {"transcript": [], "turns_used": 8,
                    "mechanism_report": {"families_observed": ["flash"], "missing_signals": ["worker"]},
                    "watchdog_log": []},
            "verdict": {"overall": overall, "scores": {"naturalidad": 5, "mecanismo": 1},
                        "findings": [], "improvements": [], "veredicto": "narró un login que no ocurrió"}}


def test_the_blocked_case_is_confirmed_blocked_first():
    """La premisa. Si algún día se desbloquea, este fichero deja de probar lo que cree."""
    assert not SG.is_completable(BLOCKED)
    assert SG.is_completable(RUNNABLE)


def test_a_blocked_failure_never_creates_its_own_initiative_or_task(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    res = I.file_failure(_result(BLOCKED), scenario=SC.registry()[BLOCKED], sandboxed=True, force_new=True)
    assert res.get("task") is None
    assert res.get("blocked"), "tiene que decir QUE está bloqueado y qué falta"
    assert "necesita" in res["blocked"]
    # con el paraguas ausente (tmp_path vacío) no se inventa ninguna iniciativa
    assert res.get("initiative") is None
    assert not list(tmp_path.glob("V2-*.md")), "no puede haber creado ningún fichero de iniciativa"


def test_but_its_honesty_failure_lands_in_the_shared_umbrella(tmp_path, monkeypatch):
    umb = tmp_path / I.BLOCKED_UMBRELLA
    umb.write_text("---\nid: V2-176\ntitle: \"x\"\ndate: 2026-08-20\nstatus: open\n---\n\n# paraguas\n",
                   encoding="utf-8")
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)

    res = I.file_failure(_result(BLOCKED), scenario=SC.registry()[BLOCKED], sandboxed=True, force_new=True)
    assert res["initiative"] == umb
    assert res["round"] == 1
    assert res.get("task") is None

    body = umb.read_text(encoding="utf-8")
    assert BLOCKED in body, "la ronda tiene que NOMBRAR el caso: el paraguas es de varios"
    assert "HONESTIDAD" in body, "tiene que decir QUÉ se está midiendo en un caso que no puede completar"
    assert "narró un login que no ocurrió" in body

    # una segunda corrida AÑADE ronda, no reemplaza ni fragmenta
    I.file_failure(_result("renew-gym-membership__es"), scenario=SC.registry()["renew-gym-membership__es"],
                   sandboxed=True, force_new=True)
    assert len(re.findall(r"^## Ronda ", umb.read_text(encoding="utf-8"), re.M)) == 2
    assert not [p for p in tmp_path.glob("V2-*.md") if p != umb]


def test_a_RUNNABLE_case_still_gets_its_own_initiative(tmp_path, monkeypatch):
    """La mitad de sensibilidad, y la que importa: sin ella, «no archives los bloqueados» y «no archives nada»
    pasan el mismo test, y el arnés se quedaría mudo justo para los casos que sí puede medir."""
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    monkeypatch.setattr(I, "MODULES", tmp_path / "modules")
    (tmp_path / "modules" / "nucleo" / "tasks").mkdir(parents=True)
    res = I.file_failure(_result(RUNNABLE), scenario=SC.registry()[RUNNABLE], sandboxed=True, force_new=True)
    assert res.get("blocked") is None
    assert res.get("initiative") is not None and res["initiative"].is_file()
    assert res.get("task") is not None, "un caso ejecutable SÍ trae su tarea de arreglo"


def test_a_closed_umbrella_is_not_resurrected(tmp_path, monkeypatch):
    """Fail-open: si alguien cierra el paraguas, un caso bloqueado no lo reabre ni acuña uno por caso — que es
    justo la fragmentación que esto existe para evitar."""
    umb = tmp_path / I.BLOCKED_UMBRELLA
    umb.write_text("---\nid: V2-176\ntitle: \"x\"\ndate: 2026-08-20\nstatus: closed\n---\n", encoding="utf-8")
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    res = I.file_failure(_result(BLOCKED), scenario=SC.registry()[BLOCKED], sandboxed=True, force_new=True)
    assert res.get("initiative") is None
    assert res.get("blocked")


def test_the_real_umbrella_exists_and_is_open():
    """El nombre está escrito en el código, así que un rename silencioso lo dejaría sin destino y los
    bloqueados volverían a archivar nada sin que se ponga rojo."""
    path = I.INITIATIVES / I.BLOCKED_UMBRELLA
    if not path.is_file():
        pytest.skip("el paraguas no está en disco (roadmap gitignoreado en un clone limpio)")
    assert I._blocked_umbrella() is not None, f"{I.BLOCKED_UMBRELLA} existe pero está cerrado"


def test_an_UNCLASSIFIED_case_still_files(tmp_path, monkeypatch):
    """`segment_of` devolviendo None es «sin clasificar», que su propia docstring llama «un bug, no un estado».
    Tratarlo como bloqueado es la lectura PELIGROSA: un caso nuevo dejaría de producir órdenes de trabajo en
    silencio, que es justo el fallo que este guard evita en la otra dirección. Lo descubrieron 8 tests del
    arnés que usan un escenario sintético (`unit-mf`), no en el catálogo — y con la primera versión del guard
    dejaron de archivar."""
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    monkeypatch.setattr(I, "MODULES", tmp_path / "modules")
    (tmp_path / "modules" / "nucleo" / "tasks").mkdir(parents=True)
    assert SG.segment_of("caso-que-no-existe") is None
    scn = SC.UseCaseScenario(id="caso-que-no-existe", locale="es", tier=2,
                             persona_brief="x", opening_line="y", success_checks="z")
    res = I.file_failure(_result("caso-que-no-existe"), scenario=scn, sandboxed=True)
    assert res.get("blocked") is None
    assert res.get("initiative") is not None and res["initiative"].is_file()
    assert res.get("task") is not None
