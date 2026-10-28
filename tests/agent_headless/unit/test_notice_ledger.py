"""A notice reaches him exactly once, wherever he is — and the ledger says how (V2-796, node 2.800).

Before this, a due reminder went to the voice and, with nobody listening, became a note for the brain's NEXT turn:
nothing recorded whether «the car's ITV expires on Thursday» ever reached him, and nothing could reach his phone.
`nucleo/notices.py` is the one door; these tests pin its four promises and the Web Push wire format it relies on.
"""
from __future__ import annotations

import asyncio
import base64
import json
import struct

import pytest
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from nucleo import notices, runstate, webpush


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@pytest.fixture(autouse=True)
def _isolated_key(tmp_path, monkeypatch):
    monkeypatch.setattr(webpush, "key_path", lambda: tmp_path / "vapid.pem")
    webpush._key_cache.clear()
    yield
    webpush._key_cache.clear()


@pytest.fixture
def voice(monkeypatch):
    """The voice door, recorded. `said` decides whether proactive.notify reports it spoke."""
    from voice import proactive
    calls, said = [], {"v": True}

    async def fake(title, text, **kw):
        calls.append(text)
        return said["v"]
    monkeypatch.setattr(proactive, "notify", fake)
    return calls, said


@pytest.fixture
def pushes(monkeypatch):
    sent, accept = [], {"n": 0}

    def fake(row):
        sent.append(row["dedupe_key"])
        return accept["n"]
    monkeypatch.setattr(notices, "push", fake)
    return sent, accept


@pytest.fixture
def running(monkeypatch):
    monkeypatch.setattr(runstate, "stopped", lambda: False)


def _run(coro):
    return asyncio.run(coro)


# ── the wire format: RFC 8291 + RFC 8292 ─────────────────────────────────────────────────────────────────────
def _browser():
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = b"0123456789abcdef"
    return priv, _b64u(pub), _b64u(auth), pub, auth


def _decrypt(body: bytes, ua_priv, ua_pub: bytes, auth: bytes) -> bytes:
    """What the BROWSER does (RFC 8291 §3.4 receiver side), written independently of the sender."""
    salt, rs, idlen = body[:16], struct.unpack("!I", body[16:20])[0], body[20]
    as_pub = body[21:21 + idlen]
    ct = body[21 + idlen:]
    assert rs == 4096 and idlen == 65
    shared = ua_priv.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))

    def hm(k, d):
        h = hmac.HMAC(k, hashes.SHA256()); h.update(d); return h.finalize()
    ikm = hm(hm(auth, shared), b"WebPush: info\x00" + ua_pub + as_pub + b"\x01")[:32]
    prk = hm(salt, ikm)
    cek = hm(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = hm(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    plain = AESGCM(cek).decrypt(nonce, ct, None)
    assert plain.endswith(b"\x02"), "a single record ends with the last-record delimiter"
    return plain[:-1]


def test_the_browser_can_decrypt_what_we_send():
    priv, p256dh, auth, pub, auth_raw = _browser()
    msg = json.dumps({"title": "ITV", "body": "La ITV del coche caduca el jueves"}).encode()
    body = webpush.encrypt(msg, p256dh, auth)
    assert _decrypt(body, priv, pub, auth_raw) == msg


def test_the_vapid_token_is_signed_by_the_key_the_browser_subscribed_with():
    hdr = webpush.vapid_header("https://fcm.googleapis.com/fcm/send/abc", now=1_000_000)
    t_part, k_part = hdr.removeprefix("vapid ").split(", ")
    jwt, key = t_part.removeprefix("t="), k_part.removeprefix("k=")
    assert key == webpush.public_key()
    head, claims, sig = jwt.split(".")
    c = json.loads(_unb64u(claims))
    assert c["aud"] == "https://fcm.googleapis.com" and c["exp"] == 1_000_000 + 12 * 3600 and c["sub"]
    raw = _unb64u(sig)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _unb64u(key))
    pub.verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))   # raises if forged


def test_a_revoked_subscription_reads_as_gone():
    priv, p256dh, auth, _, _ = _browser()

    class C:
        def __init__(self, code): self.code = code
        def post(self, *a, **k): return type("R", (), {"status_code": self.code})()
    sub = {"endpoint": "https://push.example/x", "p256dh": p256dh, "auth": auth}
    assert webpush.send(sub, {"b": 1}, client=C(201))["ok"]
    assert webpush.send(sub, {"b": 1}, client=C(410))["gone"]
    assert not webpush.send(sub, {"b": 1}, client=C(500))["gone"], "a push-service hiccup is retried, not forgotten"


# ── the ledger's promises ────────────────────────────────────────────────────────────────────────────────────
def test_never_twice_the_same_key_delivers_once(voice, pushes, running, monkeypatch):
    calls, _ = voice
    monkeypatch.setattr(notices, "someone_looking", lambda now=None: True)
    a = _run(notices.notify("ITV", "Tu ITV caduca el jueves", key="job:7:100"))
    b = _run(notices.notify("ITV", "Tu ITV caduca el jueves", key="job:7:100"))
    assert a["state"] == "spoken" and not a["duplicate"]
    assert b["duplicate"] and len(calls) == 1, "a restart that re-fires the same job must not repeat it"


