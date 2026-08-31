#
# test_vault_rules.py — user rules HARDENED for security (V2-060 F2): detection of voice config commands +
# application (persistence in state.security). No network. Run: .venv/bin/pytest tests/memory/unit/test_vault_rules.py
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


# ── detection ─────────────────────────────────────────────────────────────────────────────────────────────
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


# ── application + persistence ───────────────────────────────────────────────────────────────────────────
def test_apply_persists_flag(fresh_db):
    assert mstate.security_flag("secrets_voice", True) is True     # convenient default
    off = vault_rules.apply(("secrets_voice", False))
    assert mstate.security_flag("secrets_voice", True) is False    # persisted
    on = vault_rules.apply(("secrets_voice", True))
    assert mstate.security_flag("secrets_voice", True) is True
    # The confirmation is LOCALIZED (`apply` translates it according to the operator's language), so here we only
    # check the language-agnostic contract: that it confirms something and that the two directions do NOT say the same thing.
    # Previously, the assertion was `"no" in off.lower()` —true only in Spanish— and the test failed when the
    # product began starting in ENGLISH by default (c615ee4): a test failure, not a code failure.
    assert off.strip() and on.strip()
    assert off != on


def test_security_flag_isolated_from_style_rules(fresh_db):
    # security rules do NOT touch style rules (state.rules), nor vice versa
    mstate.set_security_flag("secrets_voice", False)
    st = mstate.read()
    assert st["security"]["secrets_voice"] is False
    assert st["rules"] == []
