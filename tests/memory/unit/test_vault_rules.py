#
# test_vault_rules.py — user rules DURAS de seguridad (V2-060 F2): detección de comandos de config por voz +
# aplicación (persistencia en state.security). Sin red. Ejecutar: .venv/bin/pytest tests/unit/memory/test_vault_rules.py
#
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import state as mstate
from nucleo.flash import vault_rules


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


# ── detección ─────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("txt", [
    "no me digas los secretos por voz",
    "no leas mis contraseñas en voz alta",
    "nunca digas mis claves por voz",
    "modo máxima seguridad",
    "muéstrame los secretos solo en pantalla",
])
def test_detect_no_voice(txt):
    assert vault_rules.detect(txt) == ("secrets_voice", False)


@pytest.mark.parametrize("txt", [
    "puedes decirme los secretos por voz",
    "léeme las contraseñas en voz alta",
])
def test_detect_yes_voice(txt):
    assert vault_rules.detect(txt) == ("secrets_voice", True)


@pytest.mark.parametrize("txt", [
    "dame la contraseña de Netflix",
    "qué tiempo hace hoy",
    "abre el reloj",
])
def test_detect_none_on_normal(txt):
    assert vault_rules.detect(txt) is None


def test_detect_english():
    assert vault_rules.detect("don't read my secrets out loud") == ("secrets_voice", False)


# ── aplicación + persistencia ───────────────────────────────────────────────────────────────────────────
def test_apply_persists_flag(fresh_db):
    assert mstate.security_flag("secrets_voice", True) is True     # default cómodo
    line = vault_rules.apply(("secrets_voice", False))
    assert "no" in line.lower()
    assert mstate.security_flag("secrets_voice", True) is False    # persistió
    vault_rules.apply(("secrets_voice", True))
    assert mstate.security_flag("secrets_voice", True) is True


def test_security_flag_isolated_from_style_rules(fresh_db):
    # las reglas de seguridad NO tocan las de estilo (state.rules) ni al revés
    mstate.set_security_flag("secrets_voice", False)
    st = mstate.read()
    assert st["security"]["secrets_voice"] is False
    assert st["rules"] == []
