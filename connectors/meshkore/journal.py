#
# MeshKore journal — a DEDICATED, append-only post-mortem log for everything that happens on the cluster channel.
#
# The voice /debug timeline (voice/observer.py) is reset per voice session, and cluster activity can happen with NO
# voice session open. So we ALSO append every cluster event here — inbound/outbound messages, presence, brain
# turns, AND connection failures (auth rejected, kicked, network) — to `.meshkore/logs/meshkore.jsonl`. This is the
# file to read when "it didn't connect / it went quiet / they threw us out" and you need to know exactly why.
#
import json
import os
import time
from pathlib import Path

from connectors.meshkore import store

LOG_FILE = Path(__file__).resolve().parents[2] / ".meshkore" / "logs" / "meshkore.jsonl"


def record(event: dict):
    """Append one redacted, timestamped line. Best-effort — never raises into the caller."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts_ms": round(time.time() * 1000), **event}, ensure_ascii=False)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(store.redact(line) + "\n")
    except Exception:
        pass


def last_exchange(cluster: str, peer: str) -> dict:
    """Was the peer's last MESSAGE to us ever answered? Scans THIS journal (the only cluster history that
    survives a restart — the voice /debug timeline resets per session, see module docstring) for the last
    inbound message from `peer` and the last outbound send TO `peer` (or a broadcast, which counts as reaching
    everyone present). Returns {"last_in_ts", "last_in_text", "last_out_ts"} (None where never seen).

    Used on (re)connect (bridge.py's "ready"/"presence" handlers, 2026-07-25 fix): the operator's own report —
    "I start this up 3 days later and there are messages we never replied to" — a peer can message us while we
    are offline for days, and unlike a real chat app there is no server-side unread count for a MeshKore cluster
    (`client.py`: 'No message history — relay to whoever is connected now'). We have to reconstruct it ourselves
    from our OWN journal. Best-effort, never raises: reads the whole file (infrequent, off-hot-path — only fires
    on reconnect/presence, not per turn)."""
    last_in_ts = last_out_ts = None
    last_in_text = ""
    peer_l = (peer or "").strip().lower()
    if not peer_l:
        return {"last_in_ts": None, "last_in_text": "", "last_out_ts": None}
    try:
        with LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                ts = ev.get("ts_ms")
                if not isinstance(ts, (int, float)):
                    continue
                if ev.get("chan") == "in" and ev.get("kind") == "message" and ev.get("cluster") == cluster:
                    frm = (ev.get("from") or "").strip().lower()
                    if frm == peer_l and (last_in_ts is None or ts > last_in_ts):
                        payload = ev.get("payload")
                        text = payload if isinstance(payload, str) else (payload or {}).get("text", "")
                        last_in_ts, last_in_text = ts, text or ""
                elif ev.get("chan") == "out" and ev.get("action") == "cluster.send":
                    extra = ev.get("extra") or {}
                    if extra.get("name") != cluster:
                        continue
                    to = (extra.get("data") or {}).get("to")
                    if (to is None or (to or "").strip().lower() == peer_l) and (last_out_ts is None or ts > last_out_ts):
                        last_out_ts = ts
    except Exception:
        pass
    return {"last_in_ts": last_in_ts, "last_in_text": last_in_text, "last_out_ts": last_out_ts}
