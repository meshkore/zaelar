#
# MeshKore connector — credential persistence + secret staging + redaction.
#
# Cluster credentials (cluster_id + token) are SECRETS. They live in config/meshkore.json (gitignored, chmod 600),
# NEVER in git and NEVER printed to the debug timeline. Two ways a cluster becomes known:
#   • the brain emits [[cluster.connect]] with the creds it read from the pasted blob → save_cluster()
#   • a REST/paste hits POST /api/meshkore/stage → stage() (short-lived, in-memory), then a name-only connect
#     resolves the secret from staging so the token need not travel back through the LLM output.
#
import json
import os
import re
from pathlib import Path

from loguru import logger

CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "meshkore.json"

_staged: dict = {}   # name -> {cluster_id, token, handle} — ephemeral, process-lifetime only


# ── persisted cluster configs (for reconnect across restarts) ────────────────────────────────────────────────
def _read() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(d: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)   # tokens inside — owner-only
    except Exception:
        pass


def save_cluster(name: str, cluster_id: str, token: str, handle: str = "zaelar"):
    d = _read()
    d[name] = {"cluster_id": cluster_id, "token": token, "handle": handle}
    _write(d)


def remove_cluster(name: str):
    d = _read()
    if name in d:
        d.pop(name)
        _write(d)


def load_clusters() -> dict:
    """All persisted cluster configs {name: {cluster_id, token, handle}}."""
    return _read()


def get_cluster(name: str) -> dict | None:
    return _read().get(name)


# ── ephemeral staging (paste → connect-by-name without the token going through the LLM) ──────────────────────
def stage(name: str, cluster_id: str, token: str, handle: str = "zaelar"):
    _staged[name] = {"cluster_id": cluster_id, "token": token, "handle": handle}


def take_staged(name: str) -> dict | None:
    return _staged.get(name)


def resolve(name: str, cluster_id: str = "", token: str = "", handle: str = "") -> dict | None:
    """Best source of truth for a connect: explicit args > staged > persisted. Returns full creds or None."""
    if cluster_id and token:
        return {"cluster_id": cluster_id, "token": token, "handle": handle or "zaelar"}
    return take_staged(name) or get_cluster(name)


# ── redaction (keep tokens/secrets out of the timeline / logs / journal) ─────────────────────────────────────
_TOKEN_KEYS = re.compile(r'("(?:token|secret|password)"\s*:\s*")([^"]+)(")', re.I)
# Secret-shaped substrings that must never land in a log line even inside free text (peer content is journaled).
_SECRET_SHAPES = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{12,}", re.I),
    re.compile(r"\bdid:key:z[1-9A-HJ-NP-Za-km-z]{20,}\b"),
]


def redact(text: str) -> str:
    """Mask token-like values in any string bound for logs / the /debug timeline / SSE / the journal. Covers JSON
    token keys, common secret shapes (keys/JWT/bearer/did:key), and live cluster tokens seen in free text."""
    if not text:
        return text
    out = _TOKEN_KEYS.sub(lambda m: m.group(1) + "***" + m.group(3), text)
    for rx in _SECRET_SHAPES:
        out = rx.sub("[redacted]", out)
    for tok in known_tokens():
        if tok and tok in out:
            out = out.replace(tok, "***")
    return out


def known_tokens() -> list:
    """Live token strings (staged + persisted) so callers can scrub them from free text too."""
    toks = []
    for src in (_staged.values(), _read().values()):
        for c in src:
            t = c.get("token")
            if t and len(t) >= 6:
                toks.append(t)
    return toks
