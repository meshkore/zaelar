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
