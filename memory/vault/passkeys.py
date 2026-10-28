"""PASSKEYS (WebAuthn PRF) — the second unlock method (V2-060 F3).

The browser gets a 32-byte secret from the authenticator only after the biometric gesture (`prf` extension) and
sends it to the server, which uses it as the KEK wrapping the SAME private key. Decryption happens on the server
(comfort mode). The PRF salt is DERIVED from the public key (not secret, stable): no extra schema or state."""
from __future__ import annotations

import hashlib
from base64 import b64decode, b64encode

from nacl.exceptions import CryptoError
from nacl.public import PrivateKey
from nacl.secret import SecretBox

from .keys import _KEYBYTES, VaultError, VaultLocked, _cache_sk, _cached_sk, _load_meta, _msg, _save_meta


def _prf_salt() -> bytes | None:
    meta = _load_meta()
    if not meta:
        return None
    return hashlib.blake2b(b"zaelar-vault-prf|" + meta["public_key"], digest_size=32).digest()


def _prf_kek(prf_secret: bytes) -> bytes:
    """Normalises the PRF secret (already ~32 uniform bytes) to a 32-byte SecretBox key."""
    return hashlib.blake2b(bytes(prf_secret), digest_size=_KEYBYTES).digest()


def passkey_meta() -> dict:
    """For the browser's WebAuthn challenge: PRF salt + registered credential ids (nothing secret)."""
    meta = _load_meta()
    if not meta:
        return {"prf_salt": None, "cred_ids": []}
    salt = _prf_salt()
    creds = [w.get("cred_id") for w in meta["wraps"] if w.get("method") == "passkey" and w.get("cred_id")]
    return {"prf_salt": b64encode(salt).decode() if salt else None, "cred_ids": creds}


def add_passkey(prf_secret: bytes, cred_id: str) -> None:
    """Registers a device: wraps the private key under the passkey's PRF. Requires the vault UNLOCKED (key in RAM),
    so only someone who already has access can add a method. Dedup by `cred_id`."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    sk_bytes = _cached_sk()
    if sk_bytes is None:
        raise VaultLocked(_msg("vault.err.unlock_before_passkey", "Unlock the vault before adding a passkey"))
    kek = _prf_kek(prf_secret)
    wrapped = SecretBox(kek).encrypt(sk_bytes)
    wraps = [w for w in meta["wraps"] if not (w.get("method") == "passkey" and w.get("cred_id") == cred_id)]
    wraps.append({"method": "passkey", "cred_id": cred_id, "wrapped_sk": b64encode(bytes(wrapped)).decode()})
    _save_meta(meta["public_key"], wraps, create=False)


def unlock_with_prf(prf_secret: bytes, *, hold: bool = True) -> bool:
    """Unlocks with a passkey's PRF secret. Same as `unlock`, with the PRF's KEK."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
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
    """Revokes a device (drops its envelope). Touches neither the secrets nor the other methods."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    wraps = [w for w in meta["wraps"] if not (w.get("method") == "passkey" and w.get("cred_id") == cred_id)]
    if not any(w.get("method") == "passphrase" for w in wraps) and \
            not any(w.get("method") == "passkey" for w in wraps):
        raise VaultError(_msg("vault.err.last_method", "You cannot remove the last unlock method"))
    _save_meta(meta["public_key"], wraps, create=False)