def test_nobody_in_front_of_a_screen_means_the_phone_is_told_too(voice, pushes, running, monkeypatch):
    sent, accept = pushes
    accept["n"] = 1
    monkeypatch.setattr(notices, "someone_looking", lambda now=None: False)
    r = _run(notices.notify("zaelar", "He terminado la búsqueda de pisos", key="notice:t1", kind="done"))
    assert r["state"] == "pushed" and r["channel"] == "voice+push" and sent == ["notice:t1"]


def test_never_lost_what_nothing_could_take_is_owed_and_shown_on_the_next_screen(voice, pushes, running, monkeypatch):
    calls, said = voice
    said["v"] = False                                # no live voice session
    shown = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **kw: shown.append((kind, kw.get("text"))))
    r = _run(notices.notify("ITV", "Tu ITV caduca el jueves", key="job:8:100"))
    assert r["state"] == "owed"
    assert notices.by_key("job:8:100")["next_try_at"], "an owed notice is retried"
    assert notices.drain_to_screen("mobile:abc") == 1
    assert ("notify", "Tu ITV caduca el jueves") in shown
    assert notices.by_key("job:8:100")["state"] == "shown"
    assert notices.drain_to_screen("mobile:abc") == 0, "and shown once"


def test_an_owed_notice_is_pushed_once_a_device_can_take_it(voice, pushes, running, monkeypatch):
    calls, said = voice
    said["v"] = False
    sent, accept = pushes
    _run(notices.notify("ITV", "Tu ITV caduca el jueves", key="job:9:100"))
    row = notices.by_key("job:9:100")
    notices._set(row["id"], next_try_at=0)
    monkeypatch.setattr(notices, "_targets", lambda: [{"id": "d"}])
    accept["n"] = 1
    notices._last_retry[0] = 0.0
    assert _run(notices.retry_owed(now=10_000_000_000)) == 1
    assert notices.by_key("job:9:100")["state"] == "pushed"


def test_covered_by_google_delivers_nothing(voice, pushes, running):
    calls, _ = voice
    sent, _ = pushes
    r = _run(notices.notify("Dentista", "Dentista a las 17:00", key="job:10:100", covered_by="google"))
    assert r["state"] == "covered" and not calls and not sent


def test_stopped_silences_the_voice_not_the_lock_screen(voice, pushes, monkeypatch):
    calls, _ = voice
    sent, accept = pushes
    accept["n"] = 1
    monkeypatch.setattr(runstate, "stopped", lambda: True)
    r = _run(notices.notify("ITV", "Tu ITV caduca el jueves", key="job:11:100"))
    assert not calls, "⏻ means the agent does not speak"
    assert r["state"] == "pushed" and sent == ["job:11:100"]


def test_a_subscription_never_returns_its_endpoint():
    notices.subscribe({"endpoint": "https://push.example/secret-capability", "keys": {"p256dh": "x", "auth": "y"}},
                      dev="mobile:1", platform="mobile:ios", installed=True)
    rows = notices.devices()
    assert len(rows) == 1 and "endpoint" not in rows[0] and rows[0]["installed"] == 1
    assert not notices.subscribe({"endpoint": "http://plain", "keys": {"p256dh": "x", "auth": "y"}})["ok"]


# ── the loop: ⏻ and the one door ─────────────────────────────────────────────────────────────────────────────
def test_the_loop_fires_a_reminder_to_the_phone_while_stopped_and_postpones_it_with_no_phone(monkeypatch):
    from nucleo.pulse import loop as _loop, scheduler
    import time
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 3600))
    job = scheduler.create("Recuerda: la ITV caduca el jueves", stamp, name="aviso: ITV", origin="cron")
    assert job["ok"], job
    later = job["schedule"]["next_run"] + 5
    monkeypatch.setattr(runstate, "stopped", lambda: True)
    got = []

    async def fake_notify(title, text, **kw):
        got.append((title, kw["key"]))
        return {"state": "pushed", "channel": "push"}
    monkeypatch.setattr(notices, "notify", fake_notify)
    lp = _loop.OrchestratorLoop()

    monkeypatch.setattr(notices, "devices", lambda: [])
    _run(lp._fire_due(later))
    assert not got and any(j["id"] == job["id"] for j in scheduler.due(later)), "no phone: postponed, as before"

    monkeypatch.setattr(notices, "devices", lambda: [{"id": "d"}])
    _run(lp._fire_due(later))
    assert got == [("ITV", f"job:{job['id']}:{job['schedule']['next_run']}")]
    assert not any(j["id"] == job["id"] for j in scheduler.due(later)), "fired once"
    scheduler.cancel(str(job["id"]))
