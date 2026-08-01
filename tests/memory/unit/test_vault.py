#
# test_vault.py — bóveda de secretos cifrados (V2-060): crypto asimétrica + sobre passphrase, storage partido,
# supersede, invariantes (valor jamás en claro en `memories`). Sin red (embeddings hash).
# Ejecutar: .venv/bin/pytest tests/memory/unit/test_vault.py
#
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import vault


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    # KDF rápido en tests (Argon2id MODERATE tarda ~0.7s; INTERACTIVE/MIN es de sobra para el test)
    from nacl import pwhash
    monkeypatch.setattr(vault, "_OPS", pwhash.argon2id.OPSLIMIT_MIN, raising=False)
    monkeypatch.setattr(vault, "_MEM", pwhash.argon2id.MEMLIMIT_MIN, raising=False)
    memdb.reset_db()
    memdb.get_db()
    vault.lock()
    yield
    vault.lock()
    memdb.reset_db()


# ── ciclo de vida ──────────────────────────────────────────────────────────────────────────────────────────
def test_create_and_status(fresh_db):
    assert not vault.exists()
    vault.create("mi-passphrase-secreta")
    assert vault.exists()
    st = vault.status()
    assert st["exists"] and st["methods"] == ["passphrase"] and st["secret_count"] == 0
    assert st["unlocked"] is False


def test_create_twice_errors(fresh_db):
    vault.create("passphrase-1")
    with pytest.raises(vault.VaultError):
        vault.create("passphrase-2")


def test_unlock_right_and_wrong(fresh_db):
    vault.create("clave-correcta")
    assert vault.unlock("clave-equivocada") is False
    assert vault.is_unlocked() is False
    assert vault.unlock("clave-correcta") is True
    assert vault.is_unlocked() is True
    vault.lock()
    assert vault.is_unlocked() is False


# ── escritura sin desbloqueo (clave pública) + storage partido ─────────────────────────────────────────────
def test_store_secret_without_unlock(fresh_db):
    vault.create("passphrase")
    vault.lock()                                    # bloqueada: aun así se puede GUARDAR
    mid = vault.store_secret("contraseña de Netflix", "Perrito123", slot="secret:netflix:password")
    assert vault.is_sealed(mid)
    assert vault.status()["secret_count"] == 1


def test_value_never_plaintext_in_memories(fresh_db):
    vault.create("passphrase")
    vault.store_secret("contraseña de Netflix", "Perrito123", slot="secret:netflix:password")
    # el VALOR no puede aparecer en NINGUNA fila de `memories` ni en su meta
    rows = memdb.get_db().query("SELECT text, meta FROM memories")
    blob = " ".join((r["text"] or "") + " " + (r["meta"] or "") for r in rows)
    assert "Perrito123" not in blob
    # la ETIQUETA sí está (buscable)
    assert any("Netflix" in (r["text"] or "") for r in rows)
    # el ciphertext tampoco contiene el valor en claro
    ct = memdb.get_db().query_one("SELECT ciphertext FROM vault_secrets")["ciphertext"]
    assert b"Perrito123" not in bytes(ct)


# ── lectura ────────────────────────────────────────────────────────────────────────────────────────────────
def test_open_requires_unlock(fresh_db):
    vault.create("passphrase")
    mid = vault.store_secret("contraseña de Netflix", "Perrito123", slot="secret:netflix:password")
    vault.lock()
    with pytest.raises(vault.VaultLocked):
        vault.open_secret(mid)


def test_open_after_unlock(fresh_db):
    vault.create("passphrase")
    mid = vault.store_secret("contraseña de Netflix", "Perrito123", slot="secret:netflix:password")
    assert vault.unlock("passphrase") is True
    assert vault.open_secret(mid) == "Perrito123"


def test_open_transient_with_passphrase_strict_mode(fresh_db):
    vault.create("passphrase")
    mid = vault.store_secret("clave", "SuperSecreto!", slot="secret:x:password")
    vault.lock()
    # modo estricto: pasa la passphrase directamente, NO cachea
    assert vault.open_secret(mid, passphrase="passphrase") == "SuperSecreto!"
    assert vault.is_unlocked() is False


