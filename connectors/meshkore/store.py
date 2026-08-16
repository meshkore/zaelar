#
# MeshKore connector — credential persistence + secret staging + redaction.
#
# Cluster credentials (cluster_id + token) are SECRETS. They live in config/meshkore.json (gitignored, chmod 600),
# NEVER in git and NEVER printed to the debug timeline. Two ways a cluster becomes known:
#   • the brain emits [[cluster.connect]] with the creds it read from the pasted blob → save_cluster()
#   • a REST/paste hits POST /api/meshkore/stage → stage() (short-lived, in-memory), then a name-only connect
#     resolves the secret from staging so the token need not travel back through the LLM output.
#
import os
import re
from pathlib import Path

from loguru import logger

from connectors.secure_json_store import SecureJsonStore
from nucleo import workspace as _workspace


def _config_file() -> Path:
    """Where cluster credentials live. Same criterion as `config/credentials.py::_store_path()` and
    `meshkore/identity.py::_key_file()`: when `ZAELAR_WORKSPACE` is set, the file moves to the workspace.

    V2-086 — this used to be a fixed ABSOLUTE path, escaping isolation. The disposable `journey` engine runs with
    `ZAELAR_WORKSPACE` in a temp location (DB, memory, canvas...), but this module kept reading the operator's REAL
    `config/meshkore.json`: tests saw their real clusters and — worse — a case that managed to connect would have
    OVERWRITTEN their credentials from a test suite. Without the env var (self-host today), the path is byte-for-byte
    the same as before."""
    if os.getenv("ZAELAR_WORKSPACE"):
        return _workspace.root() / "config" / "meshkore.json"
    return Path(__file__).resolve().parents[2] / "config" / "meshkore.json"


CONFIG_FILE = _config_file()

_staged: dict = {}   # name -> {cluster_id, token, handle} — ephemeral, process-lifetime only


# ── persisted cluster configs (for reconnect across restarts) ────────────────────────────────────────────────
# A fresh SecureJsonStore(CONFIG_FILE) per call, not a module-level singleton: tests monkeypatch
# `store.CONFIG_FILE` to a tmp path, which a cached instance bound to the ORIGINAL path would ignore. V2-098:
# this used to write CONFIG_FILE directly with no tmp+replace step — a crash mid-write could truncate it; now
# atomic, same mechanics shared with spotify/email OAuth token stores.
def _read() -> dict:
    return SecureJsonStore(CONFIG_FILE).load()


def _write(d: dict):
    SecureJsonStore(CONFIG_FILE).save(d)


def unique_name(name: str, cluster_id: str) -> str:
    """Free alias for `cluster_id`, without overwriting another cluster (V2-086).

    Real bug caught while testing the flow: when connecting to MeshKore Commons, the model chose the default alias
    `meshcore` — already used by the operator's PRIVATE cluster. Saving there would have OVERWRITTEN their
    credentials (token included) with a public cluster's credentials. A model chooses the alias, so uniqueness cannot
    depend on it guessing right: it is guaranteed here, in code. Same name + same cluster_id = legitimate reconnect
    (reuse); same name + OTHER cluster_id = collision -> suffix (`meshcore-2`)."""
    name = (name or "").strip() or "cluster"
    d = _read()
    prev = d.get(name)
    if not prev or str(prev.get("cluster_id") or "") == str(cluster_id or ""):
        return name
    for n in range(2, 100):
        cand = f"{name}-{n}"
        c = d.get(cand)
        if not c or str(c.get("cluster_id") or "") == str(cluster_id or ""):
            return cand
    return f"{name}-{str(cluster_id)[:6]}"


def save_cluster(name: str, cluster_id: str, token: str, handle: str = "zaelar", vis: str = ""):
    """Persist a cluster's credentials. `vis="public"` (V2-086) marks an OPEN cluster: saved with an intentionally
    empty `token` — it is not missing data; that cluster uses no credential."""
    d = _read()
    prev = d.get(name) or {}
    entry = {"cluster_id": cluster_id, "token": token, "handle": handle}
    if vis:
        entry["vis"] = vis
    if prev.get("perms"):                       # do NOT overwrite the permission profile when re-saving creds (V2-076)
        entry["perms"] = prev["perms"]
    d[name] = entry
    _write(d)


# ── per-CLUSTER PERMISSIONS (V2-076) — capability profile the OPERATOR grants to a cluster ─────────────────────
# Default: DENY ALL (new cluster = maximum security; no workers, no code, no execution). The operator elevates it on
# CONNECT (confirm-gate). Lives beside creds in config/meshkore.json (chmod 600), read by autoreconnect without new
# plumbing. CLOSED vocabulary: a permission only EXPANDS capability, never the peer's; granted by the operator, never
# the peer. Does NOT mix with the PACT (per-peer, capsule) — this is per-cluster.
DEFAULT_PERMS = {
    "workers": False,    # can it escalate to a brainworker (research/tasks)?
    "code": False,       # can a dev worker write/test code?
    "repo": None,        # authorized repo for git push (e.g. "meshkore/zalo-...") or None
    "execute": False,    # can it execute code in the sandbox?
    "deploy": False,     # can it deploy?
}


def get_perms(name: str) -> dict:
    """Current cluster permission profile (DENY defaults if absent). Always returns the complete key set."""
    p = dict(DEFAULT_PERMS)
    stored = (_read().get(name) or {}).get("perms")
    if isinstance(stored, dict):
        p.update({k: stored[k] for k in stored if k in DEFAULT_PERMS})
    return p


def set_perms(name: str, perms: dict) -> dict:
    """Set/update (merge) the cluster permission profile. Only closed-vocabulary keys. Persists."""
    d = _read()
    entry = d.get(name) or {}
    cur = dict(entry.get("perms") or DEFAULT_PERMS)
    for k, v in (perms or {}).items():
        if k in DEFAULT_PERMS:
            cur[k] = v
    entry["perms"] = cur
    d[name] = entry
    _write(d)
    return cur


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
def stage(name: str, cluster_id: str, token: str, handle: str = "zaelar", vis: str = ""):
    _staged[name] = {"cluster_id": cluster_id, "token": token, "handle": handle, "vis": vis}


def take_staged(name: str) -> dict | None:
    return _staged.get(name)


def resolve(name: str, cluster_id: str = "", token: str = "", handle: str = "",
            vis: str = "") -> dict | None:
    """Best source for connect: explicit args > staged > persisted. None if there is nothing to connect with.

    V2-086 — TWO cluster classes, and the difference matters:
      · PRIVATE: requires `cluster_id` + `token`. Without token, there is nothing to do.
      · PUBLIC (`vis="public"`, e.g. MeshKore Commons): `cluster_id` is enough; the token does NOT exist and requiring
        it was exactly what blocked entry. You choose the handle.
    Previously the condition was `if cluster_id and token`, so a public cluster fell through to
    `take_staged/get_cluster` and ended at "no cluster_id/token (paste them first)" even if the operator had provided
    the correct id."""
    if cluster_id and (token or vis == "public"):
        return {"cluster_id": cluster_id, "token": token, "handle": handle or "zaelar", "vis": vis}
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
