"""nucleo/flash/connector_canon.py — which connector a `show_panel(panel='conectores', connector=…)` names.

There is ONE door to connect a service: the ⚙ «Conectores» section, opened on that connector alone with its
step-by-step guide (`frontend/app/components/ConnectorWizard.js`). The widgets used to carry their own connect
screens and `connect`/`open_connectors` actions — seven of them — and a spoken «conecta mi Drive» had two
plausible destinations, so the model picked one by luck. Those were removed; this maps the model's argument
(an id, a product name, or a word like «calendario») onto the id the section knows.

The vocabulary is the catalog's own (`connectors/catalog/*.json` → id, label, capabilities), so a connector
added there is reachable here without touching this file. `google-contacts` has a live row and no catalog
manifest, hence the one extra entry.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_CATALOG = Path(__file__).resolve().parents[2] / "connectors" / "catalog"
_EXTRA = {"google-contacts": ("Google Contacts", ["contactos", "contacts", "google contacts", "people", "agenda de contactos"])}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@lru_cache(maxsize=1)
def _vocab() -> tuple[tuple[str, tuple[str, ...]], ...]:
    rows: dict[str, list[str]] = {}
    for f in sorted(_CATALOG.glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a broken manifest is the catalog gate's problem, not routing's
            continue
        # `auth: none` (YouTube audio) has nothing to connect, so it must not shadow the account it is named after
        if m.get("kind") == "connector" and m.get("state") == "built" and m.get("auth") != "none":
            rows[m["id"]] = [m["id"], m.get("label", "")] + list(m.get("capabilities") or [])
    for cid, (label, words) in _EXTRA.items():
        rows.setdefault(cid, [cid, label, *words])
    return tuple((cid, tuple(_norm(w) for w in ws if _norm(w))) for cid, ws in rows.items())


def canon_connector(v) -> str:
    """The connector id the argument names, or '' (then the section opens on its list). Exact id first,
    then a whole-phrase match, then the longest vocabulary word contained in the argument — «google drive»
    must beat «google», which is the calendar's id."""
    p = _norm(v)
    if not p:
        return ""
    vocab = _vocab()
    for cid, _ in vocab:
        if p == _norm(cid):
            return cid
    for cid, words in vocab:
        if p in words:
            return cid
    best, size = "", 0
    for cid, words in vocab:
        for w in words:
            if len(w) > size and re.search(rf"\b{re.escape(w)}\b", p):
                best, size = cid, len(w)
    return best
