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


def unique_name(name: str, cluster_id: str) -> str:
    """Alias LIBRE para `cluster_id`, sin pisar a otro cluster (V2-086).

    Bug real cazado probando el flujo: el modelo, al conectar a MeshKore Commons, eligió el alias por defecto
    `meshcore` — que ya era el del cluster PRIVADO del operador. Guardar ahí habría SOBRESCRITO sus credenciales
    (token incluido) por las de un cluster público. El alias lo elige un modelo, así que la unicidad no puede
    depender de que acierte: se garantiza aquí, en código. Mismo nombre + mismo cluster_id = reconexión legítima
    (se reutiliza); mismo nombre + OTRO cluster_id = colisión → se sufija (`meshcore-2`)."""
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
    """Persiste las credenciales de un cluster. `vis="public"` (V2-086) marca un cluster ABIERTO: se guarda con
    `token` vacío a propósito — no es un dato que falte, es que ese cluster no usa credencial."""
    d = _read()
    prev = d.get(name) or {}
    entry = {"cluster_id": cluster_id, "token": token, "handle": handle}
    if vis:
        entry["vis"] = vis
    if prev.get("perms"):                       # NO pisar el perfil de permisos al re-guardar creds (V2-076)
        entry["perms"] = prev["perms"]
    d[name] = entry
    _write(d)


# ── PERMISOS por-CLUSTER (V2-076) — perfil de capacidades que el OPERADOR concede a un cluster ────────────────
# Por defecto: DENEGAR TODO (un cluster nuevo = seguridad máxima; sin workers, sin código, sin ejecución). El
# operador lo eleva al CONECTAR (confirm-gate). Vive junto a las creds en config/meshkore.json (chmod 600), lo lee
# el autoreconnect sin plumbing nuevo. Vocabulario CERRADO: un permiso solo AMPLÍA capacidad, nunca la del peer;
# lo concede el operador, nunca el peer. NO se mezcla con el PACTO (por-peer, cápsula) — esto es por-cluster.
DEFAULT_PERMS = {
    "workers": False,    # ¿puede escalar a un brainworker (investigación/tareas)?
    "code": False,       # ¿puede un dev worker escribir/probar código?
    "repo": None,        # repo autorizado para git push (p.ej. "meshkore/zalo-...") o None
    "execute": False,    # ¿puede ejecutar código en el sandbox?
    "deploy": False,     # ¿puede desplegar?
}


def get_perms(name: str) -> dict:
    """Perfil de permisos VIGENTE del cluster (defaults DENY si no hay). Siempre devuelve las claves completas."""
    p = dict(DEFAULT_PERMS)
    stored = (_read().get(name) or {}).get("perms")
    if isinstance(stored, dict):
        p.update({k: stored[k] for k in stored if k in DEFAULT_PERMS})
    return p


def set_perms(name: str, perms: dict) -> dict:
    """Fija/actualiza (merge) el perfil de permisos del cluster. Solo claves del vocabulario cerrado. Persiste."""
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
    """Mejor fuente para un connect: args explícitos > staged > persistido. None si no hay con qué conectar.

    V2-086 — DOS clases de cluster, y la diferencia importa:
      · PRIVADO: hace falta `cluster_id` + `token`. Sin token no hay nada que hacer.
      · PÚBLICO (`vis="public"`, p.ej. MeshKore Commons): basta el `cluster_id`; el token NO existe y exigirlo
        era justo lo que impedía entrar. El handle lo eliges tú.
    Antes la condición era `if cluster_id and token`, así que un cluster público caía al `take_staged/get_cluster`
    y acababa en «no cluster_id/token (paste them first)» aunque el operador hubiera dado el id correcto."""
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
