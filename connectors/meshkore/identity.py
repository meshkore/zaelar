#
# MeshKore agent identity — the stable did:key zaelar presents to a cluster so other agents recognise it.
#
# Per https://meshkore.com/reference/agents/identity.md: a code agent in a repo keeps a stable Ed25519 keypair in
# .meshkore/credentials/ (gitignored — it's a secret) and REUSES it across sessions, no human step. The token
# gets you in; the did:key is WHO you are to the others.
#
# We derive the did:key with the standard W3C did:key method for Ed25519:
#   did:key:z<base58btc( 0xed01 || raw_32_byte_pubkey )>   → always starts "did:key:z6Mk…"
# That's the interoperable form every did:key implementation understands. MESHKORE_DID overrides it if you want to
# pin an externally-managed identity.
#
import os
from pathlib import Path

from nucleo import workspace as _workspace

_ROOT = Path(__file__).resolve().parents[2]


def _key_file() -> Path:
    # Same reasoning as config/credentials.py's _store_path(): `ZAELAR_WORKSPACE` SET (Fase 3, real
    # cloud Machine) drops the `.meshkore` segment entirely — a deployed container never has the
    # dev-only `engine/.meshkore -> ../.meshkore` symlink. UNSET (self-host, today) stays
    # byte-identical to the path this module has always used.
    if os.getenv("ZAELAR_WORKSPACE"):
        return _workspace.root() / "credentials" / "meshkore_ed25519.pem"
    return _ROOT / ".meshkore" / "credentials" / "meshkore_ed25519.pem"


KEY_FILE = _key_file()

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_cache: dict = {}


def _b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n > 0:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    pad = len(b) - len(b.lstrip(b"\x00"))     # preserve leading zero bytes as '1'
    return "1" * pad + out


def _load_or_create():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if KEY_FILE.exists():
        return serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=None)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    priv = Ed25519PrivateKey.generate()
    KEY_FILE.write_bytes(priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    try:
        os.chmod(KEY_FILE, 0o600)
    except Exception:
        pass
    from loguru import logger
    logger.info(f"MeshKore identity: generated a new Ed25519 keypair → {KEY_FILE}")
    return priv


def did_key() -> str:
    """zaelar's stable did:key (env override > persisted key > freshly generated). Cached for the process."""
    env = os.getenv("MESHKORE_DID")
    if env:
        return env
    if "did" not in _cache:
        from cryptography.hazmat.primitives import serialization
        raw = _load_or_create().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        _cache["did"] = "did:key:z" + _b58encode(b"\xed\x01" + raw)
    return _cache["did"]
