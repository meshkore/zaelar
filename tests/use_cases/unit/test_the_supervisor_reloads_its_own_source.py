"""A Python process does not reread its own file (V2-372).

The supervisor had been running the 07:59 code since 08:03, so TWO fixes made that
same morning remained inert without anything saying so:

    09:42  V2-363 — una avería del arnés no es un caso que falla
    10:12  V2-367 — los 103 escenarios que nunca habían corrido entran en la rotación

Measured at 11:00: the `things-to-do-nearby-weekend__es` round is INFRA in its own report—the judge did not
return JSON after three attempts, the conversation had gone well and was saved in `pending/`—and the diary
recorded it as **FAIL**, exactly what V2-363 had fixed three hours earlier. And the rotation was still the
32-scenario one, not the 132-scenario one.

What makes it SILENT is the asymmetry: `una_ronda` launches the round as a SUBPROCESS, so the runner, the judge,
the scenarios, and the entire engine DO reload on every cycle. The only thing left behind is this file—the one
that CLASSIFIES the result and CHOOSES the order. From the outside everything looks up to date, and the report
even carries the `sha` of HEAD read when the round began: **the diary claims to have measured a commit whose
classifier was not loaded.**

Fourth time in the same family (“a clean tree is not an up-to-date process”) and the first in which the one
that pays the price is the instrument used to decide where to work.
"""
import pytest

from tests.use_cases.e2e.agent import supervisor as S


@pytest.fixture
def espia(monkeypatch):
    """Replaces the IRREVERSIBLE part (the re-exec) and the shared part (the diary) with witnesses."""
    visto = {"exec": None, "diario": []}
    monkeypatch.setattr(S.os, "execv", lambda *a: visto.__setitem__("exec", a))
    monkeypatch.setattr(S, "_apunta", lambda **f: visto["diario"].append(f))
    monkeypatch.setattr(S, "_sha", lambda: "abc1234")
    return visto


def test_la_fuente_INTACTA_no_reinicia_nada(espia, monkeypatch):
    monkeypatch.setattr(S, "_huella", lambda: "misma")
    S._recargar_si_cambie("misma")
    assert espia["exec"] is None
    assert espia["diario"] == []


def test_la_fuente_CAMBIADA_se_recarga(espia, monkeypatch):
    monkeypatch.setattr(S, "_huella", lambda: "nueva")
    monkeypatch.setattr(S, "_fuente_utilizable", lambda: True)
    S._recargar_si_cambie("vieja")
    assert espia["exec"] is not None
    assert "tests.use_cases.e2e.agent.supervisor" in espia["exec"][1]


def test_la_recarga_DEJA_RASTRO_en_el_diario(espia, monkeypatch):
    """A silent restart turns “I have been measuring for three hours” into an impossible-to-audit claim:
    whoever reads the diary must be able to see where the code being used for measurement changed."""
    monkeypatch.setattr(S, "_huella", lambda: "nueva")
    monkeypatch.setattr(S, "_fuente_utilizable", lambda: True)
    S._recargar_si_cambie("vieja")
    (fila,) = espia["diario"]
    assert fila["resultado"] == "RECARGA"
    assert "vieja" in fila["motivo"] and "nueva" in fila["motivo"]


def test_una_fuente_ROTA_no_mata_el_bucle(espia, monkeypatch):
    """The loop must not stop—it is the only requirement the operator has repeated. Re-executing over a
    half-written file would do exactly that, and measuring with stale code is a worse defect than going without
    measurement only if one believes the two things cost the same. They do not cost the same."""
    monkeypatch.setattr(S, "_huella", lambda: "nueva")
    monkeypatch.setattr(S, "_fuente_utilizable", lambda: False)
    S._recargar_si_cambie("vieja")
    assert espia["exec"] is None
    assert espia["diario"] == []


def test_una_huella_ILEGIBLE_tampoco_reinicia(espia, monkeypatch):
    """`_huella()` returns "" if the file cannot be read. Treating that as “it changed” would restart in a loop."""
    monkeypatch.setattr(S, "_huella", lambda: "")
    S._recargar_si_cambie("vieja")
    assert espia["exec"] is None


def test_sin_huella_inicial_no_se_hace_nada(espia, monkeypatch):
    monkeypatch.setattr(S, "_huella", lambda: "nueva")
    S._recargar_si_cambie("")
    assert espia["exec"] is None


# ── lo que la fuente REAL tiene que cumplir ────────────────────────────────────────────────────────────────

def test_la_fuente_real_compila_y_tiene_huella():
    assert S._fuente_utilizable() is True
    assert len(S._huella()) == 12


