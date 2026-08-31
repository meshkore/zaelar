"""`verify.py` used `config` without importing it, and the report called that “the worker failed” (V2-381).

Measured across the 360 reports with a harness report: **49 contained**

    "worker_outcome_error": "name 'config' is not defined"

`verify.worker_bridges()` builds its path with `config.SANDBOX_DB` when it is not passed `logs_dir`, and `run.py`
calls it WITHOUT `logs_dir` — but that module never imported `config`. In other words, that function **has never
run**, and because it crashes inside the large block, everything that came after it —`delivered_by_name`,
`delivery_completeness`, `resets_during_round`— was silently skipped.

And the part that did the most damage is the FIELD NAME. `worker_outcome_error` reads as “the worker failed”, and
it records a failure in our own measurement harness. The two video cases from 2026-08-27 cited it as
evidence against the product:

    “`worker_outcome_error` proves that the code failed before it could act”
    “The internal error 'config not defined' blocked all execution”

Neither is true: the product ran; the instrument broke while measuring it. And the judge had no way to know,
because the field told it the opposite.
"""
import pytest

from tests.use_cases.e2e.agent import judge as J
from tests.use_cases.e2e.agent import verify as V


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


# ── the missing import ──────────────────────────────────────────────────────────────────────────────────────

def test_verify_puede_resolver_su_ruta_por_defecto(tmp_path):
    """The exact defect: `worker_bridges()` without `logs_dir` crashed with NameError before looking at anything."""
    out = V.worker_bridges(since=0)
    assert isinstance(out, dict) and "sessions" in out


def test_verify_IMPORTA_config():
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/verify.py").read_text()
    assert "from . import config, probe_client" in src


def test_la_ruta_explicita_sigue_mandando(tmp_path):
    """`logs_dir` is the path that did work; fixing the defect must not remove it."""
    (tmp_path / "x.jsonl").write_text("", encoding="utf-8")
    out = V.worker_bridges(since=0, logs_dir=str(tmp_path))
    assert out["read"] is True


# ── the field name ─────────────────────────────────────────────────────────────────────────────────────────

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
    """A report missing sections is indistinguishable from one that measured them and found them empty: without
    this, absence is read as a fact (the doctrine of `observability/evidence.py`)."""
    txt = _texto(J.mechanism_facts({"harness_report_error": {
        "error": "boom", "secciones_perdidas": ["delivery_completeness"]}}))
    assert "delivery_completeness" in txt
    assert "su ausencia no prueba nada" in txt


def test_un_informe_SANO_no_dice_nada_de_esto():
    """Sensitivity: a warning that always appears ceases to be a signal."""
    assert "EL ARNÉS se averió" not in _texto(J.mechanism_facts({"results_sheet": {"n_named": 3}}))


def test_se_apuntan_las_secciones_que_SI_se_midieron():
    """The report may call a section “missing” only when it is genuinely absent — otherwise it sends us looking
    for a gap that does not exist."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text()
    assert '"secciones_perdidas": [k for k in ("worker_bridges", "delivered_by_name",' in src
    assert "if k not in _hechas]" in src
