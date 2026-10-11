"""nucleo/flash/asked_site.py — rows delivered from another site than the one he asked for say so (V2-782).

search-buy-used-car ES (2026-10-11): «Busca anuncios… en coches.net». coches.net answered «Ups! Parece que algo no va
bien», Milanuncios «Pardon Our Interruption», and the worker went to AutoScout24 — said only in the progress pings
(«Coches.net y Milanuncios bloquean el acceso automático»). The chat turn that delivered «Fiat Tipo — € 10.490» never
said where it came from, so he believed he was reading coches.net.

A fact of three readings, none of them a model's: the sites HIS words named (a domain), the hosts of the rows being
delivered (their urls on the sheet), and whether the errand recorded that site as blocked (the sheet's Sources tab
with a blocked/error status, or the errand's own progress lines naming it next to a block). When the delivered rows
come from none of the sites he named, the delivery says so — once per site and set of hosts.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from search.asked import norm as _norm

_DOMAIN = re.compile(r"\b([a-z0-9][a-z0-9-]{1,40}\.(?:com|net|es|org|co\.uk|de|fr|it|io|eu|us))\b")
_BLOCK = re.compile(r"(bloque|block|captcha|anti-?bot|denied|denegad|forbidden|pardon our|algo no va bien|cerr[oó] la "
                    r"puerta|no (me )?dej)")
_SAID: set = set()


def forget() -> None:
    _SAID.clear()


def _host(url: str) -> str:
    try:
        h = urlparse(str(url or "")).netloc.lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def _rows_and_sheet(titles: list[str]) -> tuple[list[dict], dict]:
    from widgets.results import data as _d
    want = {_norm(t.split(" — ")[0].rstrip("…")) for t in titles if t}
    for sid in reversed(_d.sheets()):
        view = _d.view_data(sid)
        hits = [i for i in view.get("items") or [] if _norm(str(i.get("title") or "").rstrip("…")) in want]
        if hits:
            return hits, view
    return [], {}


def _blocked(site: str, view: dict) -> bool:
    for s in view.get("sources") or []:
        if site in (str(s.get("url") or "") + " " + str(s.get("name") or "")).lower() \
                and s.get("status") in ("blocked", "error", "auth"):
            return True
    try:
        from nucleo import dispatch as _disp
        for t in _disp.pending_summaries() or []:
            rec = _disp.get_record(t.get("id"))
            lines = [str(t.get("phase") or ""), str(t.get("note") or "")] + [
                str((p.get("s") if isinstance(p, dict) else p) or "") for p in (getattr(rec, "phases", None) or [])]
            for line in lines:
                n = _norm(line)
                if site.split(".")[0] in n and _BLOCK.search(n):
                    return True
    except Exception as e:  # noqa: BLE001 — without the record, only the Sources tab speaks
        __import__("logging").getLogger(__name__).debug("asked_site: records unreadable: %s", e)
    return False


def note(user_text: str, delivered: list[str]) -> str:
    """The sentence owed with this delivery, or "". Never raises."""
    try:
        sites = list(dict.fromkeys(_DOMAIN.findall(_norm(user_text))))
        if not sites or not delivered:
            return ""
        rows, view = _rows_and_sheet(delivered)
        hosts = sorted({h for h in (_host(r.get("url")) for r in rows) if h})
        if not hosts or any(h.endswith(s) for s in sites for h in hosts):
            return ""
        site = sites[-1]                              # the one he named last is the one he is waiting on
        key = (site, tuple(hosts))
        if key in _SAID:
            return ""
        _SAID.add(key)
        from i18n import langs as _langs
        lang = _langs.current_language()
        line = lang.asked_site_blocked if _blocked(site, view) else lang.asked_site_elsewhere
        return line.format(site=site, hosts=", ".join(hosts[:3]))
    except Exception as e:  # noqa: BLE001
        __import__("logging").getLogger(__name__).warning("asked_site failed: %s", e)
        return ""
