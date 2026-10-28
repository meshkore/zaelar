"""The secrets themselves: seal with the PUBLIC key (no unlock), store the value opaque beside its searchable
label pill, open with the private key, list by label only."""
from __future__ import annotations

import json
import time

from nacl.exceptions import CryptoError
from nacl.public import PrivateKey, PublicKey, SealedBox

from .. import db as _db
from .. import writer as _writer
from .keys import (
    VaultError, VaultLocked, WrongPassphrase, _cached_sk, _load_meta, _msg, _unwrap_passphrase, exists,
)


def seal(plaintext: str) -> bytes:
    """Encrypts a text to the vault's PUBLIC key (NO unlock needed). Returns the opaque ciphertext."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    return SealedBox(PublicKey(meta["public_key"])).encrypt(plaintext.encode("utf-8"))


def _open_with_sk(ciphertext: bytes, sk_bytes: bytes) -> str:
    _load_meta()   # kept for its read (fails the same way it always did); the binding was dead (F841)
    sk = PrivateKey(sk_bytes)
    return SealedBox(sk).decrypt(bytes(ciphertext)).decode("utf-8")


def store_secret(label: str, value: str, *, slot: str | None = None, sensitivity: str = "high",
                 kind: str = "fact") -> int:
    """Stores a secret: SEALS the value (public key, no unlock) and writes the searchable LABEL pill through the
    single writer. Returns the pill id. The label is in clear (for recall); the value never is.

    `slot` (e.g. `secret:netflix:password`) enables SUPERSEDE: saving the same label again reuses the pill (same
    id) and REPLACES the ciphertext — the latest wins, no duplicates."""
    if not exists():
        raise VaultError(_msg("vault.err.no_vault_for_secrets", "No vault has been created — create it before saving secrets"))
    ciphertext = seal(value)
    meta = {"vault": 1, "sensitivity": sensitivity, "label": label}
    mid = _writer.insert_memory(
        label, level="long", kind=kind, importance=0.9, pinned=True, slot=slot, meta=meta)
    _db.get_db().execute(
        "INSERT OR REPLACE INTO vault_secrets (memory_id, ciphertext, created) VALUES (?,?,?)",
        (mid, bytes(ciphertext), int(time.time())))
    return mid


def is_sealed(memory_id: int) -> bool:
    """Does this pill have a sealed value in the vault?"""
    return _db.get_db().query_one(
        "SELECT 1 FROM vault_secrets WHERE memory_id=?", (memory_id,)) is not None


def open_secret(memory_id: int, *, passphrase: str | None = None) -> str:
    """Decrypts a secret's value with the key in RAM (comfort mode) or, given `passphrase`, a transient unlock
    (strict mode, nothing cached). Raises VaultLocked if it cannot be unlocked, VaultError if there is no secret."""
    row = _db.get_db().query_one("SELECT ciphertext FROM vault_secrets WHERE memory_id=?", (memory_id,))
    if not row:
        raise VaultError(_msg("vault.err.no_sealed_secret", "There is no sealed secret for item {id}", id=memory_id))
    ciphertext = bytes(row["ciphertext"])
    sk_bytes = _cached_sk()
    if sk_bytes is None and passphrase is not None:
        # transient unlock (not cached): unwrap, use, drop
        meta = _load_meta()
        if not meta:
            raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
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
            raise WrongPassphrase(_msg("vault.err.bad_passphrase", "Wrong passphrase"))
    if sk_bytes is None:
        raise VaultLocked(_msg("vault.err.locked", "The vault is locked — the passphrase is needed"))
    try:
        return _open_with_sk(ciphertext, sk_bytes)
    except CryptoError as e:
        raise VaultError(_msg("vault.err.decrypt_failed", "The secret could not be decrypted")) from e


def list_secrets() -> list[dict]:
    """The secrets by LABEL (never the value): [{memory_id, label, sensitivity, slot}]."""
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
