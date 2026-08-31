#
# test_vault_ingest.py — auto-vaulting during ingestion (V2-060 F1): a turn containing a secret is ENCRYPTED and REDACTED
# before the distiller; without a vault it asks to create one; the value never reaches the LLM or a plaintext pill.
# No network (hash embeddings; mem_processor forced OFF to isolate the heuristic).
# Run: .venv/bin/pytest tests/memory/unit/test_vault_ingest.py
#
import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import vault
from nucleo import memory_agent


def _ingest(text):
    return asyncio.run(memory_agent.ingest_utterance(text))


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    # Turn off the LLM CORE (no network): ingestion falls back to the heuristic, which is sufficient for the secret gate
    monkeypatch.setenv("MEM_PROCESSOR", "0")
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


def _all_text():
    rows = memdb.get_db().query("SELECT text, meta FROM memories")
    return " ".join((r["text"] or "") + " " + (r["meta"] or "") for r in rows)


def test_secret_without_vault_asks_to_create(fresh_db):
    res = _ingest("guárdame la contraseña de Netflix, es Perrito123")
    assert res["source"] == "secret_needs_vault"
    # NOTHING in plaintext: not even a pill containing the value
    assert "Perrito123" not in _all_text()


def test_secret_with_vault_is_encrypted(fresh_db):
    vault.create("clave-maestra")
    res = _ingest("guárdame la contraseña de Netflix, es Perrito123")
    assert res["source"] == "vault" and res["atoms"] == 1
    # encrypted and recoverable
    assert vault.status()["secret_count"] == 1
    assert vault.unlock("clave-maestra")
    secs = vault.list_secrets()
    assert vault.open_secret(secs[0]["memory_id"]) == "Perrito123"
    # the value is never in plaintext in memories or in the ciphertext
    assert "Perrito123" not in _all_text()
    ct = memdb.get_db().query_one("SELECT ciphertext FROM vault_secrets")["ciphertext"]
    assert b"Perrito123" not in bytes(ct)


def test_plain_utterance_not_vaulted(fresh_db):
    vault.create("clave")
    res = _ingest("me encanta el senderismo los domingos")
    assert res["source"] != "vault"
    assert vault.status()["secret_count"] == 0
