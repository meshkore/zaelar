"""The vault's keys: errors, KDF and envelopes, the single `vault_meta` row, the unlock session in RAM, the
lifecycle (create / unlock / lock), passphrase rotation and the redacted status."""
from __future__ import annotations

import json
import threading
import time
from base64 import b64decode, b64encode

from nacl import pwhash, utils
from nacl.exceptions import CryptoError
from nacl.public import PrivateKey
from nacl.secret import SecretBox

from .. import db as _db

# Argon2id parameters. MODERATE ≈ 0.7 s on a laptop: interactive without punishing a voice unlock. Persisted per
# envelope so they can be raised later without breaking old vaults.
_OPS = pwhash.argon2id.OPSLIMIT_MODERATE
_MEM = pwhash.argon2id.MEMLIMIT_MODERATE
_SALTBYTES = pwhash.argon2id.SALTBYTES
_KEYBYTES = SecretBox.KEY_SIZE

# TTL of the unwrapped key in RAM (comfort mode). In strict mode the caller passes hold=False (nothing cached).
import os as _os

_SESSION_TTL = float(_os.getenv("ZAELAR_VAULT_SESSION_TTL", "900"))   # s

_session_lock = threading.Lock()
_session: dict = {"sk": None, "exp": 0.0}


# ── errors ───────────────────────────────────────────────────────────────────────────────────────────────
class VaultError(Exception):
    """Generic vault failure."""


class VaultLocked(VaultError):
    """A secret was read but the vault is not unlocked (passphrase/passkey missing)."""


class WrongPassphrase(VaultError):
    """The passphrase (or unlock material) does not open the private key."""


def _msg(key: str, default: str, **params) -> str:
    """An error text the vault modal shows VERBATIM, in the instance language (pack `ui`, English fallback).
    Resolved when raised, so the exception carries the sentence the screen will print."""
    from i18n import runtime as _rt
    out = _rt.text(key, default=default)
    for k, v in params.items():
        out = out.replace("{" + k + "}", str(v))
    return out


# ── KDF / envelope helpers ───────────────────────────────────────────────────────────────────────────────
def _derive_kek(passphrase: str, salt: bytes, ops: int, mem: int) -> bytes:
    """Argon2id(passphrase, salt) → the 32-byte key that wraps/unwraps the private key."""
    return pwhash.argon2id.kdf(_KEYBYTES, passphrase.encode("utf-8"), salt, opslimit=ops, memlimit=mem)


def _passphrase_wrap(sk_bytes: bytes, passphrase: str) -> dict:
    """A 'passphrase' envelope wrapping `sk_bytes`."""
    salt = utils.random(_SALTBYTES)
    kek = _derive_kek(passphrase, salt, _OPS, _MEM)
    wrapped = SecretBox(kek).encrypt(sk_bytes)          # nonce included
    return {
        "method": "passphrase",
        "salt": b64encode(salt).decode(),
        "ops": _OPS,
        "mem": _MEM,
        "wrapped_sk": b64encode(bytes(wrapped)).decode(),
    }


def _unwrap_passphrase(wrap: dict, passphrase: str) -> bytes:
    """Unwraps `sk_bytes` from a 'passphrase' envelope. Raises WrongPassphrase if it does not match."""
    salt = b64decode(wrap["salt"])
    kek = _derive_kek(passphrase, salt, int(wrap.get("ops", _OPS)), int(wrap.get("mem", _MEM)))
    try:
        return SecretBox(kek).decrypt(b64decode(wrap["wrapped_sk"]))
    except CryptoError as e:  # bad MAC = wrong key
        raise WrongPassphrase(_msg("vault.err.bad_passphrase", "Wrong passphrase")) from e


# ── vault metadata (single row) ──────────────────────────────────────────────────────────────────────────
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
    """Is there a vault (with at least one unlock method)?"""
    return _load_meta() is not None


# ── lifecycle: create / unlock / lock ────────────────────────────────────────────────────────────────────
def create(passphrase: str) -> None:
    """Creates the vault: generates the key pair, wraps the private key with the passphrase, persists. The private
    key is never stored in clear. Not idempotent: if it exists, error (use change_passphrase to rotate)."""
    if not passphrase or len(passphrase) < 4:
        raise VaultError(_msg("vault.err.short_passphrase", "The passphrase must be at least 4 characters long"))
    if exists():
        raise VaultError(_msg("vault.err.exists", "The vault already exists"))
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
    """Unlocks with the passphrase: unwraps the private key and checks its public key matches the stored one
    (defence in depth beyond the SecretBox MAC). `hold` (comfort mode) keeps it in RAM `_SESSION_TTL` s; otherwise
    (strict mode) it is used and dropped. Returns True/False; raises VaultError if there is no vault."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    for wrap in meta["wraps"]:
        if wrap.get("method") != "passphrase":
            continue
        try:
            sk_bytes = _unwrap_passphrase(wrap, passphrase)
        except WrongPassphrase:
            continue
        if bytes(PrivateKey(sk_bytes).public_key) != meta["public_key"]:
            continue  # corrupt envelope / not this vault's
        if hold:
            _cache_sk(sk_bytes)
        return True
    return False


def lock() -> None:
    """Wipes the private key from RAM (locks the vault)."""
    with _session_lock:
        _session["sk"] = None
        _session["exp"] = 0.0


def is_unlocked() -> bool:
    return _cached_sk() is not None


# ── unlock-method management ─────────────────────────────────────────────────────────────────────────────
def change_passphrase(old: str, new: str) -> None:
    """Rotates the passphrase: re-wraps ONLY its envelope (the secrets and the key pair are untouched)."""
    if not new or len(new) < 4:
        raise VaultError(_msg("vault.err.short_new_passphrase", "The new passphrase must be at least 4 characters long"))
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
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
        raise WrongPassphrase(_msg("vault.err.bad_current_passphrase", "The current passphrase is wrong"))
    wraps = [w for w in meta["wraps"] if w.get("method") != "passphrase"]
    wraps.append(_passphrase_wrap(sk_bytes, new))
    _save_meta(meta["public_key"], wraps, create=False)


def status() -> dict:
    """REDACTED view for the frontend: presence/state, NEVER key material."""
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
