"""connectors/oauth_pkce.py — PKCE (S256) verifier/challenge generation (V2-098).

The same base64url + sha256 math was hand-rolled independently in `connectors/spotify/auth.py` and
`connectors/email/oauth.py` (the latter's own comment: "Pattern copied from spotify/auth.py"). Only the PKCE
math is shared here — the surrounding OAuth flow (authorize/exchange/refresh) keeps its own shape per module:
email's is multi-account (keyed by provider:address) and spotify's is single-account with a built-in default
client_id, different enough that forcing them into one generic flow would be the wrong abstraction.
"""
from __future__ import annotations

import base64
import hashlib
import os


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def make_pkce(seed: bytes | None = None) -> tuple[str, str]:
    """(verifier, S256 challenge). `seed` injectable for deterministic tests; production = os.urandom."""
    verifier = b64url(seed if seed is not None else os.urandom(48))
    challenge = b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def make_state(nbytes: int = 18) -> str:
    """Random `state` param for the authorize URL / callback matching."""
    return b64url(os.urandom(nbytes))
