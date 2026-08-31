"""Documentation translated to English."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from base64 import b64decode, b64encode

from nacl import pwhash, utils
from nacl.exceptions import CryptoError
from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.secret import SecretBox

from . import db as _db
from . import writer as _writer

# translated implementation note
# translated implementation note
_OPS = pwhash.argon2id.OPSLIMIT_MODERATE
_MEM = pwhash.argon2id.MEMLIMIT_MODERATE
_SALTBYTES = pwhash.argon2id.SALTBYTES
_KEYBYTES = SecretBox.KEY_SIZE

# translated implementation note
import os as _os

_SESSION_TTL = float(_os.getenv("ZAELAR_VAULT_SESSION_TTL", "900"))   # s

_session_lock = threading.Lock()
_session: dict = {"sk": None, "exp": 0.0}


# translated implementation note
class VaultError(Exception):
    """Documentation translated to English."""


class VaultLocked(VaultError):
    """Documentation translated to English."""


class WrongPassphrase(VaultError):
    """Documentation translated to English."""


# translated implementation note
def _derive_kek(passphrase: str, salt: bytes, ops: int, mem: int) -> bytes:
    """Documentation translated to English."""
    return pwhash.argon2id.kdf(_KEYBYTES, passphrase.encode("utf-8"), salt, opslimit=ops, memlimit=mem)


def _passphrase_wrap(sk_bytes: bytes, passphrase: str) -> dict:
    """Documentation translated to English."""
    salt = utils.random(_SALTBYTES)
    kek = _derive_kek(passphrase, salt, _OPS, _MEM)
    wrapped = SecretBox(kek).encrypt(sk_bytes)          # incluye nonce
    return {
        "method": "passphrase",
        "salt": b64encode(salt).decode(),
        "ops": _OPS,
        "mem": _MEM,
        "wrapped_sk": b64encode(bytes(wrapped)).decode(),
    }


def _unwrap_passphrase(wrap: dict, passphrase: str) -> bytes:
    """Documentation translated to English."""
    salt = b64decode(wrap["salt"])
    kek = _derive_kek(passphrase, salt, int(wrap.get("ops", _OPS)), int(wrap.get("mem", _MEM)))
    try:
        return SecretBox(kek).decrypt(b64decode(wrap["wrapped_sk"]))
    except CryptoError as e:  # translated implementation note
        raise WrongPassphrase("passphrase incorrecta") from e


# translated implementation note
def _load_meta() -> dict | None:
    row = _db.get_db().query_one("SELECT public_key, wraps FROM vault_meta WHERE id=1")
    if not row:
        return None
    return {"public_key": bytes(row["public_key"]), "wraps": json.loads(row["wraps"])}


def _save_meta(public_key: bytes, wraps: list[dict], *, create: bool) -> None:
    now = int(time.time())
    db = _db.get_db()
    payload = json.dumps(wraps, ensure_ascii=False)
    if create:
        db.execute("INSERT INTO vault_meta (id, public_key, wraps, created, updated) VALUES (1,?,?,?,?)",
                   (public_key, payload, now, now))
    else:
        db.execute("UPDATE vault_meta SET public_key=?, wraps=?, updated=? WHERE id=1",
                   (public_key, payload, now))


def exists() -> bool:
    """Documentation translated to English."""
    return _load_meta() is not None


# translated implementation note
def create(passphrase: str) -> None:
    """Documentation translated to English."""
    if not passphrase or len(passphrase) < 4:
        raise VaultError("la passphrase debe tener al menos 4 caracteres")
    if exists():
        raise VaultError("la bóveda ya existe")
    sk = PrivateKey.generate()
    pk_bytes = bytes(sk.public_key)
    wrap = _passphrase_wrap(bytes(sk), passphrase)
    _save_meta(pk_bytes, [wrap], create=True)


def _cache_sk(sk_bytes: bytes) -> None:
    with _session_lock:
        _session["sk"] = sk_bytes
        _session["exp"] = time.time() + _SESSION_TTL


def _cached_sk() -> bytes | None:
    with _session_lock:
        sk = _session["sk"]
        if sk is None:
            return None
        if time.time() > _session["exp"]:
            _session["sk"] = None
            return None
        return sk


def unlock(passphrase: str, *, hold: bool = True) -> bool:
    """Documentation translated to English."""
    meta = _load_meta()
    if not meta:
        raise VaultError("no hay bóveda creada")
    for wrap in meta["wraps"]:
        if wrap.get("method") != "passphrase":
            continue
        try:
            sk_bytes = _unwrap_passphrase(wrap, passphrase)
        except WrongPassphrase:
            continue
        if bytes(PrivateKey(sk_bytes).public_key) != meta["public_key"]:
            continue  # translated implementation note
        if hold:
            _cache_sk(sk_bytes)
        return True
    return False


def lock() -> None:
    """Documentation translated to English."""
    with _session_lock:
        _session["sk"] = None
        _session["exp"] = 0.0


def is_unlocked() -> bool:
    return _cached_sk() is not None


# translated implementation note
def seal(plaintext: str) -> bytes:
    """Documentation translated to English."""
    meta = _load_meta()
    if not meta:
        raise VaultError("no hay bóveda creada")
    return SealedBox(PublicKey(meta["public_key"])).encrypt(plaintext.encode("utf-8"))


def _open_with_sk(ciphertext: bytes, sk_bytes: bytes) -> str:
    meta = _load_meta()
    sk = PrivateKey(sk_bytes)
    return SealedBox(sk).decrypt(bytes(ciphertext)).decode("utf-8")


def store_secret(label: str, value: str, *, slot: str | None = None, sensitivity: str = "high",
                 kind: str = "fact") -> int:
    """Documentation translated to English."""
    if not exists():
        raise VaultError("no hay bóveda creada — créala antes de guardar secretos")
    ciphertext = seal(value)
    meta = {"vault": 1, "sensitivity": sensitivity, "label": label}
    mid = _writer.insert_memory(
        label, level="long", kind=kind, importance=0.9, pinned=True, slot=slot, meta=meta)
    _db.get_db().execute(
        "INSERT OR REPLACE INTO vault_secrets (memory_id, ciphertext, created) VALUES (?,?,?)",
        (mid, bytes(ciphertext), int(time.time())))
    return mid


def is_sealed(memory_id: int) -> bool:
    """Documentation translated to English."""
    return _db.get_db().query_one(
        "SELECT 1 FROM vault_secrets WHERE memory_id=?", (memory_id,)) is not None


def open_secret(memory_id: int, *, passphrase: str | None = None) -> str:
    """Documentation translated to English."""
    row = _db.get_db().query_one("SELECT ciphertext FROM vault_secrets WHERE memory_id=?", (memory_id,))
    if not row:
        raise VaultError(f"no hay secreto sellado para la píldora {memory_id}")
    ciphertext = bytes(row["ciphertext"])
    sk_bytes = _cached_sk()
    if sk_bytes is None and passphrase is not None:
        # desbloqueo transitorio (no cachea): desenvuelve, usa, descarta
        meta = _load_meta()
        if not meta:
            raise VaultError("no hay bóveda creada")
        for wrap in meta["wraps"]:
            if wrap.get("method") != "passphrase":
                continue
            try:
                cand = _unwrap_passphrase(wrap, passphrase)
            except WrongPassphrase:
                continue
            if bytes(PrivateKey(cand).public_key) == meta["public_key"]:
                sk_bytes = cand
                break
        if sk_bytes is None:
            raise WrongPassphrase("passphrase incorrecta")
    if sk_bytes is None:
        raise VaultLocked("la bóveda está bloqueada — hace falta la passphrase")
    try:
        return _open_with_sk(ciphertext, sk_bytes)
    except CryptoError as e:
        raise VaultError("no se pudo descifrar el secreto") from e


def list_secrets() -> list[dict]:
    """Documentation translated to English."""
    rows = _db.get_db().query(
        "SELECT m.id AS id, m.text AS label, m.slot AS slot, m.meta AS meta "
        "FROM vault_secrets v JOIN memories m ON m.id = v.memory_id WHERE m.valid=1 ORDER BY m.updated DESC")
    out = []
    for r in rows:
        try:
            meta = json.loads(r["meta"]) if r["meta"] else {}
        except Exception:
            meta = {}
        out.append({"memory_id": int(r["id"]), "label": r["label"], "slot": r["slot"],
                    "sensitivity": meta.get("sensitivity", "high")})
    return out


# translated implementation note
def change_passphrase(old: str, new: str) -> None:
    """Documentation translated to English."""
    if not new or len(new) < 4:
        raise VaultError("la nueva passphrase debe tener al menos 4 caracteres")
    meta = _load_meta()
    if not meta:
        raise VaultError("no hay bóveda creada")
    sk_bytes = None
    for wrap in meta["wraps"]:
        if wrap.get("method") != "passphrase":
            continue
        try:
            sk_bytes = _unwrap_passphrase(wrap, old)
            break
        except WrongPassphrase:
            continue
    if sk_bytes is None:
        raise WrongPassphrase("la passphrase actual no es correcta")
    wraps = [w for w in meta["wraps"] if w.get("method") != "passphrase"]
    wraps.append(_passphrase_wrap(sk_bytes, new))
    _save_meta(meta["public_key"], wraps, create=False)


def status() -> dict:
    """Documentation translated to English."""
    meta = _load_meta()
    if not meta:
        return {"exists": False, "unlocked": False, "methods": [], "secret_count": 0}
    count = _db.get_db().query_one("SELECT COUNT(*) AS n FROM vault_secrets")
    return {
        "exists": True,
        "unlocked": is_unlocked(),
        "methods": sorted({w.get("method") for w in meta["wraps"] if w.get("method")}),
        "secret_count": int(count["n"]) if count else 0,
    }


# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
def _prf_salt() -> bytes | None:
    meta = _load_meta()
    if not meta:
        return None
    return hashlib.blake2b(b"zaelar-vault-prf|" + meta["public_key"], digest_size=32).digest()


def _prf_kek(prf_secret: bytes) -> bytes:
    """Documentation translated to English."""
    return hashlib.blake2b(bytes(prf_secret), digest_size=_KEYBYTES).digest()


def passkey_meta() -> dict:
    """Documentation translated to English."""
    meta = _load_meta()
    if not meta:
        return {"prf_salt": None, "cred_ids": []}
    salt = _prf_salt()
    creds = [w.get("cred_id") for w in meta["wraps"] if w.get("method") == "passkey" and w.get("cred_id")]
    return {"prf_salt": b64encode(salt).decode() if salt else None, "cred_ids": creds}


def add_passkey(prf_secret: bytes, cred_id: str) -> None:
    """Documentation translated to English."""
    meta = _load_meta()
    if not meta:
        raise VaultError("no hay bóveda creada")
    sk_bytes = _cached_sk()
    if sk_bytes is None:
        raise VaultLocked("desbloquea la bóveda antes de añadir una passkey")
    kek = _prf_kek(prf_secret)
    wrapped = SecretBox(kek).encrypt(sk_bytes)
    wraps = [w for w in meta["wraps"] if not (w.get("method") == "passkey" and w.get("cred_id") == cred_id)]
    wraps.append({"method": "passkey", "cred_id": cred_id, "wrapped_sk": b64encode(bytes(wrapped)).decode()})
    _save_meta(meta["public_key"], wraps, create=False)


def unlock_with_prf(prf_secret: bytes, *, hold: bool = True) -> bool:
    """Documentation translated to English."""
    meta = _load_meta()
    if not meta:
        raise VaultError("no hay bóveda creada")
    kek = _prf_kek(prf_secret)
    for wrap in meta["wraps"]:
        if wrap.get("method") != "passkey":
            continue
        try:
            sk_bytes = SecretBox(kek).decrypt(b64decode(wrap["wrapped_sk"]))
        except CryptoError:
            continue
        if bytes(PrivateKey(sk_bytes).public_key) != meta["public_key"]:
            continue
        if hold:
            _cache_sk(sk_bytes)
        return True
    return False


def remove_passkey(cred_id: str) -> None:
    """Documentation translated to English."""
    meta = _load_meta()
    if not meta:
        raise VaultError("no hay bóveda creada")
    wraps = [w for w in meta["wraps"] if not (w.get("method") == "passkey" and w.get("cred_id") == cred_id)]
    if not any(w.get("method") == "passphrase" for w in wraps) and \
            not any(w.get("method") == "passkey" for w in wraps):
        raise VaultError("no puedes quitar el último método de desbloqueo")
    _save_meta(meta["public_key"], wraps, create=False)
