"""A widget action's trace keeps what it carried (demo pass 30, V6, 2026-09-28).

The player reported `player_error` and the event kept only the action's name: not the code (101/150 = the owner
refuses embedding) nor which video. A correct fallback and a broken player looked the same from outside. The
event now carries a digest of the payload — scalars, clipped, and never a field whose name says secret.
"""
import asyncio

from widgets import server_api as S


def test_the_ui_action_event_carries_the_code_and_the_video(monkeypatch):
    seen = []
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: seen.append(k.get("extra") or {}))

    async def _fake_dispatch(wid, action, data):
        return {"ok": True}
    monkeypatch.setattr(S, "_dispatch", _fake_dispatch)
    asyncio.run(S.widget_action("youtube", {"action": "player_error",
                                            "payload": {"code": "150", "videoId": "abc123"}}))
    ev = [e for e in seen if e.get("action") == "player_error"][0]
    assert ev["payload"] == {"code": "150", "videoId": "abc123"}


def test_a_secret_field_never_reaches_the_trace():
    d = S._payload_digest({"api_key": "sk-live-x", "password": "p", "token": "t", "q": "starship",
                           "rows": [1, 2, 3], "long": "x" * 500})
    assert "api_key" not in d and "password" not in d and "token" not in d
    assert d["q"] == "starship" and d["rows"] == "[3]" and len(d["long"]) == 120