def test_open_wrong_transient_passphrase(fresh_db):
    vault.create("passphrase")
    mid = vault.store_secret("clave", "x", slot="secret:x:password")
    vault.lock()
    with pytest.raises(vault.WrongPassphrase):
        vault.open_secret(mid, passphrase="no-es")


# ── supersede: re-guardar la misma etiqueta reemplaza el valor ─────────────────────────────────────────────
def test_supersede_same_slot_replaces_value(fresh_db):
    vault.create("passphrase")
    vault.unlock("passphrase")
    mid1 = vault.store_secret("contraseña de Netflix", "vieja", slot="secret:netflix:password")
    mid2 = vault.store_secret("contraseña de Netflix", "nueva", slot="secret:netflix:password")
    assert mid1 == mid2                              # misma etiqueta → misma píldora
    assert vault.open_secret(mid2) == "nueva"
    assert vault.status()["secret_count"] == 1


# ── rotación de passphrase ─────────────────────────────────────────────────────────────────────────────────
def test_change_passphrase(fresh_db):
    vault.create("vieja-clave")
    mid = vault.store_secret("clave", "dato", slot="secret:x:password")
    vault.change_passphrase("vieja-clave", "nueva-clave")
    assert vault.unlock("vieja-clave") is False
    assert vault.unlock("nueva-clave") is True
    assert vault.open_secret(mid) == "dato"          # el secreto sobrevive a la rotación


def test_change_passphrase_wrong_old(fresh_db):
    vault.create("vieja")
    with pytest.raises(vault.WrongPassphrase):
        vault.change_passphrase("no-es-la-vieja", "nueva")


# ── passkeys (WebAuthn PRF, cripto server-side) ────────────────────────────────────────────────────────────
def test_passkey_enroll_and_unlock(fresh_db):
    import os
    vault.create("passphrase")
    vault.store_secret("clave", "SecretoPasskey", slot="secret:x:password")
    # enrolar exige la bóveda desbloqueada (solo quien ya tiene acceso añade un método)
    vault.unlock("passphrase")
    prf = os.urandom(32)                         # simula el secreto que devuelve el autenticador
    vault.add_passkey(prf, cred_id="cred-abc")
    assert "passkey" in vault.status()["methods"]
    # bloquea y desbloquea SOLO con el PRF (sin passphrase)
    vault.lock()
    assert vault.unlock_with_prf(os.urandom(32)) is False    # PRF equivocado
    assert vault.unlock_with_prf(prf) is True
    secs = vault.list_secrets()
    assert vault.open_secret(secs[0]["memory_id"]) == "SecretoPasskey"


def test_passkey_enroll_requires_unlock(fresh_db):
    import os
    vault.create("passphrase")
    vault.lock()
    with pytest.raises(vault.VaultLocked):
        vault.add_passkey(os.urandom(32), cred_id="cred-x")


def test_passkey_salt_is_stable_and_from_pubkey(fresh_db):
    vault.create("passphrase")
    m1 = vault.passkey_meta()
    m2 = vault.passkey_meta()
    assert m1["prf_salt"] and m1["prf_salt"] == m2["prf_salt"]   # estable
    assert m1["cred_ids"] == []


# ── listado (etiquetas, nunca valores) ─────────────────────────────────────────────────────────────────────
def test_list_secrets_labels_only(fresh_db):
    vault.create("passphrase")
    vault.store_secret("contraseña de Netflix", "a", slot="secret:netflix:password")
    vault.store_secret("IBAN", "b", slot="secret:iban:x", sensitivity="high", kind="iban")
    lst = vault.list_secrets()
    assert len(lst) == 2
    labels = {x["label"] for x in lst}
    assert "contraseña de Netflix" in labels and "IBAN" in labels
    # ningún valor en el listado
    assert all("value" not in x for x in lst)
