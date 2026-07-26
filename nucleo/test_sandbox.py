#
# Sandbox de ejecución ligero (V2-076 Parte B). Run: .venv/bin/pytest nucleo/test_sandbox.py -q
#
# Certeza de que el código creado se puede EJECUTAR para auditarlo sin comprometer el host de forma casual:
# subproceso aislado (cwd temporal + env scrubbeado + topes + timeout). Soporta Python + SQLite.
#
import os

from nucleo import sandbox


def test_runs_python_and_captures_stdout():
    r = sandbox.run("print('hola sandbox')")
    assert r["ok"] and r["exit"] == 0
    assert "hola sandbox" in r["stdout"]


def test_supports_sqlite():
    code = ("import sqlite3; c=sqlite3.connect(':memory:'); c.execute('create table t(x)'); "
            "c.execute('insert into t values (42)'); print(c.execute('select x from t').fetchone()[0])")
    r = sandbox.run(code)
    assert r["ok"] and "42" in r["stdout"]


def test_error_is_captured_not_raised():
    r = sandbox.run("raise ValueError('boom')")
    assert not r["ok"] and r["exit"] != 0
    assert "ValueError" in r["stderr"] and "boom" in r["stderr"]


def test_timeout_kills_process():
    r = sandbox.run("import time; time.sleep(10)", timeout=1.0)
    assert r["timed_out"] is True and not r["ok"]
    assert r["elapsed_s"] < 5           # se mató pronto, no esperó los 10s


def test_env_is_scrubbed_no_secret_leak():
    os.environ["ZAELAR_SANDBOX_TEST_SECRET"] = "no-debe-verse"
    try:
        r = sandbox.run("import os; print('SECRET=' + repr(os.environ.get('ZAELAR_SANDBOX_TEST_SECRET')))")
        assert "SECRET=None" in r["stdout"]     # el subproceso NO ve los secretos/ZAELAR_* del padre
    finally:
        os.environ.pop("ZAELAR_SANDBOX_TEST_SECRET", None)


def test_runs_in_temp_workdir_not_project():
    r = sandbox.run("import os; print(os.getcwd())")
    cwd = r["stdout"].strip()
    assert "zaelar-sbx-" in cwd            # corre en un dir temporal dedicado, no en la raíz del proyecto


def test_unsupported_lang_degrades():
    r = sandbox.run("fn main(){}", lang="rust")
    assert not r["ok"] and "no soportado" in r["stderr"]


# ── rlimits del dev-worker interactivo (auditoría 2026-07-26, distintos de los de run()) ────────────────────────
def test_dev_worker_rlimits_sets_limits_without_erroring():
    """A diferencia de `_rlimits()` (CPU/wall cortos para un script de un turno), estos NO deben acotar tiempo —
    solo memoria/nproc/fsize. Confirma que el preexec_fn NUNCA revienta el subproceso (cada setrlimit está en su
    propio try/except) y que `RLIMIT_NPROC` (que SÍ se aplica en Linux Y macOS, verificado empíricamente) queda
    realmente fijado. **`RLIMIT_AS` (memoria) NO se comprueba aquí a propósito**: en macOS/Darwin
    `setrlimit(RLIMIT_AS, …)` lanza `ValueError` (Darwin no soporta acotar el address-space) — es un no-op
    silencioso ahí, honesto en el docstring de `dev_worker_rlimits()`, no un fallo de este test."""
    import subprocess
    import sys

    apply_fn = sandbox.dev_worker_rlimits()
    if apply_fn is None:
        return   # Windows u otra plataforma sin `resource` — mismo límite honesto que _rlimits()
    code = "import resource; print(resource.getrlimit(resource.RLIMIT_NPROC)[0])"
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       preexec_fn=apply_fn, timeout=10)
    assert p.returncode == 0
    assert str(sandbox._DEV_NPROC) in p.stdout


def test_dev_worker_rlimits_compatible_with_start_new_session():
    """No debe chocar con `start_new_session=True` (claude_session.py SIEMPRE lo usa, para el killpg de grupo) —
    reproduce la MISMA combinación en un subproceso real y aislado (nunca en el propio proceso del test: aplicar
    un rlimit de memoria/nproc al runner de pytest rompería el resto de la suite)."""
    import subprocess
    import sys

    apply_fn = sandbox.dev_worker_rlimits()
    if apply_fn is None:
        return
    p = subprocess.run([sys.executable, "-c", "print('ok')"], capture_output=True, text=True,
                       preexec_fn=apply_fn, start_new_session=True, timeout=10)
    assert p.returncode == 0 and "ok" in p.stdout
