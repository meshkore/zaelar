"""V2-459 — three agents on this machine, three ports, and none of them moves.

The operator returned to `http://127.0.0.1:43921/` expecting to find the ES agent there, but nothing was
listening. It was not a startup failure: that address existed only for `--lab`, while the unattended batch
(`--sandbox`) started at `preferred_port(43918)` — ONE number for both languages, and on top of that one
that slid to an ephemeral port when it was occupied. So «the Spanish agent» had two addresses depending on
which command had started it, and the sliding one had none: the round ran wherever it fit and nobody could
watch it.

What is locked down here is exactly what the operator asked for — that ports remain consistent from one
run to the next:

  · a single table (`tests/platform/ports.py`), not a number in every place that needs one,
  · the port comes from the case LANGUAGE, not from whoever started the batch, and
  · an occupied port is an ERROR that says who has it, never a reason to move.
"""
from __future__ import annotations

import argparse
import contextlib
import pathlib
import re

import pytest

from tests.platform import ports as PORTS

ENGINE = pathlib.Path(__file__).resolve().parents[3]


# ── the table ───────────────────────────────────────────────────────────────────────────────────────────
def test_son_tres_y_estos_son_sus_numeros():
    """Intentionally hard-coded: the operator has them in browser bookmarks, so changing one
    must require touching a test that explains why, not editing a pass-through constant."""
    assert PORTS.OPERATOR == 43917
    assert PORTS.SANDBOX_ES == 43921
    assert PORTS.SANDBOX_US == 43922
    assert set(PORTS.AGENTS) == {"operator", "es", "us"}
    assert len(set(PORTS.AGENTS.values())) == 3, "dos agentes en el mismo puerto es uno solo, y a ratos"


def test_el_puerto_del_operador_es_EL_QUE_EL_MOTOR_ARRANCA_SOLO():
    """The row this table does not control: `server/__main__.py` decides 43917. If someone changes the
    default there, the sandbox could end up fighting with the operator installation — and that collision is
    paid for with a person's work session, not a red test."""
    src = (ENGINE / "server" / "__main__.py").read_text(encoding="utf-8")
    m = re.search(r'os\.getenv\("PORT",\s*"(\d+)"\)', src)
    assert m, "no encuentro el puerto por defecto del motor en server/__main__.py"
    assert int(m.group(1)) == PORTS.OPERATOR


def test_el_puerto_sale_del_IDIOMA_y_entiende_las_dos_formas_de_decirlo():
    """The catalog says `es`/`us`; the engine says `ZAELAR_LANGUAGE=es`/`en`. Both pass through this harness and
    a mapping that understood only one would send half the rounds to the other country's agent — exactly the
    failure that justifies having two agents (see the header of lab/profiles.py)."""
    for spanish in ("es", "es-ES", "ES"):
        assert PORTS.sandbox_port(spanish) == PORTS.SANDBOX_ES, spanish
    for english in ("us", "en", "en-US", ""):
        assert PORTS.sandbox_port(english) == PORTS.SANDBOX_US, english


def test_el_laboratorio_LEE_la_tabla_en_vez_de_tener_su_propia_copia():
    """Two copies of the same number diverge, and divergence here means the operator opens the port they
    remember and finds something else. Both the value AND the source are checked: matching by coincidence
    today proves nothing."""
    from tests.use_cases.lab import profiles as LP
    assert LP.ES.port == PORTS.SANDBOX_ES and LP.US.port == PORTS.SANDBOX_US
    src = (ENGINE / "tests" / "use_cases" / "lab" / "profiles.py").read_text(encoding="utf-8")
    assert "ports.SANDBOX_ES" in src and "ports.SANDBOX_US" in src
    assert not re.search(r"port\s*=\s*\d{4,5}", src), "un literal de puerto ha vuelto a profiles.py"


# ── the unattended batch ────────────────────────────────────────────────────────────────────────────────
def _scn(locale: str):
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id=f"x__{locale}", locale=locale, tier=1, persona_brief="p",
                              opening_line="o", success_checks="s")


