"""Searching for videos is channelled to the PLAYER, never to the results sheet (V2-402).

Seen live by the operator (2026-08-27): "find me videos about X" ended in the generic results sheet. The cause
is architectural, not a bug in any one line: `play_video` owned exactly ONE video ("pon el vídeo de…"),
`play_music` owned playback — and a media SEARCH ("búscame vídeos de…", "qué documentales hay de…") had no
owner, so it fell through to `escalate_to_slowbrain`, whose `lista` surface IS the results sheet
(`nucleo/surfaces.py`: the closed vocabulary has no media destination). The operator's rule, now written into
the catalog: content you WATCH or LISTEN to is channelled through its dedicated widget — searching for it
included; the sheet is for INFORMATION, even when an informational result happens to contain videos.

The V2-380/383 lesson governs the shape: the play/list decision is normalized in ONE place (`video_turn`) and
both channels (voice provider and probe) consume it, because anything decided per-channel diverges per-channel.
"""
import asyncio
import json

import pytest

from nucleo.flash import router
from nucleo.flash import video_turn as VT


# ── ONE normalization for both channels ──────────────────────────────────────────────────────────────────────

def test_action_normalizes_to_play_or_list_and_nothing_else():
    for raw in ("list", "LIST", "search", "browse", "buscar", "varios", "lista"):
        assert VT.normalize_action(raw) == "list", raw
    for raw in ("", None, "play", "PLAY", "anything-else"):
        assert VT.normalize_action(raw) == "play", raw


def test_request_from_carries_the_action():
    req = VT.request_from([{"name": "play_video", "args": {"query": "vídeos de paella", "action": "search"}}])
    assert req == {"query": "vídeos de paella", "action": "list"}
    req = VT.request_from([{"name": "play_video", "args": {"query": "tráiler de Dune"}}])
    assert req["action"] == "play"


def test_router_decision_travels_with_the_normalized_action():
    d = router.decide("play_video", {"query": "vídeos de paella", "action": "browse"})
    assert d.payload["action"] == "list"
    assert router.decide("play_video", {"query": "x"}).payload["action"] == "play"


# ── the execution rail: list → the widget's `search` data-op ────────────────────────────────────────────────

@pytest.fixture
def rail(monkeypatch):
    seen = {}

    async def _brain_action(wid, action, payload):
        seen.update({"wid": wid, "action": action, "payload": payload})
        return seen.get("_res", {"ok": True, "added": ["Paella de marisco", "Paella valenciana",
                                                       "El secreto del socarrat"], "count": 3})
    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    return seen


def test_a_list_request_runs_the_search_dataop_not_load(rail):
    parte = asyncio.run(VT.execute("vídeos de paella", "list"))
    assert rail["wid"] == "youtube" and rail["action"] == "search"
    assert parte["ok"] and parte["accion"] == "list" and parte["count"] == 3
    assert parte["added"][0] == "Paella de marisco"


def test_a_play_request_still_loads_one_video(rail):
    rail["_res"] = {"ok": True, "videoId": "Way9Dexny3w", "title": "Dune: Part Two | Official Trailer"}
    parte = asyncio.run(VT.execute("tráiler de Dune", "play"))
    assert rail["action"] == "load", "the single-video contract must stay byte-identical"
    assert parte.get("accion") != "list"


def test_the_mouth_names_the_candidates_and_invites_a_choice(rail, monkeypatch):
    # V2-464: las frases siguen al MOTOR y el entorno de la suite resuelve inglés — se fija el castellano
    # porque este caso mide el CONTENIDO de la frase, no su idioma.
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es", raising=False)
    parte = asyncio.run(VT.execute("vídeos de paella", "list"))
    spoken = VT.spoken_for(parte, "Hecho.")
    assert "3" in spoken and "Paella de marisco" in spoken and "cuál" in spoken
    assert spoken != "Hecho.", "a search must never collapse into the canned ack"


def test_a_failed_search_is_said_not_acked(rail, monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es", raising=False)  # V2-464
    rail["_res"] = {"ok": False, "message": "No encontré vídeos de eso."}
    parte = asyncio.run(VT.execute("zzz", "list"))
    spoken = VT.spoken_for(parte, "Hecho.")
    assert "No he podido" in spoken and "Hecho." not in spoken


# ── the boundary is TOLD to the model (the catalog is where the routing decision lives) ─────────────────────

def _desc(name: str) -> str:
    t = next(t for t in router.TOOLS if t["function"]["name"] == name)
    return json.dumps(t, ensure_ascii=False)


def test_the_catalog_says_a_media_search_belongs_to_the_player():
    pv = _desc("play_video")
    assert "action=list" in pv and "hoja" in pv, "play_video must claim the SEARCH half and name the boundary"
    esc = _desc("escalate_to_slowbrain")
    assert "play_video/play_music" in esc and "BUSCAR" in esc, \
        "escalate's NO-list must send media searches to the player tools"
    pm = _desc("play_music")
    assert "PODCAST" in pm, "a podcast is audio content and play_music must say so"


def test_the_voice_channel_reaches_the_search_dataop():
    """Wiring witness for the voice provider (its elif chain has no unit seam). Rewritten with the architecture
    ratchet's toll: the branch body moved into `video_turn.voice_dispatch` (op + label decided ONCE for both
    channels), so the witness now checks (a) the shared helper's both faces, and (b) that the provider actually
    consumes it — which is what turns "the voice half was never wired" (the V2-380/383 family) from silent
    into red."""
    assert VT.voice_dispatch("search") == ("search", "🔎 vídeos → lista youtube")
    assert VT.voice_dispatch(None)[0] == "load"
    import inspect
    import voice.engine.llm.providers.nucleo as prov
    src = inspect.getsource(prov)
    assert "voice_dispatch" in src, "the voice provider must consume the ONE shared play/list decision"
    assert '_apply_widget_data("youtube", _vop' in src, "the decided op must reach the widget data rail"


# ── the WHOLE probe turn, where V2-383's family of defects lived (per-link guards stayed green there) ───────

class _ClientThatSearchesVideos:
    """Stub: the model asks to SEARCH videos, as in the operator's live session."""

    async def stream(self, *_a, on_tool_call=None, **_kw):
        if on_tool_call is not None:
            res = on_tool_call("play_video", {"query": "vídeos de recetas de paella", "action": "search"})
            if asyncio.iscoroutine(res):
                await res
        yield "Te los busco."


def test_a_probe_search_turn_reaches_the_widgets_search_dataop(monkeypatch, tmp_path):
    """From the model's call to the widget's `search`, nothing dropped in between — the exact link that
    swallowing `action` on the probe side would silently break (every search would quietly become a load)."""
    from memory import db as memdb
    from memory import embeddings as mememb
    from nucleo.flash import probe

    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset(); memdb.reset_db(); memdb.get_db()

    seen = {}

    async def _brain_action(wid, action, payload):
        seen.update({"wid": wid, "action": action, "payload": payload})
        return {"ok": True, "added": ["Paella de marisco", "Paella valenciana"], "count": 2}

    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _ClientThatSearchesVideos)
    try:
        res = asyncio.run(probe.run_turn("Búscame vídeos de recetas de paella.",
                                         sid="test-video-search-turn", ingest=False, execute=True))
    finally:
        probe._SESSIONS.pop("test-video-search-turn", None)
        memdb.reset_db(); mememb.reset()

    assert res["ok"] is True
    assert seen == {"wid": "youtube", "action": "search", "payload": {"query": "vídeos de recetas de paella"}}, \
        "the search must reach the player's list; landing anywhere else is the defect the operator saw"
