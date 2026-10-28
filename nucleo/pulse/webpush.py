"""nucleo/pulse/webpush.py — send a Web Push message to a browser, with no third-party push library (V2-796).

Two standards, both small enough to own:
  · RFC 8291 / RFC 8188 — the payload is encrypted for the browser (`aes128gcm`): an ephemeral ECDH P-256 key
    against the subscription's `p256dh`, mixed with its 16-byte `auth` secret, one AES-128-GCM record.
  · RFC 8292 (VAPID) — the request is signed with THIS install's key pair, so the push service (Google, Apple,
    Mozilla) only accepts messages for a subscription from the server that created it.

The key pair is generated on first use next to the credential store (`key_path()`, never in git). Losing it is survivable — every browser re-subscribes against the new public key the next time
it opens the app — but rotating it on purpose invalidates every subscription at once, so it is never rotated here.

`send()` never raises: it returns `{"ok", "status", "gone"}`. `gone` (404/410) means the browser revoked the
subscription and the caller must forget it; anything else is retried by the caller's own policy.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import struct
import threading
import time
import urllib.parse

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from nucleo import workspace as _workspace

logger = logging.getLogger("zaelar.webpush")

#: Push services cap the payload at 4096 bytes of ciphertext; one record of this size always fits one message.
RECORD_SIZE = 4096
MAX_PAYLOAD = 3000
_TTL_S = 24 * 3600          # a notice nobody's phone could take in a day is not worth delivering late
_JWT_TTL_S = 12 * 3600      # RFC 8292 caps `exp` at 24 h; the push services reject anything longer

_lock = threading.Lock()
_key_cache: dict = {}


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64u(s: str) -> bytes:
    s = (s or "").strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def key_path():
    # Same placement rule as the credential store (`config/credentials.py::_store_path`): a container keeps it on
    # its volume, a self-hosted checkout in the gitignored `.meshkore/credentials/`.
    if os.getenv("ZAELAR_WORKSPACE"):
        return _workspace.root() / "credentials" / "webpush_vapid.pem"
    return _workspace.root() / ".meshkore" / "credentials" / "webpush_vapid.pem"


def _private_key() -> ec.EllipticCurvePrivateKey:
    with _lock:
        path = key_path()
        cached = _key_cache.get(str(path))
        if cached is not None:
            return cached
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        else:
            key = ec.generate_private_key(ec.SECP256R1())
            path.parent.mkdir(parents=True, exist_ok=True)
            pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(pem)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        _key_cache[str(path)] = key
        return key


def _raw_public(pub: ec.EllipticCurvePublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def public_key() -> str:
    """The VAPID public key, base64url — what the browser passes as `applicationServerKey`."""
    return _b64u(_raw_public(_private_key().public_key()))


def _subject() -> str:
    # Apple rejects a VAPID token without a `sub` that is a mailto: or https: URL.
    return (os.getenv("ZAELAR_PUSH_SUBJECT") or "").strip() or "https://zaelar.com"


def vapid_header(endpoint: str, now: float | None = None) -> str:
    """`Authorization: vapid t=<jwt>, k=<public key>` for this endpoint's push service."""
    u = urllib.parse.urlsplit(endpoint)
    aud = f"{u.scheme}://{u.netloc}"
    now = time.time() if now is None else now
    head = _b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = _b64u(json.dumps({"aud": aud, "exp": int(now + _JWT_TTL_S), "sub": _subject()},
                              separators=(",", ":")).encode())
    signing_input = f"{head}.{claims}".encode()
    der = _private_key().sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")       # JWS wants raw r||s, not DER
    return f"vapid t={head}.{claims}.{_b64u(sig)}, k={public_key()}"


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    h = hmac.HMAC(prk, hashes.SHA256())
    h.update(info + b"\x01")
    return h.finalize()[:length]


def _hmac(key: bytes, data: bytes) -> bytes:
    h = hmac.HMAC(key, hashes.SHA256())
    h.update(data)
    return h.finalize()


def encrypt(payload: bytes, p256dh: str, auth: str, *, salt: bytes | None = None,
            sender: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    """RFC 8291 §3.4: the `aes128gcm` body for one subscription. `salt`/`sender` are only passed by tests."""
    ua_public = _unb64u(p256dh)
    auth_secret = _unb64u(auth)
    if len(ua_public) != 65 or len(auth_secret) < 16:
        raise ValueError("bad subscription keys")
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    as_key = sender or ec.generate_private_key(ec.SECP256R1())
    as_public = _raw_public(as_key.public_key())
    ecdh = as_key.exchange(ec.ECDH(), ua_key)
    prk_key = _hmac(auth_secret, ecdh)
    ikm = _hkdf_expand(prk_key, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    prk = _hmac(salt, ikm)
    cek = _hkdf_expand(prk, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf_expand(prk, b"Content-Encoding: nonce\x00", 12)
    record = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)      # 0x02 = last (and only) record
    return salt + struct.pack("!I", RECORD_SIZE) + bytes([len(as_public)]) + as_public + record


def send(sub: dict, message: dict, *, topic: str = "", urgency: str = "high", client=None) -> dict:
    """POST one encrypted message to `sub` ({endpoint, p256dh, auth}). Never raises."""
    endpoint = str((sub or {}).get("endpoint") or "")
    if not endpoint.startswith("https://"):
        return {"ok": False, "status": 0, "gone": True, "error": "endpoint is not https"}
    try:
        body = json.dumps(message, ensure_ascii=False).encode()[:MAX_PAYLOAD]
        data = encrypt(body, sub.get("p256dh", ""), sub.get("auth", ""))
        headers = {"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
                   "TTL": str(_TTL_S), "Urgency": urgency, "Authorization": vapid_header(endpoint)}
        if topic:
            # A newer message with the same Topic REPLACES an undelivered older one at the push service.
            headers["Topic"] = _b64u(topic.encode())[:32]
        if client is None:
            import httpx
            with httpx.Client(timeout=10.0) as c:
                r = c.post(endpoint, content=data, headers=headers)
        else:
            r = client.post(endpoint, content=data, headers=headers)
        status = int(r.status_code)
    except ValueError as e:
        return {"ok": False, "status": 0, "gone": True, "error": str(e)}
    except Exception as e:  # noqa: BLE001 — a network failure is retried by the caller, never raised into the loop
        logger.warning(f"webpush: send failed: {e!r}")
        return {"ok": False, "status": 0, "gone": False, "error": repr(e)[:200]}
    if status in (200, 201, 202):
        return {"ok": True, "status": status, "gone": False}
    if status in (404, 410):
        return {"ok": False, "status": status, "gone": True}
    if status in (401, 403):
        # The subscription was made against another VAPID key (a lost key file): the browser re-subscribes on its
        # next open, so the old row is dead either way.
        return {"ok": False, "status": status, "gone": True}
    logger.warning(f"webpush: push service answered {status}")
    return {"ok": False, "status": status, "gone": False}
