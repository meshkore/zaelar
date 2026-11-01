"""Every call to an outside provider says what happened — never an empty answer in silence (V2-833 F0).

Measured 2026-11-01 on a hosted engine: ten song lookups came back empty from the in-page player's resolver
(`except: return "", ""`) and no event said whether YouTube was unreachable, refused or simply had nothing — so «I
could not ask» reached the operator as «I could not find your song». One door, `connectors/outcome.py`, reports each
call (`provider · op · ok · reason · ms · status/bytes/hits`, kind `provider`, both surfaces) and re-raises, so every
caller keeps its own fallback.

The ratchet: a product function that makes a network call (urllib's `urlopen`, `httpx`, `requests`) and neither it
nor an enclosing function reports through the door is counted; the count may only fall, per file and in total.
"""
from __future__ import annotations

import ast
import subprocess
import urllib.error
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]

#: Measured 2026-11-01 when the door landed — the calls still outside it, per file. Lower a number when a call joins
#: the door (that edit is the point); never raise one. Most are the engine's OWN services (its local bridge, its LLM
#: and memory clients — they report through their own events) rather than third-party providers.
_MEASURED = {
    "config/balances.py": 2, "config/doctor.py": 1, "memory/embeddings/cloud.py": 1, "memory/embeddings/local.py": 1,
    "nucleo/cli/bridge.py": 2, "nucleo/cli/client.py": 1, "nucleo/cli/mem.py": 1, "nucleo/cli/nav.py": 1,
    "nucleo/cli/report.py": 1, "nucleo/cli/widget.py": 1, "nucleo/energy/egress.py": 1, "nucleo/flash/titular_watch.py": 1,
    "nucleo/memory_agent/processor/llm.py": 1, "nucleo/memory_agent/processor/llm_rungs.py": 1, "nucleo/pulse/offhost.py": 1,
    "search/health.py": 1, "server/livekit_api.py": 1, "voice/engine/pipeline/prewarm.py": 1, "voice/llm.py": 1,
}


def _net_call(n) -> bool:
    if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
        return False
    attr, base = n.func.attr, n.func.value
    if attr == "urlopen":
        return True
    return isinstance(base, ast.Name) and base.id in ("httpx", "requests") and attr in (
        "get", "post", "put", "delete", "patch", "request", "stream")


def _reports(fn) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("call", "report")
               and isinstance(n.func.value, ast.Name) and n.func.value.id == "_outcome" for n in ast.walk(fn))


def unreported(files: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for rel, src in files.items():
        tree = ast.parse(src)
        parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for call in (n for n in ast.walk(tree) if _net_call(n)):
            node, covered = call, False
            while node in parents:
                node = parents[node]
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _reports(node):
                    covered = True
                    break
            if not covered:
                out[rel] = out.get(rel, 0) + 1
    return out


def _product() -> dict[str, str]:
    names = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    return {n: (ENGINE / n).read_text(encoding="utf-8") for n in names
            if not n.startswith(("tests/", "scripts/")) and "/tests/" not in n and (ENGINE / n).exists()}


def test_a_provider_call_outside_the_door_only_gets_rarer():
    got = unreported(_product())
    grown = {f: n for f, n in got.items() if n > _MEASURED.get(f, 0)}
    assert not grown, f"a network call answers in silence where it did not before — report it through connectors/outcome: {grown}"
    assert sum(got.values()) <= sum(_MEASURED.values())


def test_the_guard_sees_an_unreported_call():
    bad = "import httpx\n\ndef f():\n    try:\n        return httpx.get('https://x')\n    except Exception:\n        return None\n"
    good = bad.replace("return httpx.get('https://x')", "return _outcome.call('x', 'get', lambda: httpx.get('https://x'))")
    assert unreported({"a.py": bad}) == {"a.py": 1} and unreported({"a.py": good}) == {}


# ── the door itself ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def events(monkeypatch):
    from voice import observer
    got: list = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: got.append((kind, (k.get("extra") or {}))))
    return got


def test_found_empty_refused_and_unreachable_are_told_apart(events):
    from connectors import outcome
    assert outcome.call("p", "op", lambda: b"x", empty=lambda b: not b) == b"x"
    outcome.call("p", "op", lambda: b"", empty=lambda b: not b)
    outcome.call("p", "op", lambda: type("R", (), {"status_code": 429})(), refused=lambda r: r.status_code >= 400,
                 measure=lambda r: {"status": r.status_code})

    def _down():
        raise urllib.error.HTTPError("https://x", 503, "down", {}, None)
    with pytest.raises(urllib.error.HTTPError):
        outcome.call("p", "op", _down)
    reasons = [(e["reason"], e.get("status")) for k, e in events if k == "provider"]
    assert reasons == [("found", None), ("empty", None), ("unreachable", 429), ("unreachable", 503)], reasons


@pytest.mark.parametrize("page,reason", [(b"<html>consent wall</html>", "empty"), (None, "unreachable")])
def test_the_song_lookup_says_why_it_came_back_empty(events, monkeypatch, page, reason):
    """The case that was invisible: the in-page player's resolver reports the page it got (bytes, hits) or the
    failure — while still answering «nothing» to its caller, whose chain goes on."""
    import urllib.request

    from connectors.music import youtube_resolve as yr

    class _Resp:
        def read(self):
            return page

    def _open(req, timeout=0):
        if page is None:
            raise TimeoutError("timed out")
        return _Resp()
    monkeypatch.setattr(urllib.request, "urlopen", _open)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    from search import browser
    monkeypatch.setattr(browser, "_loop", None)                          # no warm Chromium: the page is the only source
    assert yr._resolve("Shakira Bzrp Music Sessions 53")[:2] == ("", "")
    got = [e for k, e in events if k == "provider" and e["provider"] == "youtube"]
    assert got and got[0]["reason"] == reason, got
    if reason == "empty":
        assert got[0]["hits"] == 0 and got[0]["bytes"] == len(page)


def test_the_kind_is_classified_on_the_engine_side():
    from voice import observer
    assert observer._CAT.get("provider") == "system"