def test_la_recarga_va_ENTRE_rondas_y_nunca_dentro():
    """In the middle of a round there is a live subprocess with its browser: re-executing there would orphan it and
    the round would be lost. The place is after the `sleep`, with the cycle already closed.

    Rewritten 2026-08-28, NOT flipped: the anchor was the EXACT text `una_ronda(esc)` and broke when the
    studio was passed in the call (`una_ronda(esc, plato_de(esc))`, node 10.104). The protected property—the
    round → sleep → reload order—did not change one bit; what changed is that the CALL is now sought rather than
    one of its possible signatures, so the next argument does not bring down a test that is not about that.
    """
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text()
    i_ronda, i_sleep, i_rec = (src.index("parte = una_ronda(esc"), src.index("time.sleep(PAUSA_S)"),
                               src.index("_recargar_si_cambie(_mia)"))
    assert i_ronda < i_sleep < i_rec


def test_el_arranque_DICE_con_qué_fuente_corre():
    """Without this line, “I have been measuring for three hours” and “I have been measuring for three hours
    with the code from three hours ago” look exactly the same in the operator's terminal."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text()
    assert "fuente {_mia}" in src and "HEAD {_sha()}" in src


# ── 24/7: what starts the supervisor and starts it again (V2-417) ───────────────────────────────────────
# It is a shell script and a plist, meaning exactly what breaks WITHOUT MAKING A SOUND: a failed `exec` leaves
# launchd watching a dead parent, a lock without a real check leaves two supervisors fighting over ONE browser, and
# a `cd` with one level too many leaves the wrapper starting from the wrong directory. None of that raises an alert.

_OPS = "tests/use_cases/e2e/agent/ops"
_ENV = "tests/use_cases/e2e/agent/supervisor_24x7.sh"


def _lee(ruta: str) -> str:
    from pathlib import Path
    return Path(ruta).read_text(encoding="utf-8")


def test_los_tres_ficheros_del_247_existen_y_son_ejecutables():
    import os
    from pathlib import Path
    for ruta in (_ENV, f"{_OPS}/keepalive.sh"):
        assert Path(ruta).exists(), f"falta {ruta}"
        assert os.access(ruta, os.X_OK), f"{ruta} no es ejecutable — launchd/el guardián fallan con 127"
    assert Path(f"{_OPS}/com.zaelar.usecases.supervisor.plist").exists()


def test_el_envoltorio_entra_al_bucle_con_exec():
    """Without `exec`, the watcher (launchd or the guardian) watches a parent shell that has already finished, and the
    supervisor is left orphaned with no one to bring it back when it dies—which is exactly what it exists for."""
    src = _lee(_ENV)
    assert "exec caffeinate" in src and "exec ./.venv/bin/python" in src


def test_el_envoltorio_levanta_los_platos_antes_del_bucle():
    """After a restart there is no live studio. A supervisor against dead ports does not fail: it writes an
    INFRA row for every scenario in the rotation at full speed, which is worse than being stopped."""
    src = _lee(_ENV)
    # The line has to EXECUTE, not merely appear. Measured while dismantling it on 2026-08-28: commenting it out
    # left the test green despite the defect, because the text was still there inside the comment.
    viva = [l for l in src.splitlines() if "tests.use_cases.lab up all" in l and not l.lstrip().startswith("#")]
    assert viva, "el envoltorio tiene que levantar los platós, no mencionarlos"
    assert src.index(viva[0]) < src.index("exec caffeinate")


def test_el_candado_del_guardian_se_comprueba_contra_el_proceso():
    """A lone PID file is NOT enough: a killed guardian leaves its own behind and blocks forever.
    And two guardians are two supervisors fighting over each studio's only browser."""
    src = _lee(f"{_OPS}/keepalive.sh")
    assert "kill -0" in src, "el candado tiene que preguntarle al SO si ese pid sigue vivo"
    assert "trap" in src and "rm -f" in src, "y soltarse al salir"


def test_el_plist_vigila_de_verdad():
    src = _lee(f"{_OPS}/com.zaelar.usecases.supervisor.plist")
    assert "<key>KeepAlive</key>" in src and "<key>RunAtLoad</key>" in src
    assert "<key>ThrottleInterval</key>" in src, ("sin respiro, un arranque que falla en bucle llena el "
                                                 "disco de logs en minutos")


def test_esta_escrito_por_que_launchd_no_basta_hoy():
    """The next person who reads this will try the plist. Let them find out here, not after half an hour: the repo
    lives under ~/Documents and TCC denies read access to a launchd agent (measured: `127 · can't open input
    file` for a file that exists and is executable)."""
    src = _lee(f"{_OPS}/keepalive.sh")
    assert "TCC" in src and "Documents" in src and "127" in src
