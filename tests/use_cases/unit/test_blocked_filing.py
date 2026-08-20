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


def test_the_tick_does_not_file_a_blocked_case_a_SECOND_time(monkeypatch):
    """`run.py --verify` ya archiva la ronda; el tick solo la NOMBRA.

    Archivar en los dos sitios escribió la MISMA ronda dos veces —mismo caso, mismo minuto— y se vio leyendo
    V2-176 el 2026-08-20 (rondas 3 y 4 idénticas). La rama de AGRUPADOS que está justo encima ya lo hacía bien
    por este mismo motivo; la de bloqueados no. Un duplicado no se pone rojo: solo hace que la evidencia de una
    iniciativa cuente el doble de intentos de los que hubo, que es peor que no tenerla.

    Se afirma sobre la CONDUCTA (¿se llamó a `file_failure`?) y no leyendo el fuente: la primera versión de
    este test buscaba el nombre en el texto de la rama y lo encontraba... en el comentario que explica por qué
    NO hay que llamarlo.
    """
    from tests.use_cases.e2e.agent import status as statusmod, tick as T

    calls: list[str] = []
    monkeypatch.setattr(T.I, "file_failure",
                        lambda result, **kw: calls.append(kw["scenario"].id) or {"initiative": None})
    monkeypatch.setattr(T.I, "rotate_failure",
                        lambda result, **kw: calls.append("ROTATE:" + kw["scenario"].id) or {})
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": BLOCKED, "task": "T999"}])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: None)
    # El marcador tiene que MOVERSE con la tanda: si `last_run` no cambia, el tick concluye —con razón— que no
    # se midió nada y no clasifica el caso en absoluto (ver `test_run_persistence.py`). Aquí lo que se prueba es
    # la rama de BLOQUEADOS, así que la tanda sí mide.
    ledger = {"scenarios": {BLOCKED: {"state": "FAIL", "overall": 2, "last_run": "2026-08-20 01:00",
                                      "verdict": "narró un login que no ocurrió"}}}

    def _run(args, timeout_s):
        ledger["scenarios"][BLOCKED]["last_run"] = "2026-08-20 02:20"
        return (1, "salida de prueba")

    monkeypatch.setattr(T, "_run", _run)
    monkeypatch.setattr(statusmod, "load", lambda: ledger)
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    out = T._retest_pending()
    assert out["retested"] == 1
    assert out["blocked"], "tiene que DECIR que lo re-probó y estaba bloqueado"
    assert calls == [], f"el tick volvió a archivar el caso bloqueado: {calls}"


def test_a_runnable_case_can_also_be_grouped_under_the_umbrella():
    """`cheapest-monitor` es EJECUTABLE y aun así comparte el defecto de V2-176 — iba camino de su tercera
    iniciativa propia. Que esté en GROUPED es lo que impide que se vuelva a fragmentar solo."""
    assert SG.is_completable("cheapest-monitor")
    assert I.GROUPED.get("cheapest-monitor") == I.BLOCKED_UMBRELLA
    path = I.INITIATIVES / I.BLOCKED_UMBRELLA
    if path.is_file():
        assert I.grouped_for("cheapest-monitor") is not None


def test_a_case_that_is_BOTH_blocked_and_grouped_files_in_its_OWN_umbrella(monkeypatch, tmp_path):
    """`find-theatre-tickets__es` necesita cuenta y tarjeta (bloqueado) **y** está en V2-167 (agrupado). Su
    paraguas propio manda.

    Sin esto, la MISMA medición cae en un fichero u otro según qué camino la archive —la rama de bloqueados
    escribe en V2-176, la de agrupados en V2-167— y la evidencia de un caso queda partida entre dos
    iniciativas. Se vio el 2026-08-20 preparando el handoff: los dos paraguas tenían rondas del mismo caso, y
    quien tiene que arreglarlo no puede saber que le falta la mitad.
    """
    from tests.use_cases.e2e.agent import initiative as I, segments as SG, scenarios as SC

    sid = "find-theatre-tickets__es"
    assert not SG.is_completable(sid), "el caso de prueba tiene que estar BLOQUEADO"
    assert I.grouped_for(sid) is not None, "y AGRUPADO"

    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    own = tmp_path / I.GROUPED["find-theatre-tickets"]
    own.write_text("---\nstatus: open\n---\n\n# propio\n", encoding="utf-8")
    (tmp_path / I.BLOCKED_UMBRELLA).write_text("---\nstatus: open\n---\n\n# bloqueados\n", encoding="utf-8")

    res = I.file_failure(
        {"scenario": sid, "tier": 1,
         "run": {"transcript": [], "mechanism_report": {}, "watchdog_log": []},
         "verdict": {"overall": 2, "scores": {}, "veredicto": "narró lo que no pasó",
                     "findings": [], "improvements": []}},
        scenario=SC.registry()[sid], sandboxed=True)

    assert res["initiative"] == own, (
        f"la ronda fue a {res['initiative'].name if res['initiative'] else None} en vez de a su paraguas propio")
    assert "Ronda 1" in own.read_text(encoding="utf-8")
    assert res.get("blocked"), "sigue teniendo que DECIR que está bloqueado, solo cambia dónde escribe"
