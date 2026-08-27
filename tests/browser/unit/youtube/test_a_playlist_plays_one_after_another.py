#
# V2-366 — the youtube widget gains a PLAYLIST (operator: bring it to `musica`'s level).
# The queue model lives entirely in data.py (pure server code): `list` holds the videos, `pos` points at the
# item playing (or last played; -1 = the current video is not from the list), and `ended` — fired by the
# widget when the player reaches the end — advances by itself, one after another.
#
# The load-bearing decisions, each with its own test:
#   · `add` NEVER starts playback (YouTube's own "Add to queue"); that is also what keeps it usable with the
#     agent stopped — it is not a `produce` op in the manifest.
#   · `play` on an empty player with a non-empty list STARTS the list (the voice path that launches a queue).
#   · removing/closing never loses the list; `close` closes the VIDEO only.
#
import io
import json
import urllib.request

import pytest

from widgets import store
from widgets.youtube import data as yt

_VID1, _VID2, _VID3 = "AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"

_SEARCH_HTML = (
    '{"videoRenderer":{"videoId":"%s",'
    '"title":{"runs":[{"text":"Video buscado"}]},'
    '"longBylineText":{"runs":[{"text":"Canal X"}]},'
    '"publishedTimeText":{"simpleText":"hace 3 d\\u00edas"}}}' % _VID3
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    def _fake_urlopen(req, timeout=6):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "oembed" in url:
            return io.BytesIO(json.dumps({"title": "Oembed Title", "author_name": "Oembed Channel"}).encode())
        return io.BytesIO(_SEARCH_HTML.encode())

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    yield


def _add_two():
    yt.apply_action("add", {"url": "https://youtu.be/" + _VID1})
    yt.apply_action("add", {"url": "https://www.youtube.com/watch?v=" + _VID2})


def test_add_by_link_lands_in_the_list_and_never_autoplays():
    out = yt.apply_action("add", {"url": "https://youtu.be/" + _VID1})
    assert out["ok"] is True and out["position"] == 1
    db = yt._load()
    assert [it["videoId"] for it in db["list"]] == [_VID1]
    assert db["list"][0]["title"] == "Oembed Title"      # a pasted bare link still gets a readable row
    assert db["videoId"] == "" and db["paused"] is True  # nothing started playing


def test_add_with_the_network_down_still_lands_with_the_short_url(monkeypatch):
    def _dead(req, timeout=6):
        raise OSError("network down")
    monkeypatch.setattr(urllib.request, "urlopen", _dead)
    out = yt.apply_action("add", {"url": "https://youtu.be/" + _VID1})
    assert out["ok"] is True
    assert yt._load()["list"][0]["title"] == "youtu.be/" + _VID1


def test_add_by_name_searches_and_a_repeated_add_does_not_duplicate():
    out = yt.apply_action("add", {"query": "video buscado"})
    assert out["ok"] is True and yt._load()["list"][0]["videoId"] == _VID3
    again = yt.apply_action("add", {"url": "https://youtu.be/" + _VID3})
    assert again["ok"] is True and again.get("already_in_list") is True
    assert len(yt._load()["list"]) == 1


def test_play_on_an_empty_player_starts_the_list():
    _add_two()
    out = yt.apply_action("play", {})
    assert out["ok"] is True
    db = yt._load()
    assert db["videoId"] == _VID1 and db["pos"] == 0 and db["paused"] is False


def test_ended_advances_and_at_the_end_stops_honestly():
    _add_two()
    yt.apply_action("play_item", {"item": "1"})
    out = yt.apply_action("ended", {})
    assert out["ok"] is True
    db = yt._load()
    assert db["videoId"] == _VID2 and db["pos"] == 1 and db["paused"] is False
    out = yt.apply_action("ended", {})                    # end of the list: stop, do not loop
    db = yt._load()
    assert db["paused"] is True and db["videoId"] == _VID2


def test_a_video_loaded_outside_the_list_chains_into_it():
    _add_two()
    yt.apply_action("load", {"videoId": _VID3})           # direct load, not in the list → pos -1
    assert yt._load()["pos"] == -1
    yt.apply_action("ended", {})                          # after it ends, the queue starts
    assert yt._load()["videoId"] == _VID1


def test_next_and_previous_walk_the_list_and_the_edges_are_honest():
    _add_two()
    yt.apply_action("play_item", {"item": "1"})
    assert yt.apply_action("next", {})["ok"] is True
    assert yt._load()["videoId"] == _VID2
    out = yt.apply_action("next", {})                     # past the end
    assert out["ok"] is False and out["error"] == "end_of_list"
    assert yt.apply_action("previous", {})["ok"] is True
    assert yt._load()["videoId"] == _VID1
    out = yt.apply_action("previous", {})                 # at the start: back = restart, like YouTube
    assert out["ok"] is True and yt._load()["last_cmd"] == "restart"


def test_play_item_resolves_by_number_and_by_title_and_never_invents():
    _add_two()
    out = yt.apply_action("play_item", {"item": "2"})
    assert out["ok"] is True and yt._load()["videoId"] == _VID2
    out = yt.apply_action("play_item", {"item": "oembed title"})
    assert out["ok"] is True and yt._load()["videoId"] == _VID1
    out = yt.apply_action("play_item", {"item": "no existe"})
    assert out["ok"] is False and out["error"] == "item_not_found"


def test_load_of_a_video_already_in_the_list_syncs_pos():
    _add_two()
    yt.apply_action("load", {"videoId": _VID2})
    assert yt._load()["pos"] == 1                         # `next` would say end_of_list, not repeat B


def test_close_closes_the_video_and_the_list_survives():
    _add_two()
    yt.apply_action("play_item", {"item": "1"})
    yt.apply_action("close", {})
    db = yt._load()
    assert db["videoId"] == "" and db["pos"] == -1
    assert len(db["list"]) == 2                           # close closes the VIDEO; the list is the user's


# --- list management (V2-366, second wave): remove / move / sort / filter / clear ---

def _add_three():
    _add_two()
    yt.apply_action("add", {"url": "https://youtu.be/" + _VID3})


def test_removing_the_playing_item_keeps_the_thread_of_the_queue():
    _add_three()
    yt.apply_action("play_item", {"item": "2"})           # playing B
    out = yt.apply_action("remove", {"item": "2"})        # remove B while it plays
    assert out["ok"] is True
    db = yt._load()
    assert db["videoId"] == _VID2                         # playback untouched (like YouTube)
    yt.apply_action("ended", {})
    assert yt._load()["videoId"] == _VID3                 # `ended` plays what FOLLOWED the removed one


def test_removing_an_earlier_item_shifts_pos_with_the_list():
    _add_three()
    yt.apply_action("play_item", {"item": "2"})
    yt.apply_action("remove", {"item": "1"})
    db = yt._load()
    assert db["pos"] == 0 and db["list"][0]["videoId"] == _VID2
    out = yt.apply_action("next", {})
    assert out["ok"] is True and yt._load()["videoId"] == _VID3


def test_move_reorders_and_pos_follows_the_playing_item():
    _add_three()
    yt.apply_action("play_item", {"item": "1"})           # playing A
    out = yt.apply_action("move", {"item": "3", "to": 1})  # C to the front
    assert out["ok"] is True and out["position"] == 1
    db = yt._load()
    assert [it["videoId"] for it in db["list"]] == [_VID3, _VID1, _VID2]
    assert db["pos"] == 1                                  # still pointing at A
    yt.apply_action("ended", {})
    assert yt._load()["videoId"] == _VID2                  # next after A is B, wherever they moved


def test_sort_by_title_and_back_by_added():
    _add_three()                                           # titles: Oembed Title ×3 differ? no — same oembed
    db = yt._load()
    db["list"][0]["title"], db["list"][1]["title"], db["list"][2]["title"] = "zeta", "alfa", "media"
    store.save(yt.WID, db)
    assert yt.apply_action("sort_list", {"by": "title"})["ok"] is True
    assert [it["title"] for it in yt._load()["list"]] == ["alfa", "media", "zeta"]
    assert yt.apply_action("sort_list", {"by": "added"})["ok"] is True
    assert [it["videoId"] for it in yt._load()["list"]] == [_VID1, _VID2, _VID3]
    out = yt.apply_action("sort_list", {"by": "magic"})
    assert out["ok"] is False and out["error"] == "bad_sort"


def test_filter_is_display_only_and_clears_with_empty_q():
    _add_two()
    assert yt.apply_action("filter_list", {"q": "oembed"})["ok"] is True
    db = yt._load()
    assert db["list_filter"] == "oembed" and len(db["list"]) == 2   # the list itself never shrinks
    yt.apply_action("filter_list", {"q": ""})
    assert yt._load()["list_filter"] == ""


def test_clear_list_empties_the_list_but_never_cuts_the_video():
    _add_two()
    yt.apply_action("play_item", {"item": "1"})
    out = yt.apply_action("clear_list", {})
    assert out["ok"] is True
    db = yt._load()
    assert db["list"] == [] and db["pos"] == -1
    assert db["videoId"] == _VID1 and db["paused"] is False   # what plays keeps playing


def test_two_pasted_links_in_one_add_both_land_in_order():
    """Measured 2026-08-27 14:38 (`build-a-video-playlist-from-links`): the operator pasted TWO urls in one
    sentence, the model emitted ONE `add` — and only the first id landed. Every id in the text lands now."""
    out = yt.apply_action("add", {"url": "Te paso https://www.youtube.com/watch?v=" + _VID1
                                          + " y https://youtu.be/" + _VID2 + " — móntame una lista"})
    assert out["ok"] is True and out["count"] == 2 and out["positions"] == [1, 2]
    db = yt._load()
    assert [it["videoId"] for it in db["list"]] == [_VID1, _VID2]
    assert db["videoId"] == "" and db["paused"] is True   # still: add NEVER starts playback
    again = yt.apply_action("add", {"urls": ["https://youtu.be/" + _VID2, "https://youtu.be/" + _VID3]})
    assert again["ok"] is True and again["count"] == 3    # dedup inside the batch path too
