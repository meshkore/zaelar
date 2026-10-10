"""search/health.py — is every search provider ALIVE, and known to be alive? (V2-782 F2)

    ./.venv/bin/python -m search.health             # one line per provider, names only
    ./.venv/bin/python -m search.health --json
    ./.venv/bin/python -m search.health --engine http://127.0.0.1:7801   # asks a running engine (adds the Chromium)

WHY. On 2026-10-10 the engine held no key for any paid search index; every inline search in the sweep fell to
DuckDuckGo; the listing pass said «no unlocker token» on all six hunts; the workers' built-in search answered
«Weekly/Monthly Limit Exhausted» eighteen times; Foursquare's key had no credits. None of that was visible
anywhere but in the timelines of failed rounds — and the rounds were graded as product failures. This module
makes ONE minimal real call per provider and says, per provider, one of:

  live       it answered
  missing    no key — reported as missing, never as down (the fix is a key, not a bug)
  off        switched off by env (`BROWSER_SEARCH=0`)
  exhausted  quota, credits or rate limit (HTTP 429, «limit», «credits»)
  credential key refused (HTTP 401/403, «invalid key»)
  blocked    a bot challenge instead of results (captcha)
  network    timeout / no route
  down       any other error
  engine     needs the running engine (the warm Chromium lives on the server loop) — `--engine` asks it

Names only: the key's env var NAME travels in the report, its value never leaves the provider's HTTP header.
The use-case harness calls `summary()` before a batch (T2.3): with no provider able to answer, a round is INFRA,
not a product failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from .providers import PROVIDERS
from .providers import keys as _keys

_PROBE_TIMEOUT_S = 25.0

_KIND_NEEDLES = (
    ("exhausted", ("429", "quota", "limit exhausted", "rate limit", "too many requests", "no api credits",
                   "credits remaining", "insufficient", "resource_exhausted")),
    ("credential", ("401", "403", "api key", "unauthorized", "forbidden", "invalid key", "permission_denied",
                    "api_key_invalid")),
    ("blocked", ("captcha", "unusual traffic", "/sorry/", "bots use duckduckgo", "made by a human", "squares containing",
                 "are you a robot", "bloqueado")),
    ("network", ("timeout", "timed out", "connect", "dns", "unreachable", "ssl", "name or service")),
)


def classify(detail: str) -> str:
    low = (detail or "").lower()
    for kind, needles in _KIND_NEEDLES:
        if any(n in low for n in needles):
            return kind
    return "down"


# ── one minimal call per provider ────────────────────────────────────────────────────────────────
def _call(name: str) -> tuple[bool, str]:
    """`(answered, note)` — raises on failure; the caller classifies."""
    from . import web as _web
    if name == "perplexity":
        r = _web._perplexity("What year is it?", 1)
        return bool(r.get("answer") or r.get("results")), ""
    if name == "tavily":
        r = _web._tavily("current year", 1)
        return bool(r.get("answer") or r.get("results")), ""
    if name == "brave":
        r = _web._brave("wikipedia", 1)
        return bool(r.get("results")), ""
    if name == "openai":
        from .providers import openai as _p
        r = _p.search("What is today's date?", 1)
        return bool(r.get("answer")), "" if r.get("results") else "answer without citations"
    if name == "gemini":
        from .providers import gemini as _p
        r = _p.search("What is today's date?", 1)
        return bool(r.get("answer")), "" if r.get("results") else "answer without citations"
    if name == "zai":
        from .providers import zai as _p
        r = _p.search("wikipedia", 1)
        return True, "" if r.get("results") else "HTTP 200, 0 results"
    if name == "ddg":
        r = _web._ddg("wikipedia", 1)
        return bool(r.get("results")), "" if r.get("results") else "0 results"
    if name == "foursquare":
        from .providers import foursquare as _p
        rows = _p.places("cafe", near="Madrid, ES", k=1)
        return True, "" if rows else "0 results"
    if name in ("brightdata_serp", "brightdata_unlocker"):
        from . import listing as _listing
        zone = _listing._bd_zone_serp() if name == "brightdata_serp" else _listing._bd_zone_unlocker()
        _listing._bd_request({"zone": zone, "url": "https://example.com/", "format": "raw"}, provider=name)
        return True, f"zone {zone}"
    if name in ("google", "images"):
        from . import browser as _browser
        if _browser._loop is None or not _browser._loop.is_running():
            raise _NeedsEngine()
        if name == "google":
            r = _browser.search_sync("wikipedia", 1)
            return bool(r.get("results") or r.get("answer")), ""
        r = _browser.images_sync("wikipedia logo", 3)
        if r.get("blocked"):
            raise RuntimeError("captcha: the image index served a bot challenge")
        return bool(r.get("items")), f"index {r.get('source') or '?'}"
    raise RuntimeError(f"no probe for {name}")


class _NeedsEngine(RuntimeError):
    pass


def probe(name: str) -> dict:
    """One provider → `{provider, kind, state, ok, latency_ms, why, key, paid}`."""
    p = PROVIDERS[name]
    row = {"provider": name, "kind": p.kind, "paid": p.paid, "key": _keys.key_name(name), "ok": False,
           "latency_ms": 0, "state": "", "why": ""}
    if p.env_switch[0] and (os.getenv(p.env_switch[0]) or "") == p.env_switch[1]:
        row.update(state="off", why=f"{p.env_switch[0]}={p.env_switch[1]}")
        return row
    if p.keys and not _keys.key(name):
        row.update(state="missing", why=f"set {row['key']} to enable it")
        return row
    t0 = time.monotonic()
    try:
        answered, note = _call(name)
        row["latency_ms"] = int((time.monotonic() - t0) * 1000)
        row.update(ok=bool(answered), state="live" if answered else "down", why=note if answered else (note or "no answer"))
    except _NeedsEngine:
        row.update(state="engine", why="the warm Chromium lives on the engine's loop — ask /api/search/health")
    except Exception as e:  # noqa: BLE001 — a probe REPORTS failure, it never is one
        row["latency_ms"] = int((time.monotonic() - t0) * 1000)
        detail = f"{type(e).__name__}: {str(e)[:200]}"
        row.update(state=classify(detail), why=detail)
    return row


def probe_all(names=None, *, parallel: bool = True) -> list[dict]:
    names = list(names or PROVIDERS)
    if not parallel or len(names) == 1:
        return [probe(n) for n in names]
    with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
        return list(pool.map(probe, names))


def summary(rows: list[dict]) -> dict:
    """What the harness and the panel need in one glance."""
    live = [r["provider"] for r in rows if r["state"] == "live"]
    kinds_live = {PROVIDERS[r["provider"]].kind for r in rows if r["state"] == "live"}
    return {
        "live": live,
        "missing": [r["provider"] for r in rows if r["state"] == "missing"],
        "failing": [{"provider": r["provider"], "state": r["state"], "why": r["why"][:120]} for r in rows
                    if r["state"] not in ("live", "missing", "off", "engine")],
        "can_answer": bool(kinds_live & {"answer", "results"}),
        "can_discover": "results" in kinds_live,
        "can_place": "places" in kinds_live,
        "probed_at": time.time(),
    }


_MARK = {"live": "✓", "missing": "·", "off": "·", "exhausted": "✗", "credential": "✗", "blocked": "✗", "network": "✗",
         "down": "✗", "engine": "?"}


def render(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        key = f"({r['key']})" if r.get("key") else "(no key)"
        lat = f"{r['latency_ms']:>6} ms" if r.get("latency_ms") else " " * 9
        why = f"  {r['why']}" if r.get("why") else ""
        lines.append(f"{_MARK.get(r['state'], '?')} {r['provider']:<20} {r['state']:<10} {lat}  {key}{why}")
    s = summary(rows)
    verdict = ("the service CAN answer" if s["can_answer"] else "NO provider can answer — a round now is INFRA")
    lines.append(f"— {len(s['live'])} live · {len(s['missing'])} missing · {len(s['failing'])} failing · {verdict}")
    return "\n".join(lines)


def _load_credentials() -> None:
    """The CLI runs outside the server: load the same two files `server/common.py` loads, names into the env."""
    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001
        return
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(root, ".env"), override=False)
    load_dotenv(os.path.join(root, ".meshkore", "credentials", "zaelar.env"), override=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m search.health", description="one minimal real call per search provider")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--engine", default="", help="a running engine's base url (adds the Chromium probes)")
    ap.add_argument("--only", default="", help="comma-separated provider names")
    a = ap.parse_args(argv)
    _load_credentials()
    if a.engine:
        import urllib.request
        with urllib.request.urlopen(a.engine.rstrip("/") + "/api/search/health?fresh=1", timeout=90) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        rows = payload.get("providers") or []
    else:
        names = [n.strip() for n in a.only.split(",") if n.strip()] or None
        rows = probe_all(names)
    if a.json:
        print(json.dumps({"providers": rows, "summary": summary(rows)}, ensure_ascii=False, indent=1))
    else:
        print(render(rows))
    return 0 if summary(rows)["can_answer"] else 2


if __name__ == "__main__":
    sys.exit(main())
