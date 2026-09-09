"""V2-634 — an unplayable video is a FACT to act on, never a screen to leave the operator with.

Measured live (session b828c901, 2026-09-09): «ponme un vídeo de Ronaldinho» resolved to a LaLiga-blocked
video; the embedded player refused it (onError, one second after the load — the report ARRIVED and nothing
consumed it), and the operator sat in front of «Video unavailable · Watch on YouTube». His rule, verbatim in
spirit: a video WE searched out ourselves gets silently replaced by the next playable candidate — «no dejes
al usuario con un vídeo prohibido que él no te ha pedido expresamente» — while a link HE pasted gets the
honest copyright message instead, because swapping what he explicitly asked for would be a different lie.
Every refused video goes on a blocklist no later search or swap may offer again.
"""
import io
import urllib.request

import pytest

from widgets import store
from widgets.youtube import data as yt


def _page(*vids):
    """A minimal results page carrying the given (id, title) candidates, in order."""
    return "".join(
        '{"videoRenderer":{"videoId":"%s","title":{"runs":[{"text":"%s"}]},'
        '"ownerText":{"runs":[{"text":"Canal %s"}]}}}' % (v, t, v[-1]) for v, t in vids
    )


_A, _B, _C = "AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3"


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    def serve(html):
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda req, timeout=6: io.BytesIO(html.encode("utf-8")))
    serve(_page((_A, "Jugadas A"), (_B, "Jugadas B"), (_C, "Jugadas C")))
    return serve


def test_a_search_pick_that_cannot_play_is_swapped_for_the_next_result(sandbox):
    yt.apply_action("search", {"query": "ronaldinho jugadas"})
    yt.apply_action("play_result", {"item": 1})
    r = yt.apply_action("player_error", {"code": 150})
    db = yt.view_data()
    assert db["videoId"] == _B, "the next playable search result must take the dead one's place"
    assert db["player_error"] == "", "_swap_to starts the replacement on a clean slate"
    assert db["blocked_notice"]["kind"] == "swapped"
    assert "Jugadas A" in db["blocked_notice"]["from"] and "Jugadas B" in db["blocked_notice"]["to"]
    assert _A in {b["videoId"] for b in db["blocked_videos"]}
    assert r["ok"] is True


def test_an_explicitly_pasted_link_is_never_swapped_only_told(sandbox):
    yt.apply_action("load", {"videoId": _A, "title": "El que pegó él"})
    r = yt.apply_action("player_error", {"code": 101})
    db = yt.view_data()
    assert db["videoId"] == _A, "swapping what he explicitly handed over would be a different lie"
    assert db["blocked_notice"]["kind"] == "explicit"
    assert _A in {b["videoId"] for b in db["blocked_videos"]}
    assert r["ok"] is True


def test_a_blocklisted_video_never_comes_back_from_a_search(sandbox):
    yt.apply_action("search", {"query": "ronaldinho jugadas"})
    yt.apply_action("play_result", {"item": 1})
    yt.apply_action("player_error", {"code": 150})            # _A blocklisted
    out = yt.apply_action("search", {"query": "ronaldinho jugadas"})
    ids = [r["videoId"] for r in yt.view_data()["search_results"]]
    assert _A not in ids and out["ok"] is True
    assert set(ids) == {_B, _C}


def test_a_query_load_that_cannot_play_reresolves_the_same_intent(sandbox):
    """«pon el vídeo de X» (our _search_id pick) errors with no queue and no search band: the stored
    last_query is re-resolved with the blocklist applied — the INTENT survives, the dead video does not."""
    yt.apply_action("load", {"query": "ronaldinho jugadas"})
    assert yt.view_data()["videoId"] == _A and yt.view_data()["pick_explicit"] is False
    yt.apply_action("player_error", {"code": 150})
    db = yt.view_data()
    assert db["videoId"] == _B
    assert db["blocked_notice"]["kind"] == "swapped"


def test_queue_driven_playback_advances_to_the_next_playable_item(sandbox):
    yt.apply_action("add", {"videoId": _A, "title": "Cola A"})
    yt.apply_action("add", {"videoId": _B, "title": "Cola B"})
    yt.apply_action("play_item", {"item": 1})
    yt.apply_action("player_error", {"code": 100})
    db = yt.view_data()
    assert db["videoId"] == _B and db["blocked_notice"]["kind"] == "swapped"


def test_no_candidate_left_is_said_honestly_not_swapped_blindly(sandbox, monkeypatch):
    yt.apply_action("load", {"query": "ronaldinho jugadas"})
    monkeypatch.setattr(yt, "_search_many", lambda q, n=5: [])   # the world went empty
    yt.apply_action("player_error", {"code": 150})
    db = yt.view_data()
    assert db["videoId"] == _A, "nothing honest to offer: the player's own message stays, with our banner"
    assert db["blocked_notice"]["kind"] == "exhausted"


def test_a_garbage_or_nonfatal_code_only_records_it(sandbox):
    yt.apply_action("load", {"query": "ronaldinho jugadas"})
    yt.apply_action("player_error", {"code": "weird<junk>"})
    db = yt.view_data()
    assert db["videoId"] == _A and db["blocked_notice"] == {} and db["blocked_videos"] == []


def test_the_next_successful_load_clears_the_notice(sandbox):
    yt.apply_action("search", {"query": "ronaldinho jugadas"})
    yt.apply_action("play_result", {"item": 1})
    yt.apply_action("player_error", {"code": 150})
    assert yt.view_data()["blocked_notice"]["kind"] == "swapped"
    yt.apply_action("load", {"videoId": _C, "title": "Otro"})
    assert yt.view_data()["blocked_notice"] == {}


def test_a_swapped_in_video_that_also_fails_swaps_again(sandbox):
    """The blocklist grows until something plays: B dies after replacing A → C takes over."""
    yt.apply_action("search", {"query": "ronaldinho jugadas"})
    yt.apply_action("play_result", {"item": 1})
    yt.apply_action("player_error", {"code": 150})            # A → B
    yt.apply_action("player_error", {"code": 150})            # B → C
    db = yt.view_data()
    assert db["videoId"] == _C
    assert {b["videoId"] for b in db["blocked_videos"]} == {_A, _B}


def test_the_brain_is_told_what_happened(sandbox):
    yt.apply_action("search", {"query": "ronaldinho jugadas"})
    yt.apply_action("play_result", {"item": 1})
    yt.apply_action("player_error", {"code": 150})
    d = yt.prompt_digest()
    assert "AVISO DEL REPRODUCTOR" in d and "Jugadas A" in d and "Jugadas B" in d
    yt.apply_action("load", {"videoId": _A, "title": "El que pegó él"})   # explicit reload of the blocked one
    yt.apply_action("player_error", {"code": 101})
    d = yt.prompt_digest()
    assert "solo puede" in d and "NO lo recargues" in d


def test_a_late_report_for_a_replaced_video_never_blames_its_successor(sandbox):
    """The report names its video: after A→B, a straggling onError for A blocklists A (again, no-op) and
    leaves B untouched — attributing it to the CURRENT video would blocklist the innocent replacement."""
    yt.apply_action("search", {"query": "ronaldinho jugadas"})
    yt.apply_action("play_result", {"item": 1})
    yt.apply_action("player_error", {"code": 150, "videoId": _A})     # A → B
    r = yt.apply_action("player_error", {"code": 150, "videoId": _A})  # straggler for A
    db = yt.view_data()
    assert r.get("stale") is True
    assert db["videoId"] == _B and db["player_error"] == ""
    assert {b["videoId"] for b in db["blocked_videos"]} == {_A}
