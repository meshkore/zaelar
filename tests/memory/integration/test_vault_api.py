#
# test_vault_api.py — ciclo completo de la bóveda por HTTP (V2-060): crear → guardar → bloqueada pide passphrase →
# desbloquear/revelar. Es el camino que conduce el TESTER (dominio «seguridad de datos», sin biometría) y el modal
# nativo del frontend. Router aislado (sin lifespan pesado). Sin red (embeddings hash).
# Ejecutar: .venv/bin/pytest tests/integration/test_vault_api.py
#
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memory import db as memdb
from memory import embeddings as mememb
from memory import vault
from memory.vault_api import router as vault_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    from nacl import pwhash
    monkeypatch.setattr(vault, "_OPS", pwhash.argon2id.OPSLIMIT_MIN, raising=False)
    monkeypatch.setattr(vault, "_MEM", pwhash.argon2id.MEMLIMIT_MIN, raising=False)
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    vault.lock()
    app = FastAPI()
    app.include_router(vault_router)
    with TestClient(app) as c:
        yield c
    vault.lock()
    memdb.reset_db()
    mememb.reset()


def test_full_cycle(client):
    # 1) al principio no hay bóveda
    assert client.get("/api/vault/status").json()["exists"] is False

    # 2) crear
    r = client.post("/api/vault/create", json={"passphrase": "clave-maestra"})
    assert r.status_code == 200 and r.json()["exists"] is True

    # 3) guardar un secreto (por la vía directa del vault; el auto-vaulting conversacional es F1)
    mid = vault.store_secret("contraseña de Netflix", "Perrito123", slot="secret:netflix:password")

    # 4) el listado da la etiqueta, nunca el valor
    secs = client.get("/api/vault/secrets").json()["secrets"]
    assert any(s["label"] == "contraseña de Netflix" for s in secs)
    assert all("value" not in s for s in secs)

    # 5) bloqueada → revelar responde 423 (el frontend abre el modal)
    vault.lock()
    r = client.post("/api/vault/reveal", json={"memory_id": mid})
    assert r.status_code == 423

    # 6) desbloquear con passphrase → revelar da el valor
    r = client.post("/api/vault/unlock", json={"passphrase": "clave-maestra"})
    assert r.json()["ok"] is True and r.json()["unlocked"] is True
    r = client.post("/api/vault/reveal", json={"memory_id": mid})
    assert r.status_code == 200 and r.json()["value"] == "Perrito123"


def test_unlock_wrong_passphrase(client):
    client.post("/api/vault/create", json={"passphrase": "buena"})
    r = client.post("/api/vault/unlock", json={"passphrase": "mala"})
    assert r.json()["ok"] is False and r.json()["unlocked"] is False


def test_reveal_transient_strict_mode(client):
    client.post("/api/vault/create", json={"passphrase": "maestra"})
    mid = vault.store_secret("clave wifi", "RouterCasa2024", slot="secret:wifi:password")
    vault.lock()
    # modo estricto: passphrase en la propia petición, no cachea
    r = client.post("/api/vault/reveal", json={"memory_id": mid, "passphrase": "maestra"})
    assert r.status_code == 200 and r.json()["value"] == "RouterCasa2024"
    assert client.get("/api/vault/status").json()["unlocked"] is False


def test_passkey_enroll_and_unlock_over_http(client):
    import os
    from base64 import b64encode
    client.post("/api/vault/create", json={"passphrase": "maestra"})
    mid = vault.store_secret("clave", "ValorPasskey", slot="secret:x:password")
    prf = b64encode(os.urandom(32)).decode()
    # enrolar sin desbloquear → 423
    assert client.post("/api/vault/passkey/enroll", json={"cred_id": "c1", "prf_secret": prf}).status_code == 423
    # desbloquea (passphrase), enrola el aparato, bloquea, desbloquea SOLO con el PRF
    client.post("/api/vault/unlock", json={"passphrase": "maestra"})
    assert client.post("/api/vault/passkey/enroll", json={"cred_id": "c1", "prf_secret": prf}).status_code == 200
    ch = client.get("/api/vault/passkey/challenge").json()
    assert ch["prf_salt"] and "c1" in ch["cred_ids"]
    client.post("/api/vault/lock")
    assert client.post("/api/vault/passkey/unlock", json={"prf_secret": prf}).json()["ok"] is True
    assert client.post("/api/vault/reveal", json={"memory_id": mid}).json()["value"] == "ValorPasskey"


def test_change_passphrase(client):
    client.post("/api/vault/create", json={"passphrase": "vieja"})
    mid = vault.store_secret("clave", "dato", slot="secret:x:password")
    r = client.post("/api/vault/change", json={"old": "vieja", "new": "nueva"})
    assert r.status_code == 200
    assert client.post("/api/vault/unlock", json={"passphrase": "vieja"}).json()["ok"] is False
    assert client.post("/api/vault/unlock", json={"passphrase": "nueva"}).json()["ok"] is True
    assert client.post("/api/vault/reveal", json={"memory_id": mid}).json()["value"] == "dato"
