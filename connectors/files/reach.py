"""The cloud-files family's reach: the date the provider reports for the drive's ROOT (refactor2710-13 T-02).

One `item(root)` call through the same client the browser uses (`gdrive.py` / `onedrive.py`), so a provider that
is not connected or whose tier cannot read answers with the service's own words. Never raises.
"""
from __future__ import annotations

from connectors.reach import Reach

SOURCE = "drive:root:modified"


def earliest_readable(provider: str = "", *, prepared=None) -> Reach:
    """`prepared` = (client, token, api_base, error), as `connectors.files.service._prepared` returns it; a test
    passes its own, the product resolves the connected provider."""
    from connectors.files import service as _svc
    pid = _svc.active_provider(provider) if prepared is None else (provider or "")
    cli, tok, api_base, err = prepared if prepared is not None else _svc._prepared(pid)
    if err or cli is None:
        return Reach(family="cloud_files", provider=pid, source=SOURCE, detail=err or "not_connected")
    try:
        root = cli.item(tok, api_base, "")
    except Exception as e:  # noqa: BLE001 — the provider's refusal is the answer
        return Reach(family="cloud_files", provider=pid, source=SOURCE, detail=type(e).__name__)
    when = str(root.get("modified") or "").strip()
    if not when:
        return Reach(family="cloud_files", provider=pid, source=SOURCE, detail="no_date")
    return Reach(family="cloud_files", provider=pid, earliest=when, source=SOURCE)
