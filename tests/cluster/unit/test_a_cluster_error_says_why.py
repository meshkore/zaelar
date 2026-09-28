"""A cluster's «error» status says why (demo pass 30, 2026-09-28).

The trace showed «meshcore: error» with an empty text. The client knew the reason and the detail (it journals
them), and the bridge dropped both when it re-emitted the status. An error nobody can read is not observability.
"""
import asyncio

from connectors.meshkore import bridge as B


class _Mgr:
    def get(self, cluster): return None
    def clusters(self): return []
    def names(self): return []
    def has(self, n): return False


def test_the_status_event_carries_the_reason_and_the_detail(monkeypatch):
    seen = []
    monkeypatch.setattr(B, "_emit", lambda *a, **k: seen.append((a, k)))
    monkeypatch.setattr(B.journal, "record", lambda ev: None)

    async def _brain(text, on_chunk=None, **kw):
        return ""
    br = B.ClusterBridge(_Mgr(), _brain)
    br._notify_registry = lambda: None
    asyncio.run(br.on_event({"type": "status", "cluster": "meshcore", "status": "error",
                             "reason": "handshake", "detail": "HTTP 502 from the relay"}))
    args, kw = [s for s in seen if s[0][0] == "cluster"][0]
    assert "502" in kw.get("text", ""), kw
    assert kw["extra"]["reason"] == "handshake"
