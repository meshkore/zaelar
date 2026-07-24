#
# realiza-cambio-real widget — backend. Groups kind=="cluster" log turns PER CLUSTER (name, connected, peers,
# last activity, a short "recent" tail of turns) so the widget can render a compact list on the left and a
# short side-panel view of ONE selected cluster on the right, entirely client-side. Stdlib only. Never raises.
#
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS = REPO_ROOT / ".meshkore" / "logs"
TIMELINE = LOGS / "timeline-latest.jsonl"
SESSIONS_DIR = LOGS / "sessions"
MAX_TURNS_PER_CLUSTER = 6  # short side-panel view — only the tail, not the full registry


def _live_status() -> dict:
    """Ask the in-process MeshKore control-plane for REAL connection state per cluster (loopback-only
    /api/meshkore/status, stdlib GET, 2s timeout). Never raises: unreachable -> empty map."""
    try:
        port = os.environ.get("PORT", "43917")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/meshkore/status",
            headers={"User-Agent": "zaelar-widget/realiza-cambio-real"},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
        out = {}
        for c in payload.get("clusters") or []:
            name = c.get("name")
            if name:
                out[name] = {"connected": bool(c.get("connected")), "online": c.get("online") or []}
        return out
    except Exception:
        return {}


def _iter_lines(path: Path):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except Exception:
        return


def _norm(ev: dict) -> dict | None:
    """Keep only kind=='cluster' events that carry a message (drop pure status pings)."""
    if ev.get("kind") != "cluster":
        return None
    text = (ev.get("text") or "").strip()
    direction = ev.get("dir") or ""
    if not text and direction not in ("in", "out"):
        return None
    role = ev.get("role") or ""
    peer = ev.get("peer") or ev.get("to") or ""
    who = "peer" if (direction == "in" or role == "peer") else ("zaelar" if direction == "out" or role == "assistant" else (role or "system"))
    t_ms = int(ev.get("t_ms") or 0)
    return {
        "t_ms": t_ms,
        "ts": time.strftime("%d %b %H:%M", time.localtime(t_ms / 1000.0)) if t_ms else "",
        "cluster": ev.get("cluster") or "",
        "peer": peer,
        "who": who,
        "dir": direction or ("note" if role == "assistant" else ""),
        "text": text or (ev.get("label") or ""),
    }


def _collect_by_cluster() -> dict:
    seen = set()
    by_cluster: dict[str, list[dict]] = {}
    files: list[Path] = []
    if TIMELINE.exists():
        files.append(TIMELINE)
    if SESSIONS_DIR.exists():
        try:
            files += sorted(SESSIONS_DIR.glob("*.jsonl"))
        except Exception:
            pass
    for p in files:
        for ev in _iter_lines(p):
            n = _norm(ev)
            if not n:
                continue
            key = (n["cluster"], n["t_ms"], n["dir"], n["text"][:80])
            if key in seen:
                continue
            seen.add(key)
            by_cluster.setdefault(n["cluster"], []).append(n)
    for name in by_cluster:
        by_cluster[name].sort(key=lambda r: r["t_ms"])
    return by_cluster


def view_data(q: str = "") -> dict:
    try:
        by_cluster = _collect_by_cluster()
        live = _live_status()
        clusters = []
        names = sorted(set(by_cluster) | set(live))
        for name in names:
            turns = by_cluster.get(name, [])
            peers = sorted({t["peer"] for t in turns if t.get("peer")})
            last = turns[-1] if turns else None
            live_c = live.get(name, {})
            clusters.append({
                "name": name,
                "connected": bool(live_c.get("connected")),
                "live_reachable": name in live or bool(live),
                "peers": peers,
                "peer_count": len(peers),
                "count": len(turns),
                "last_ts": last["ts"] if last else "",
                "last_text": (last["text"][:90] if last else ""),
                "recent": turns[-MAX_TURNS_PER_CLUSTER:],
            })
        return {"clusters": clusters, "at": time.strftime("%H:%M")}
    except Exception as e:
        return {"error": f"No he podido leer los clusters: {e}", "clusters": []}
