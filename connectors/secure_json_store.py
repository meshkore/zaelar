"""connectors/secure_json_store.py — atomic, owner-only-readable JSON file (V2-098).

The same handful of lines — read JSON with a safe empty-dict fallback, write via tmp-file + os.replace +
chmod 600 — was hand-rolled independently in `connectors/spotify/auth.py`, `connectors/email/oauth.py` and
`connectors/meshkore/store.py`. One of the three (`meshkore/store.py`) wrote directly to the target file with
no tmp/replace step — a crash mid-write could leave a truncated `config/meshkore.json` behind. This gives
everyone the atomic version; each caller keeps its own module-level `_load()`/`_save()` wrapper (and whatever
exception handling it already had) delegating to an instance of this class.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class SecureJsonStore:
    """A JSON dict persisted at `path`: atomic write, chmod 600 applied to the temp file BEFORE the rename so
    the target never has a window at default (world/group-readable) permissions."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self.path) + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
