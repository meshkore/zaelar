#
# test_vault_flow.py — flujo de LECTURA de secretos del FlashBrain (V2-060 F1b): resolución difusa de etiqueta +
# los desenlaces (no_vault/empty/not_found/locked/ok). El valor solo en 'ok'. Sin red (embeddings hash).
# Ejecutar: .venv/bin/pytest tests/memory/unit/test_vault_flow.py
#
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import vault
from nucleo.flash import router, vault_flow


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    from nacl import pwhash
    monkeypatch.setattr(vault, "_OPS", pwhash.argon2id.OPSLIMIT_MIN, raising=False)
    monkeypatch.setattr(vault, "_MEM", pwhash.argon2id.MEMLIMIT_MIN, raising=False)
    memdb.reset_db()
    memdb.get_db()
    vault.lock()
    yield
    vault.lock()
    memdb.reset_db()


# ── la tool está en el router ──────────────────────────────────────────────────────────────────────────────
def test_reveal_tool_registered():
    names = {t["function"]["name"] for t in router.tools()}
    assert "reveal_secret" in names
    assert router.decide("reveal_secret", {"label": "netflix"}).kind == router.REVEAL


# ── desenlaces ───────────────────────────────────────────────────────────────────────────────────────────
def test_no_vault(fresh_db):
    assert vault_flow.reveal("la contraseña de Netflix")["status"] == "no_vault"


def test_empty(fresh_db):
    vault.create("clave")
    assert vault_flow.reveal("la contraseña de Netflix")["status"] == "empty"


def test_locked(fresh_db):
    vault.create("clave")
    vault.store_secret("contraseña de Netflix", "Perrito123", slot="secret:netflix:password")
    vault.lock()
    r = vault_flow.reveal("dame la contraseña de Netflix")
    assert r["status"] == "locked" and r["label"] == "contraseña de Netflix"
    assert "value" not in r                     # jamás el valor en 'locked'


def test_ok_returns_value_when_unlocked(fresh_db):
    vault.create("clave")
    vault.store_secret("contraseña de Netflix", "Perrito123", slot="secret:netflix:password")
    vault.unlock("clave")
    r = vault_flow.reveal("dame la contraseña de Netflix")
    assert r["status"] == "ok" and r["value"] == "Perrito123"


def test_not_found_when_no_match(fresh_db):
    vault.create("clave")
    vault.store_secret("contraseña de Netflix", "x", slot="secret:netflix:password")
    vault.unlock("clave")
    r = vault_flow.reveal("dame la clave de mi banco Santander")
    assert r["status"] == "not_found"
    assert "contraseña de Netflix" in r["candidates"]


# ── resolución difusa ─────────────────────────────────────────────────────────────────────────────────────
def test_resolve_picks_right_service(fresh_db):
    vault.create("clave")
    vault.unlock("clave")
    vault.store_secret("contraseña de Netflix", "n", slot="secret:netflix:password")
    vault.store_secret("contraseña de Spotify", "s", slot="secret:spotify:password")
    vault.store_secret("clave del wifi de casa", "w", slot="secret:wifi:password")
    assert vault_flow.reveal("pásame la de spotify")["value"] == "s"
    assert vault_flow.reveal("la clave del wifi")["value"] == "w"
    assert vault_flow.reveal("dame la contraseña de netflix")["value"] == "n"
