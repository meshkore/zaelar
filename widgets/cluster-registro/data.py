#
# cluster-registro widget — backend. Reads kind=="cluster" turns from local MeshKore logs and returns them
# newest-last (the widget renders bottom-anchored). Stdlib only. Never raises: on error returns {"error": "..."}.
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
MAX_TURNS = 400  # cap to keep the payload light
# "Harvey" es un agente FANTASMA: variante fonética con la que el STT confunde la wake-word "zaelar"
# (ver voice/attention.py) que quedó mal-atribuida como peer en el log — nunca fue un peer real del
# cluster. Se filtra en el origen para que ni el registro ni la lista de peers lo muestren.
PHANTOM_PEERS = {"harvey"}


def _meshkore_clusters() -> list[dict]:
    """Raw `/api/meshkore/status` clusters list (loopback, stdlib, 2s timeout). Never raises: unreachable → []."""
    try:
        port = os.environ.get("PORT", "43917")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/meshkore/status",
            headers={"User-Agent": "zaelar-widget/cluster-registro"},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
        return payload.get("clusters") or []
    except Exception:
        return []


def _live_status(cluster: str) -> dict:
    """Ask the in-process MeshKore control-plane for the REAL, current connection state of `cluster`."""
    clusters = _meshkore_clusters()
    if not clusters:
        return {"reachable": False, "connected": False, "online": []}
    for c in clusters:
        if c.get("name") == cluster:
            return {"reachable": True, "connected": bool(c.get("connected")), "online": c.get("online") or []}
    return {"reachable": True, "connected": False, "online": []}


def _active_cluster_name() -> str:
    """El nombre del cluster a usar cuando no hay uno explícito. Bug real 2026-07-25: antes caía a un
    literal "arena" hardcodeado — el operador renombró/reemplazó ese cluster por otro (V2-064: connect_cluster
    reemplaza, no acumula) y los envíos seguían apuntando al nombre VIEJO, muerto. FUENTE DE VERDAD = la conexión
    REAL ahora mismo (`/api/meshkore/status`), nunca un nombre fijo. Vacío ("") si no hay ninguna conectada —
    el llamador debe tratarlo como "no hay cluster", no adivinar."""
    for c in _meshkore_clusters():
        if c.get("connected"):
            return c.get("name") or ""
    return ""


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
    # skip status-only rows (connected/disconnected/error/joined) — the registry is about the conversation
    if not text and direction not in ("in", "out"):
        return None
    role = ev.get("role") or ""
    peer = ev.get("peer") or ev.get("to") or ""
    if peer.strip().lower() in PHANTOM_PEERS:
        return None
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


def _collect() -> list[dict]:
    seen = set()
    out: list[dict] = []
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
            # dedupe by (t_ms, dir, first 80 chars) — sessions often overlap the timeline
            key = (n["t_ms"], n["dir"], n["text"][:80])
            if key in seen:
                continue
            seen.add(key)
            out.append(n)
    out.sort(key=lambda r: r["t_ms"])  # oldest first → most recent at bottom
    if len(out) > MAX_TURNS:
        out = out[-MAX_TURNS:]
    return out


def view_data(q: str = "") -> dict:
    try:
        turns = _collect()
        clusters = sorted({t["cluster"] for t in turns if t["cluster"]})
        peers = sorted({t["peer"] for t in turns if t["peer"]})
        # FUENTE DE VERDAD = la conexión activa AHORA (nunca un nombre fijo ni "el último visto en el log" — un
        # cluster reemplazado, V2-064, deja el log viejo apuntando a un nombre ya muerto).
        cluster_name = _active_cluster_name() or (clusters[0] if clusters else "")
        live = _live_status(cluster_name) if cluster_name else {"reachable": True, "connected": False, "online": []}
        return {
            "cluster": cluster_name,
            "clusters": clusters,
            "peers": peers,
            "count": len(turns),
            "turns": turns,
            "at": time.strftime("%H:%M"),
            "connected": live["connected"],
            "live_reachable": live["reachable"],
            "online_peers": live["online"],
        }
    except Exception as e:
        return {"error": f"No he podido leer el registro del cluster: {e}", "turns": []}


def _send_message(cluster: str, text: str, to: str | None = None) -> dict:
    """POST an outbound message to the MeshKore cluster via the loopback control-plane
    (same host/port/timeout convention as _live_status). `to` = exact peer handle, or None for a
    cluster-wide broadcast. Never raises."""
    try:
        port = os.environ.get("PORT", "43917")
        body = json.dumps({"name": cluster, "to": to, "text": text}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/meshkore/send",
            data=body,
            method="POST",
            headers={"User-Agent": "zaelar-widget/cluster-registro", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=4) as r:
                payload = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            payload = json.loads(e.read().decode("utf-8", "replace"))
        if payload.get("ok"):
            return {"ok": True}
        return {"ok": False, "error": payload.get("error") or "El cluster ha rechazado el mensaje."}
    except Exception as e:
        return {"ok": False, "error": f"No se ha podido enviar: {e}"}


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Chat wall send box — the single data-op, driven both by the widget's own send button and by the brain."""
    payload = payload or {}
    if action == "send":
        text = (payload.get("text") or "").strip()
        to_raw = (payload.get("to") or "").strip()
        out = view_data()
        if not text:
            out["send_error"] = "No hay texto que enviar."
            return out
        cluster_name = out.get("cluster") or ""
        if not cluster_name:
            out["send_error"] = "No hay ningún cluster MeshKore conectado ahora mismo."
            return out
        # Bug real 2026-07-25: esta acción SIEMPRE mandaba `to: None` (broadcast) sin importar lo que pidiera el
        # operador — con un solo peer online funcionaba "por accidente", con varios habría mandado el mensaje a
        # TODOS aunque el operador nombrara uno concreto. Si da un nombre, resuélvelo contra los peers ONLINE
        # (case-insensitive, sin inventar variantes) — nunca "quizá se entienda": si no está online AHORA, el
        # protocolo no lo entrega (no hay historial de mensajes en MeshKore), así que es mejor decirlo claro que
        # mandarlo al vacío en silencio.
        to = None
        if to_raw:
            online = out.get("online_peers") or []
            match = next((p for p in online if p.lower() == to_raw.lower()), None)
            if not match:
                out["send_error"] = (f"«{to_raw}» no está online en «{cluster_name}» ahora mismo — no se puede "
                                      f"entregar. Peers online: {', '.join(online) or 'ninguno'}.")
                return out
            to = match
        result = _send_message(cluster_name, text, to=to)
        out = view_data()
        if not result.get("ok"):
            out["send_error"] = result.get("error")
        else:
            # el log del cluster puede tardar en reflejar el envío (escritura async) — si el
            # turno recién enviado aún no aparece, lo añadimos optimista para que el estado
            # devuelto refleje YA el cambio real ejecutado (no solo el "ok" de la llamada).
            recent_out = [t for t in out.get("turns", [])[-5:] if t.get("dir") == "out" and t.get("text") == text]
            if not recent_out:
                out.setdefault("turns", []).append({
                    "t_ms": int(time.time() * 1000),
                    "ts": time.strftime("%d %b %H:%M"),
                    "cluster": cluster_name,
                    "peer": to or "",
                    "who": "zaelar",
                    "dir": "out",
                    "text": text,
                })
                out["count"] = len(out["turns"])
        return out
    return view_data()
