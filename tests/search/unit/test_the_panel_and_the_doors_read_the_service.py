"""The status panel's search line, the fact door of both channels, and the brief's asked fields (V2-782 T2.2 / T5.3 / T4.3)."""
from __future__ import annotations

from nucleo import research
from search import api as _api


def test_the_status_line_says_who_is_live_and_who_is_not(monkeypatch):
    monkeypatch.setattr(_api, "_health_cache", {"at": 0.0, "rows": []})
    assert _api.status_item()["detail"] == "sin sondear todavía"
    rows = [{"provider": "zai", "kind": "results", "state": "live", "why": "", "paid": True, "key": "Z_AI_API_KEY", "ok": True, "latency_ms": 1},
            {"provider": "foursquare", "kind": "places", "state": "exhausted", "why": "HTTP 429 no credits", "paid": True,
             "key": "FOURSQUARE_SERVICE_KEY", "ok": False, "latency_ms": 1},
            {"provider": "brave", "kind": "results", "state": "missing", "why": "", "paid": True, "key": "BRAVE_SEARCH_KEY", "ok": False, "latency_ms": 0}]
    monkeypatch.setattr(_api, "_health_cache", {"at": 1.0, "rows": rows})
    item = _api.status_item()
    assert item["state"] == "warn" and "vivos: zai" in item["detail"] and "foursquare exhausted" in item["detail"]
    assert "BRAVE" not in item["detail"], "a missing key is not a failure on the panel"
    monkeypatch.setattr(_api, "_health_cache", {"at": 1.0, "rows": rows[1:]})
    assert _api.status_item()["state"] == "error"


def test_prime_cache_never_raises_and_fills_the_rows(monkeypatch):
    from search import health
    monkeypatch.setattr(_api, "_health_cache", {"at": 0.0, "rows": []})
    monkeypatch.setattr(health, "probe_all", lambda names=None, parallel=True: [{"provider": "ddg", "kind": "results",
                                                                                  "state": "live", "why": "", "paid": False,
                                                                                  "key": "", "ok": True, "latency_ms": 2}])
    _api.prime_cache()
    assert _api.cached_rows()[0]["provider"] == "ddg"
    monkeypatch.setattr(health, "probe_all", lambda names=None, parallel=True: (_ for _ in ()).throw(RuntimeError("x")))
    _api.prime_cache()


def test_the_server_mounts_the_line_and_primes_once():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert "_search_api.status_item()" in (root / "server" / "voice_status.py").read_text(encoding="utf-8")
    assert "_search_api.prime_cache" in (root / "server" / "boot_halves.py").read_text(encoding="utf-8")


def test_both_fact_doors_call_the_service():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    for f in ("nucleo/flash/post_stream_lanes.py", "nucleo/flash/probe_after.py"):
        src = (root / f).read_text(encoding="utf-8")
        assert 'route="inline_fact", proposal="web_search"' in src, f
        assert "to_thread(_ws.search" not in src, f"{f} still calls the chain beside the service"


def test_the_brief_carries_the_fields_he_asked_for_as_hard_criteria():
    brief = {"goal": "fontanero", "request": "el fontanero mejor valorado que pueda venir hoy", "hard": ["Madrid"],
             "breadth": {"min_candidates": 25}, "deliverable": {"n_final": 3}}
    out = research.to_criteria(brief)
    assert out["hard"] == ["Madrid", "rating / reviews", "availability (when)"]
    assert research.to_criteria({"goal": "x", "request": "fotos del Amalfi"}).get("hard") is None


def test_find_keeps_the_chain_dict_for_the_doors(monkeypatch):
    import search
    from search import web
    raw = {"query": "q", "answer": "a", "results": [], "source": "ddg", "ai": False}
    monkeypatch.setattr(web, "search", lambda q, k=5, mode="answer": raw)
    res = search.find("q", route="inline_fact")
    assert res.raw is raw and "raw" not in res.to_dict()
