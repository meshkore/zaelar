"""`verify.py` usaba `config` sin importarlo, y el informe llamaba a eso «el worker falló» (V2-381).

Medido sobre los 360 informes con informe de mecanismo del plató: **49 llevaban**

    "worker_outcome_error": "name 'config' is not defined"

`verify.worker_bridges()` compone su ruta con `config.SANDBOX_DB` cuando no le pasan `logs_dir`, y `run.py` la
llama SIN `logs_dir` — pero ese módulo nunca importó `config`. O sea que esa función **no ha corrido jamás**, y
como revienta dentro del bloque grande, todo lo que venía detrás —`delivered_by_name`,
`delivery_completeness`, `resets_during_round`— se saltaba en silencio.

Y la mitad que más daño hizo es el NOMBRE DEL CAMPO. `worker_outcome_error` se lee como «el worker falló», y
guarda una avería de nuestro propio bloque de medición. Los dos casos de vídeo del 2026-08-27 lo citaron como
prueba del producto:

    «El `worker_outcome_error` prueba que el código falló antes de poder actuar»
    «El error interno 'config not defined' bloqueó toda ejecución»

Ninguna de las dos es cierta: el producto corrió; se rompió el instrumento mientras lo medía. Y el juez no
tenía forma de saberlo, porque el campo le decía lo contrario.
"""
import pytest

from tests.use_cases.e2e.agent import judge as J
from tests.use_cases.e2e.agent import verify as V


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


# ── el import que faltaba ──────────────────────────────────────────────────────────────────────────────────

def test_verify_puede_resolver_su_ruta_por_defecto(tmp_path):
    """El defecto exacto: `worker_bridges()` sin `logs_dir` reventaba con NameError antes de mirar nada."""
    out = V.worker_bridges(since=0)
    assert isinstance(out, dict) and "sessions" in out


def test_verify_IMPORTA_config():
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/verify.py").read_text()
    assert "from . import config, probe_client" in src


def test_la_ruta_explicita_sigue_mandando(tmp_path):
    """`logs_dir` es el camino que sí funcionaba; arreglar el defecto no puede quitarlo."""
    (tmp_path / "x.jsonl").write_text("", encoding="utf-8")
    out = V.worker_bridges(since=0, logs_dir=str(tmp_path))
    assert out["read"] is True


# ── el nombre del campo ────────────────────────────────────────────────────────────────────────────────────

def test_el_campo_ya_no_dice_que_falló_el_worker():
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text()
    assert 'mech["harness_report_error"]' in src
    assert 'mech["worker_outcome_error"]' not in src


def test_el_juez_lo_lee_como_AVERIA_DEL_ARNES():
    txt = _texto(J.mechanism_facts({"harness_report_error": {
        "error": "name 'config' is not defined", "es_del_arnes": True,
        "secciones_perdidas": ["worker_bridges", "resets_during_round"]}}))
    assert "EL ARNÉS se averió" in txt
    assert "NO es un fallo del producto" in txt and "NO se puntúa" in txt


def test_el_juez_DICE_qué_secciones_faltan():
    """Un informe al que le faltan secciones es indistinguible de uno que las midió y salieron vacías: sin
    esto, la ausencia se lee como un hecho (doctrina de `observability/evidence.py`)."""
    txt = _texto(J.mechanism_facts({"harness_report_error": {
        "error": "boom", "secciones_perdidas": ["delivery_completeness"]}}))
    assert "delivery_completeness" in txt
    assert "su ausencia no prueba nada" in txt


def test_un_informe_SANO_no_dice_nada_de_esto():
    """Sensibilidad: un aviso que sale siempre deja de ser señal."""
    assert "EL ARNÉS se averió" not in _texto(J.mechanism_facts({"results_sheet": {"n_named": 3}}))


def test_se_apuntan_las_secciones_que_SI_se_midieron():
    """El parte solo puede llamar «perdida» a una sección que de verdad falte — si no, manda a buscar un
    hueco que no existe."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text()
    assert '"secciones_perdidas": [k for k in ("worker_bridges", "delivered_by_name",' in src
    assert "if k not in _hechas]" in src