def _boot_port(monkeypatch, tmp_path, locale: str) -> int:
    """Starts `_sandbox_batch` with a fake engine and returns the port it REQUESTED."""
    from tests.use_cases.e2e.agent import config, run as R
    import tests.platform.sandbox_engine as SE

    got: dict = {}

    @contextlib.contextmanager
    def _fake_engine(**kw):
        got["port"] = kw.get("port")
        yield type("E", (), {"base_url": "http://x", "workspace": tmp_path,
                             "new_widget_dirs": lambda self=None: [],
                             "log_tail": lambda self=None, n=0: ""})()

    config._CODE_STAMP = None
    config._MACHINE_STAMP = None
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "abc1234", "n_dirty": 0, "dirty": []})
    monkeypatch.setattr(config, "machine_stamp", lambda: {"n": 0})
    monkeypatch.setattr(SE, "sandbox_engine", _fake_engine)
    monkeypatch.setattr(PORTS, "busy_refusal", lambda port, **kw: "")
    monkeypatch.setattr(R, "brain_preflight", lambda **kw: "")
    monkeypatch.setattr(R, "bridge_allowlist_refusal", lambda **kw: "")
    monkeypatch.setattr(R, "_run_batch", lambda *a, **k: 0)
    R._sandbox_batch([_scn(locale)], argparse.Namespace(no_file=True, stop_after_failures=0))
    return got["port"]


def test_una_tanda_ES_arranca_en_43921_y_una_US_en_43922(monkeypatch, tmp_path):
    """The operator's exact scenario: they open 43921 while the Spanish batch runs and watch the agent work.
    Previously both landed on the same 43918 (when they landed there)."""
    assert _boot_port(monkeypatch, tmp_path, "es") == PORTS.SANDBOX_ES
    assert _boot_port(monkeypatch, tmp_path, "us") == PORTS.SANDBOX_US


def test_un_puerto_OCUPADO_para_la_tanda_en_vez_de_mudarla(monkeypatch, tmp_path):
    """The part that really locks it down: without this, «the port is fixed» lasts until the first orphan.

    It exits with 4 (CANNOT MEASURE) rather than 3 (MUST NOT, dirty tree): the batch has not been forbidden,
    it has been blocked, and whoever reads the log needs to distinguish them.
    """
    from tests.use_cases.e2e.agent import config, run as R
    import tests.platform.sandbox_engine as SE

    @contextlib.contextmanager
    def _never(**kw):  # pragma: no cover — must never reach startup
        raise AssertionError("arrancó un motor con el puerto ocupado")
        yield

    config._CODE_STAMP = None
    config._MACHINE_STAMP = None
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "abc1234", "n_dirty": 0, "dirty": []})
    monkeypatch.setattr(config, "machine_stamp", lambda: {"n": 0})
    monkeypatch.setattr(SE, "sandbox_engine", _never)
    monkeypatch.setattr(PORTS, "busy_refusal", lambda port, **kw: f"OCUPADO {port}")
    with pytest.raises(SystemExit) as e:
        R._sandbox_batch([_scn("es")], argparse.Namespace(no_file=True, stop_after_failures=0))
    assert e.value.code == 4


def test_la_negativa_dice_QUIEN_tiene_el_puerto_y_como_seguir():
    """A bare EADDRINUSE sends someone searching from scratch. With three agents on the machine, what needs
    to be known is WHICH TWO are fighting and what to do about it."""
    ocupado = PORTS.busy_refusal(PORTS.SANDBOX_ES, want="el sandbox ES de esta tanda")
    if not ocupado:                       # the ES agent is not running on this machine right now
        ocupado = PORTS.busy_refusal(PORTS.OPERATOR, want="el sandbox ES de esta tanda")
    if not ocupado:
        pytest.skip("ningún puerto conocido está ocupado en esta máquina; la forma del mensaje se ve abajo")
    assert "OCUPADO" in ocupado and "lsof" in ocupado
    assert "el sandbox ES de esta tanda" in ocupado, "no dice qué se quería levantar"


def test_un_puerto_LIBRE_no_inventa_una_negativa():
    """The sensitivity counterpart to the case above: without this, a `busy_refusal` that always returned text
    would stop every batch and both cases would pass anyway."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        libre = s.getsockname()[1]
    assert PORTS.busy_refusal(libre, want="lo que sea") == ""
    assert PORTS.holder(libre) == ""


def test_ya_no_queda_forma_de_DESLIZARSE_a_otro_puerto():
    """The ratchet. `preferred_port()` was the function that did exactly what the operator prohibited, and
    as long as it exists someone will call it again «just so startup does not fail»."""
    import tests.platform.sandbox_engine as SE
    assert not hasattr(SE, "preferred_port")
    src = (ENGINE / "tests" / "use_cases" / "e2e" / "agent" / "run.py").read_text(encoding="utf-8")
    boot = src[src.index("def _sandbox_batch"):]
    boot = boot[:boot.index("\ndef ", 10)]
    # Without comments: the explanation of WHY sliding was removed names the removed function, and
    # a ratchet triggered by its own obituary is not a ratchet.
    codigo = "\n".join(l for l in boot.splitlines() if not l.strip().startswith("#"))
    assert "free_port" not in codigo and "preferred_port(" not in codigo
    assert "ports.sandbox_port(" in codigo, "el puerto tiene que salir de la tabla, no de un número aquí"
