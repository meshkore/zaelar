#!/usr/bin/env python3
"""
tls_cert.py — make sure THIS install has its own certificate for https://local.zaelar.com:44317.

WHY THIS EXISTS
    `local.zaelar.com` is a public DNS A record pointing at 127.0.0.1, so the name always means «this machine».
    Until 2026-10-10 every install presented the SAME Let's Encrypt certificate, with its private key committed to
    the public repo. That key is gone from the repo; each install now gets its own certificate, issued by a LOCAL
    certificate authority (mkcert) that only this machine's browsers trust. Nothing leaves the machine and nothing
    is shared between installs.

WHAT IT DECIDES (one of three, see `decide`)
    · `use`       — a certificate + key are already in the cert dir and the certificate has not expired.
    · `generate`  — they are missing (or expired) and `mkcert` is installed: issue one for
                    local.zaelar.com, localhost and 127.0.0.1.
    · `http-only` — they are missing and there is no mkcert: the engine runs on plain HTTP (http://localhost works,
                    microphone included, because browsers treat localhost as a secure context) and we print ONE
                    line saying how to enable HTTPS.

    It never runs `mkcert -install`: that adds a root CA to the system and browser trust stores, which is the
    user's call to make. When the local CA is not installed yet we still issue the certificate and say so.

    The server (`server/__main__.py`) only READS the pair — it opens the HTTPS listener when both files exist and
    skips it otherwise — so this runs from the launchers (`./zaelar start`, `make run`, `scripts/zaelar.py start`),
    once per start, not inside the server.

    Standard library only, like `scripts/zaelar.py`: it has to run before (and without) the venv.

    Run: python scripts/tls_cert.py        (exit 0 = HTTPS available, 1 = HTTP only)
"""
from __future__ import annotations

import os
import shutil
import ssl
import subprocess
import sys
import time
from typing import Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(ROOT, "certs", "local.zaelar.com")
CERT_NAME, KEY_NAME = "fullchain.pem", "privkey.pem"
HOSTS = ("local.zaelar.com", "localhost", "127.0.0.1")

USE, GENERATE, HTTP_ONLY = "use", "generate", "http-only"

HINT = ("HTTPS (https://local.zaelar.com:44317) is off: no certificate for this install. To enable it, install "
        "mkcert (macOS: `brew install mkcert`; others: https://github.com/FiloSottile/mkcert), run "
        "`mkcert -install` once, and start Zaelar again. Until then use http://localhost:43917 — the microphone "
        "works there too.")


def cert_dir() -> str:
    """Same lookup the server does: `$ZAELAR_TLS_CERT_DIR`, else certs/local.zaelar.com/ in this checkout."""
    return os.getenv("ZAELAR_TLS_CERT_DIR") or DEFAULT_DIR


def paths(directory: str) -> tuple[str, str]:
    return os.path.join(directory, CERT_NAME), os.path.join(directory, KEY_NAME)


def _expired(certfile: str, now: float | None = None) -> bool:
    """True only when the certificate is READABLE and past its notAfter. Anything we cannot parse counts as valid:
    the server's own TLS setup is the authority on a broken file, and refusing a good one here would be worse."""
    try:
        info = ssl._ssl._test_decode_cert(certfile)  # type: ignore[attr-defined]  # stdlib, no cryptography dep
        not_after = ssl.cert_time_to_seconds(info["notAfter"])
    except Exception:  # noqa: BLE001
        return False
    return not_after <= (time.time() if now is None else now)


def decide(directory: str, mkcert: str | None, *, expired: Callable[[str], bool] = _expired) -> str:
    """Pure decision: which of `use` / `generate` / `http-only` applies to this cert dir."""
    certfile, keyfile = paths(directory)
    have = os.path.isfile(certfile) and os.path.isfile(keyfile)
    if have and not expired(certfile):
        return USE
    return GENERATE if mkcert else HTTP_ONLY


def _ca_installed(mkcert: str, run: Callable) -> bool:
    """mkcert keeps its CA in `mkcert -CAROOT`; no rootCA.pem there means `mkcert -install` was never run."""
    try:
        out = run([mkcert, "-CAROOT"], capture_output=True, text=True, timeout=15)
        root = (out.stdout or "").strip()
        return bool(root) and os.path.isfile(os.path.join(root, "rootCA.pem"))
    except Exception:  # noqa: BLE001
        return False


def ensure(directory: str | None = None, *, which: Callable = shutil.which, run: Callable = subprocess.run,
           say: Callable[[str], None] = print, expired: Callable[[str], bool] = _expired) -> str:
    """Make the decision and act on it. Returns the decision that ended up true (`use` after a successful
    `generate`, `http-only` if generation failed)."""
    directory = directory or cert_dir()
    mkcert = which("mkcert")
    action = decide(directory, mkcert, expired=expired)
    if action == USE:
        return USE
    if action == HTTP_ONLY:
        say(f"ℹ {HINT}")
        return HTTP_ONLY

    certfile, keyfile = paths(directory)
    ca_ready = _ca_installed(mkcert, run)
    os.makedirs(directory, exist_ok=True)
    try:
        res = run([mkcert, "-cert-file", certfile, "-key-file", keyfile, *HOSTS],
                  capture_output=True, text=True, timeout=60)
        ok = getattr(res, "returncode", 1) == 0 and os.path.isfile(certfile) and os.path.isfile(keyfile)
    except Exception as e:  # noqa: BLE001
        say(f"✗ mkcert could not issue the certificate ({e}). {HINT}")
        return HTTP_ONLY
    if not ok:
        err = (getattr(res, "stderr", "") or "").strip().splitlines()[-1:] or ["no output"]
        say(f"✗ mkcert failed ({err[0][:160]}). {HINT}")
        return HTTP_ONLY
    try:
        os.chmod(keyfile, 0o600)
    except OSError as e:
        say(f"! could not restrict the key's permissions ({e}) — check {keyfile}")
    say(f"✓ issued this install's own certificate for {', '.join(HOSTS)} → {directory}")
    if not ca_ready:
        say("ℹ run `mkcert -install` once so your browser trusts it (it adds mkcert's local CA to this machine).")
    return USE


if __name__ == "__main__":
    sys.exit(0 if ensure() == USE else 1)
