"""The status panel's search line, the turn's fact door, and the brief's asked fields (V2-782 T2.2 / T5.3 / T4.3)."""
from __future__ import annotations

from nucleo.workers import brief as research
from search import api as _api


def test_the_status_line_says_who_is_live_and_who_is_not(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")          # the line is in the instance language
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
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")          # the line is in the instance language
    monkeypatch.setattr(_api, "_health_cache", {"at": 0.0, "rows": []})
    monkeypatch.setattr(health, "probe_all", lambda names=None, parallel=True: [{"provider": "ddg", "kind": "results",
                                                                                  "state": "live", "why": "", "paid": False,
                                                                                  "key": "", "ok": True, "latency_ms": 2}])
    _api.prime_cache()
    assert _api.cached_rows()[0]["provider"] == "ddg"
    monkeypatch.setattr(health, "probe_all", lambda names=None, parallel=True: (_ for _ in ()).throw(RuntimeError("x")))
    _api.prime_cache()


_LIVE_ROWS = [{"provider": "ddg", "kind": "results", "state": "live", "why": "", "paid": False, "key": "",
               "ok": True, "latency_ms": 3},
              {"provider": "tavily", "kind": "results", "state": "blocked", "why": "HTTP 403", "paid": True,
               "key": "TAVILY_API_KEY", "ok": False, "latency_ms": 2}]


def _panel_items() -> list[dict]:
    """The status panel's rows as `/api/status` builds them (the second half, where the search line lives)."""
    import asyncio
    from types import SimpleNamespace

    from server import voice_status
    items: list[dict] = []
    asyncio.run(voice_status.the_rest_and_the_light(
        SETTINGS=SimpleNamespace(stt_provider="whisper", tts_provider="kokoro"), brain="direct",
        has=lambda _k: False, health_state={}, items=items))
    return items


def test_the_status_panel_carries_the_services_line(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")          # another variant: the line in English
    monkeypatch.setattr(_api, "_health_cache", {"at": 1.0, "rows": _LIVE_ROWS})
    rows = [it for it in _panel_items() if it["key"] == "search"]
    assert len(rows) == 1, rows
    assert rows[0]["state"] == _api.status_item()["state"] and rows[0]["detail"] == _api.status_item()["detail"]
    assert "ddg" in rows[0]["detail"] and "tavily blocked" in rows[0]["detail"]


def test_the_disarm_a_panel_that_does_not_read_the_service_is_caught(monkeypatch):
    monkeypatch.setattr(_api, "_health_cache", {"at": 1.0, "rows": _LIVE_ROWS})
    monkeypatch.setattr(_api, "status_item", lambda: (_ for _ in ()).throw(RuntimeError("off")))
    row = next(it for it in _panel_items() if it["key"] == "search")
    assert "ddg" not in row["detail"], "with the service's line cut the panel says only that it has no probe"


def _boot_seams(monkeypatch) -> tuple[list, list]:
    """Run the boot's seam wiring on a loop that RECORDS what it schedules; return (scheduled, primed)."""
    import asyncio
    from types import SimpleNamespace

    from nucleo import memory_agent
    from nucleo.energy import meter
    from nucleo.llm import prewarm
    from observability import identity
    from search import browser, hooks
    from server.boot import surfaces
    for mod in (browser, meter, identity, memory_agent):
        monkeypatch.setattr(mod, "set_loop", lambda _loop: None)
    monkeypatch.setattr(hooks, "on_chain_failure", hooks.on_chain_failure)   # restored after the test
    monkeypatch.setattr(hooks, "emit", hooks.emit)

    async def _noop():
        return None
    monkeypatch.setattr(prewarm, "run", _noop)
    primed: list = []
    monkeypatch.setattr(_api, "prime_cache", lambda: primed.append(1))
    scheduled: list = []

    class _Loop(asyncio.SelectorEventLoop):
        def call_later(self, delay, cb, *args, **kw):
            scheduled.append((delay, cb))

    async def _boot():
        app = SimpleNamespace(state=SimpleNamespace())
        surfaces.prewarm_and_seams(app, lambda: "nucleo")
        for _delay, cb in list(scheduled):          # fire what was deferred, as the loop would after 45 s
            fut = cb()
            if fut is not None:
                await fut
        task = getattr(app.state, "prewarm_task", None)
        if task is not None:
            await task

    loop = _Loop()
    try:
        loop.run_until_complete(_boot())
    finally:
        loop.close()
    return scheduled, primed


def test_the_boot_primes_the_panels_probe_once_and_late(monkeypatch):
    scheduled, primed = _boot_seams(monkeypatch)
    assert [d for d, _ in scheduled] == [45.0], "one deferred probe, well after boot"
    assert primed == [1], "the deferred call is the service's prime_cache, once"


def test_the_disarm_a_boot_without_the_search_seams_primes_nothing(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "voice.health_state", None)   # the seam block fails to import → skipped
    monkeypatch.delattr("voice.health_state", raising=False)
    scheduled, primed = _boot_seams(monkeypatch)
    assert scheduled == [] and primed == [], "with the seams cut nothing is primed — the test above goes red"


def test_the_fact_door_asks_find_for_an_inline_fact(monkeypatch):
    """The turn's fact door is the service's `find(route="inline_fact")`, never the chain beside it."""
    import search
    from nucleo.acts import search as door
    from search.result import SearchResult
    asked = []
    monkeypatch.setattr(search, "find", lambda q, **kw: asked.append((q, kw)) or SearchResult(
        query=q, raw={"query": q, "answer": "x", "results": [], "source": "zai"}))
    out = door.fact({"text": "q?", "brief": None}, {"query": "q"}, emit=lambda *a, **k: None, channel="voice")
    assert asked and asked[0][0] == "q" and asked[0][1]["route"] == "inline_fact"
    assert out.fired and out.verdict == "met" and out.data["res"]["answer"] == "x"


def test_the_fact_door_returns_the_chain_dict_and_never_raises(monkeypatch):
    from nucleo.acts import search as door
    from search import web
    seen = []
    monkeypatch.setattr(web, "search", lambda q, k=5, mode="answer": {"query": q, "answer": "x", "results": [], "source": "zai"})
    res = door.fact({}, {"query": "q"}, emit=lambda *a, **k: seen.append(a), channel="probe").data["res"]
    assert res["answer"] == "x" and res["source"] == "zai" and any(a[1].startswith("🧭") for a in seen)
    monkeypatch.setattr(web, "search", lambda q, k=5, mode="answer": (_ for _ in ()).throw(RuntimeError("boom")))
    out = door.fact({}, {"query": "q"}, emit=lambda *a, **k: None, channel="probe")
    assert out.data["res"]["results"] == [] and out.data["res"]["failure"]["kind"] in ("error",)
    assert out.verdict == "unmet"


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
