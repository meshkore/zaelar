"""The video widget OWNS its library: channels, history, preferences and saved lists (V2-604).

Operator's direction (2026-09-06), which is the whole point of this file: «it is more important to me that
the video widget is responsible for storing the data. We don't want external dependencies. We want to manage
the subscription list that we like, the video list that we like, the history, the preferences, the filters.
Our core, our engine, our memory, our widget are the ones who have control.»

So every test here runs with the account connector ABSENT — which is also its real state today (V2-603 F2
deactivated it until an OAuth client exists). Nothing in the library may need it, ask it anything, or degrade
without it. The connector, when INI-032 finally opens its door, only EXTENDS this.

Two facts this file pins that are easy to get wrong later:

  * The history is ours BECAUSE WE PLAY THE VIDEO. It is not a copy of anything: YouTube's own API has
    returned an empty watch history for every account since 2016 (INI-032 §6), so this is the one video fact
    a connector could never hand us. It is recorded at the two moments a video really starts, and nowhere else.
  * A "minimum 720p" rule can only be checked when the PLAYER has the video. The results page does not
    publish definition (measured 2026-09-07: of ~20 hits only 4K carries a badge at all), so the rule WARNS
    on the video he asked for and never silently skips it — an explicit order outranks a standing filter,
    the same line `block_channel` already draws for a pasted link.
"""
import io
import urllib.request

import pytest

from widgets import store
from widgets.youtube import data as yt
from widgets.youtube import library

# Two hits from the same channel plus one from another, so `channel_videos` has something to filter.
_HTML = (
    '{"videoRenderer":{"videoId":"KKKKKKKKKK1",'
    '"title":{"runs":[{"text":"Por qué el cielo es azul"}]},'
    '"ownerText":{"runs":[{"text":"Kurzgesagt"}]},'
    '"publishedTimeText":{"simpleText":"hace 2 dias"}}}'
    '{"videoRenderer":{"videoId":"ZZZZZZZZZZ2",'
    '"title":{"runs":[{"text":"Otra cosa cualquiera"}]},'
    '"ownerText":{"runs":[{"text":"Canal Ajeno"}]}}}'
    '{"videoRenderer":{"videoId":"KKKKKKKKKK3",'
    '"title":{"runs":[{"text":"El origen de la Luna"}]},'
    '"ownerText":{"runs":[{"text":"Kurzgesagt"}]}}}'
)


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """An isolated store and a stubbed network. No connector is patched in ON PURPOSE: absent is the state
    this library is designed for, and a test that quietly provided one would prove nothing."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(_HTML.encode("utf-8")))


# ── the library exists without any account ────────────────────────────────────────────────────────────────

def test_the_connector_is_absent_and_the_library_still_answers(sandbox, monkeypatch):
    monkeypatch.setattr(yt, "_svc", lambda: None)        # harder than today's reality: no connector at all
    assert yt.view_data()["accounts_enabled"] is False
    assert yt.apply_action("follow_channel", {"channel": "Kurzgesagt"})["ok"]
    assert yt.apply_action("set_preference", {"key": "calidad mínima", "value": "720p"})["ok"]
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Cielo azul"})
    assert yt.apply_action("show_history")["ok"]
    d = yt.view_data()
    assert [c["name"] for c in d["channels"]] == ["Kurzgesagt"]
    assert d["prefs"]["min_definition"] == 720
    assert len(d["history"]) == 1


def test_the_library_fields_survive_a_reload_of_the_store(sandbox):
    yt.apply_action("follow_channel", {"channel": "Kurzgesagt"})
    yt.apply_action("set_preference", {"key": "volumen", "value": "40"})
    yt.apply_action("add", {"url": "https://youtu.be/ZZZZZZZZZZ2", "title": "En cola"})
    yt.apply_action("save_list", {"name": "la de la tarde"})
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Cielo azul"})
    fresh = yt._load()                                   # straight off disk, not the in-memory dict
    assert [c["name"] for c in fresh["channels"]] == ["Kurzgesagt"]
    assert fresh["prefs"] == {"volume": 40}
    assert [L["name"] for L in fresh["lists"]] == ["la de la tarde"]
    assert fresh["history"][0]["videoId"] == "KKKKKKKKKK1"


# ── history: ours because we are the ones playing ─────────────────────────────────────────────────────────

def test_playing_a_video_records_it_and_replaying_moves_the_row_instead_of_duplicating_it(sandbox):
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Cielo azul"})
    yt.apply_action("load", {"url": "https://youtu.be/ZZZZZZZZZZ2", "title": "Otra cosa"})
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Cielo azul"})
    hist = yt.view_data()["history"]
    assert [h["videoId"] for h in hist] == ["KKKKKKKKKK1", "ZZZZZZZZZZ2"]    # distinct videos, newest first
    assert hist[0]["plays"] == 2                                             # watched twice, one row


def test_the_list_driving_playback_is_recorded_too(sandbox):
    yt.apply_action("add", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    yt.apply_action("add", {"url": "https://youtu.be/ZZZZZZZZZZ2", "title": "Dos"})
    yt.apply_action("play")                              # starts the queue
    yt.apply_action("next")
    assert [h["videoId"] for h in yt.view_data()["history"]] == ["ZZZZZZZZZZ2", "KKKKKKKKKK1"]


def test_adding_and_searching_do_not_pretend_they_were_watched(sandbox):
    """`add` and `search` never start playback (V2-366), so they never enter the history. A history that
    filled up with things he only queued would answer «what have I watched» with things he has not."""
    yt.apply_action("add", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    yt.apply_action("search", {"query": "cualquier cosa"})
    assert yt.view_data()["history"] == []


def test_history_answers_from_his_own_past_not_from_the_network(sandbox, monkeypatch):
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Receta de cocido"})
    yt.apply_action("load", {"url": "https://youtu.be/ZZZZZZZZZZ2", "title": "Historia de Roma"})

    def _boom(*a, **k):                                  # searching his history must not touch the network
        raise AssertionError("el historial se contesta con lo nuestro, no buscando fuera")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    r = yt.apply_action("show_history", {"query": "cocido"})
    assert r["ok"] and r["count"] == 1 and r["total"] == 2
    assert [it["title"] for it in yt.view_data()["list"]] == ["Receta de cocido"]
    assert yt.apply_action("show_history", {"query": "submarinismo"})["error"] == "no_match"


def test_an_empty_history_says_so_instead_of_showing_an_empty_list(sandbox):
    r = yt.apply_action("show_history")
    assert r["ok"] is False and r["error"] == "no_history"
    assert yt.view_data()["list"] == []                  # and it did not blank a list he had


def test_clearing_the_history_leaves_the_rest_of_the_library_alone(sandbox):
    yt.apply_action("follow_channel", {"channel": "Kurzgesagt"})
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    assert yt.apply_action("clear_history")["cleared"] == 1
    d = yt.view_data()
    assert d["history"] == [] and [c["name"] for c in d["channels"]] == ["Kurzgesagt"]


# ── channels: our subscription list, and the contradiction with blocking ──────────────────────────────────

def test_following_a_channel_he_had_blocked_undoes_the_block_and_says_so(sandbox):
    """Both standing at once would make his own searches drop the channel he just said he wants — and a
    filter that vanishes in silence is one he cannot trust. The newer sentence wins, out loud."""
    yt.apply_action("block_channel", {"channel": "Kurzgesagt"})
    r = yt.apply_action("follow_channel", {"channel": "Kurzgesagt"})
    assert r["ok"] and r["unblocked"] == ["Kurzgesagt"]
    assert yt.view_data()["blocked_channels"] == []


def test_following_twice_is_not_two_rows_and_unfollowing_something_absent_says_so(sandbox):
    yt.apply_action("follow_channel", {"channel": "Kurzgesagt"})
    assert yt.apply_action("follow_channel", {"channel": "Kurzgesagt"})["already"] is True
    assert len(yt.view_data()["channels"]) == 1
    r = yt.apply_action("unfollow_channel", {"channel": "Canal Que No Sigo"})
    assert r["ok"] is False and r["error"] == "not_followed"


def test_a_followed_channels_videos_land_in_the_list_and_other_channels_do_not(sandbox):
    yt.apply_action("follow_channel", {"channel": "Kurzgesagt"})
    r = yt.apply_action("channel_videos", {})            # one followed channel: he need not name it
    assert r["ok"] and r["channel"] == "Kurzgesagt"
    assert [it["videoId"] for it in yt.view_data()["list"]] == ["KKKKKKKKKK1", "KKKKKKKKKK3"]


def test_channel_videos_still_honours_a_blocked_channel(sandbox):
    """Every NAME-search door honours the filter (V2-596). A new door that forgot it would be a hole in a
    rule the operator educated by voice, and it would open in silence."""
    yt.apply_action("block_channel", {"channel": "Kurzgesagt"})
    r = yt.apply_action("channel_videos", {"channel": "Kurzgesagt"})
    assert r["ok"] is False and r["error"] == "no_video"
    assert yt.view_data()["list"] == []


# ── preferences: enforced, or honestly labelled as a note ─────────────────────────────────────────────────

def test_a_preference_is_understood_in_his_own_words_accents_included(sandbox):
    """He says «calidad mínima» and «sí», not `min_definition` and `si`. A vocabulary that only knows its
    own identifiers turns every real sentence into an unknown preference."""
    assert yt.apply_action("set_preference", {"key": "calidad mínima", "value": "720p"})["key"] == "min_definition"
    r = yt.apply_action("set_preference", {"key": "subtítulos", "value": "sí"})
    assert r["ok"] and r["key"] == "captions" and r["value"] is True


def test_a_preference_we_cannot_enforce_is_stored_as_a_note_and_says_so(sandbox):
    """The failure this module is built against: storing an unenforceable rule as though it were enforced
    is a true sentence about the wrong mechanism (V2-603)."""
    r = yt.apply_action("set_preference", {"key": "nada de vídeos de más de una hora"})
    assert r["ok"] and r["stored_as"] == "note"
    assert "no puedo forzarlo" in r["message"]
    assert r["enforceable"] == ["captions", "min_definition", "volume"]
    assert yt.view_data()["prefs"] == {}                 # NOT stored as a rule
    assert yt.view_data()["prefs_notes"][0]["text"] == "nada de vídeos de más de una hora"


def test_a_quality_the_player_cannot_report_is_refused_instead_of_stored(sandbox):
    r = yt.apply_action("set_preference", {"key": "min_definition", "value": "700"})
    assert r["ok"] is False and "720" in r["message"]
    assert yt.view_data()["prefs"] == {}


def test_the_captions_preference_is_applied_to_every_video_that_starts(sandbox):
    yt.apply_action("set_preference", {"key": "subtítulos", "value": "sí"})
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    assert yt.view_data()["captions"] is True
    yt.apply_action("captions_off")                      # he overrides it for this one
    yt.apply_action("load", {"url": "https://youtu.be/ZZZZZZZZZZ2", "title": "Dos"})
    assert yt.view_data()["captions"] is True            # the standing preference returns on the next video


def test_the_volume_preference_does_not_undo_his_last_explicit_order(sandbox):
    """A preference that re-imposes itself on every item fights him: he turns one video down and the next
    shouts again. It sets the volume playback STARTS at, not the volume he is allowed to have."""
    yt.apply_action("set_preference", {"key": "volumen", "value": "80"})
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    assert yt.view_data()["volume"] == 80
    yt.apply_action("set_volume", {"level": 20})
    yt.apply_action("load", {"url": "https://youtu.be/ZZZZZZZZZZ2", "title": "Dos"})
    assert yt.view_data()["volume"] == 20                # still where he left it


def test_clearing_reaches_both_a_rule_and_a_note(sandbox):
    yt.apply_action("set_preference", {"key": "calidad", "value": 1080})
    yt.apply_action("set_preference", {"key": "nada de vídeos largos"})
    assert yt.apply_action("clear_preference", {"key": "calidad"})["ok"]
    assert yt.view_data()["prefs"] == {}
    assert yt.apply_action("clear_preference", {"key": "vídeos largos"})["ok"]
    assert yt.view_data()["prefs_notes"] == []
    assert yt.apply_action("clear_preference", {"key": "cualquier cosa"})["error"] == "not_set"


# ── the minimum-definition rule: measured at the player, warns, never skips ────────────────────────────────

def test_the_minimum_definition_warns_about_the_video_he_asked_for_and_keeps_playing_it(sandbox):
    yt.apply_action("set_preference", {"key": "calidad mínima", "value": 1080})
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    r = yt.apply_action("player_quality", {"levels": ["medium", "large", "hd720"], "videoId": "KKKKKKKKKK1"})
    assert r["known"] is True and r["quality"] == 720 and r["below_min"] is True
    assert "720p" in r["message"] and "1080p" in r["message"]
    d = yt.view_data()
    assert d["videoId"] == "KKKKKKKKKK1" and d["paused"] is False    # warned, never skipped
    assert d["history"][0]["quality"] == 720                          # and remembered for next time


def test_a_video_that_meets_the_minimum_says_nothing(sandbox):
    yt.apply_action("set_preference", {"key": "calidad mínima", "value": 720})
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    r = yt.apply_action("player_quality", {"levels": ["hd720", "hd1080"], "videoId": "KKKKKKKKKK1"})
    assert r["known"] is True and r["quality"] == 1080 and "below_min" not in r


def test_a_player_that_tells_us_nothing_never_produces_a_verdict(sandbox):
    """`auto`/`default` carry no information. Guessing from them would invent a complaint about a video
    that may be perfectly fine — the honest answer is that we do not know."""
    yt.apply_action("set_preference", {"key": "calidad mínima", "value": 1080})
    yt.apply_action("load", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    r = yt.apply_action("player_quality", {"levels": ["auto", "default"], "videoId": "KKKKKKKKKK1"})
    assert r["ok"] and r["known"] is False and "below_min" not in r and "message" not in r
    assert yt.view_data()["quality"] == 0


def test_the_quality_rule_is_read_from_the_player_and_never_from_a_search(sandbox):
    """Pins the reason `player_quality` exists at all. If a later change tries to decide definition from
    search results, this fails: the results page simply does not carry it."""
    hits = yt._search_many("lo que sea", 3)
    assert hits and all("quality" not in h and "definition" not in h for h in hits)
    assert library.best_quality([h.get("quality") for h in hits]) == 0


# ── saved lists ───────────────────────────────────────────────────────────────────────────────────────────

def test_a_list_is_saved_recovered_and_deleted_by_the_name_he_gave_it(sandbox):
    yt.apply_action("add", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    yt.apply_action("add", {"url": "https://youtu.be/ZZZZZZZZZZ2", "title": "Dos"})
    assert yt.apply_action("save_list", {"name": "la de la tarde"})["count"] == 2
    yt.apply_action("clear_list")
    r = yt.apply_action("open_list", {"name": "tarde"})   # he says a fragment, as people do
    assert r["ok"] and r["count"] == 2 and r["name"] == "la de la tarde"
    assert [it["title"] for it in yt.view_data()["list"]] == ["Uno", "Dos"]
    assert yt.apply_action("delete_list", {"name": "la de la tarde"})["lists"] == []


def test_opening_a_saved_list_does_not_start_playing(sandbox):
    """The rule every queue door in this widget follows (V2-366): only an explicit play starts a video."""
    yt.apply_action("add", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    yt.apply_action("save_list", {"name": "tarde"})
    yt.apply_action("clear_list")
    yt.apply_action("open_list", {"name": "tarde"})
    d = yt.view_data()
    assert d["videoId"] == "" and d["pos"] == -1 and d["history"] == []


def test_saving_over_a_name_replaces_it_instead_of_growing_two_with_the_same_name(sandbox):
    yt.apply_action("add", {"url": "https://youtu.be/KKKKKKKKKK1", "title": "Uno"})
    yt.apply_action("save_list", {"name": "tarde"})
    yt.apply_action("add", {"url": "https://youtu.be/ZZZZZZZZZZ2", "title": "Dos"})
    r = yt.apply_action("save_list", {"name": "tarde"})
    assert r["replaced"] is True and r["lists"] == ["tarde"]
    assert yt.apply_action("open_list", {"name": "tarde"})["count"] == 2


def test_saving_and_opening_nothing_say_what_is_missing(sandbox):
    assert yt.apply_action("save_list", {"name": "tarde"})["error"] == "empty_list"
    r = yt.apply_action("open_list", {"name": "tarde"})
    assert r["error"] == "no_list" and "Todavía no has guardado" in r["message"]


# ── the brain can SEE all of it ───────────────────────────────────────────────────────────────────────────

def test_every_library_action_is_declared_so_the_model_cannot_narrate_it_instead(sandbox):
    """An undeclared capability is one the model NARRATES rather than uses (V2-540), and the gate that
    normally catches this only reads data.py — the library lives in a sibling module."""
    import json
    import pathlib
    man = json.loads((pathlib.Path(yt.__file__).parent / "manifest.json").read_text(encoding="utf-8"))
    for name in ("show_history", "clear_history", "follow_channel", "unfollow_channel", "channel_videos",
                 "save_list", "open_list", "delete_list", "set_preference", "clear_preference",
                 "player_quality"):
        assert name in man["actions"], f"{name} no está declarada: el modelo no puede usar lo que no ve"
        assert yt.apply_action(name, {}) .get("error") != "unknown_action"


def test_the_routing_line_names_the_library_and_survives_the_prompt_trim(sandbox):
    """V2-547: `whenToUse` is cut at 300 chars, and the first draft of a routing line routinely loses the
    clause that routes the new intent. Checked against what the model actually reads."""
    import json
    import pathlib
    from widgets import brief
    man = json.loads((pathlib.Path(yt.__file__).parent / "manifest.json").read_text(encoding="utf-8"))
    seen = brief._purpose(man["whenToUse"])
    for word in ("HISTORIAL", "CANALES", "LISTAS", "PREFERENCIAS"):
        assert word in seen, f"«{word}» no sobrevive al recorte de la línea de enrutado"


def test_the_action_gate_follows_the_delegate_instead_of_forcing_a_god_file(sandbox):
    """V2-025's gate reads `apply_action` statically and rejects any declared action it cannot find a branch
    for. Until V2-604 it read data.py ONLY, so the two rules of this repo pulled in opposite directions: the
    architecture ratchet pays a growing file by EXTRACTING a module, and the gate would then call every
    extracted action a dead manifest entry — leaving "keep the whole dispatch in one god file" as the only
    green option. It now follows one level of delegation, and it still fails closed on real drift."""
    import json
    import pathlib
    from widgets import validator
    wdir = str(pathlib.Path(yt.__file__).parent)
    src = (pathlib.Path(wdir) / "data.py").read_text(encoding="utf-8")
    man = json.loads((pathlib.Path(wdir) / "manifest.json").read_text(encoding="utf-8"))

    handled = validator._apply_action_names(src, wdir)
    assert {"show_history", "set_preference", "player_quality", "open_list"} <= handled
    assert validator._validate_actions_sync(man, src, wdir) is None

    # Still closed in both directions: a declared action nothing handles, and a handled one left undeclared.
    ghost = dict(man, actions=dict(man["actions"], invented_action={"desc": "x", "payload": {}}))
    assert "invented_action" in (validator._validate_actions_sync(ghost, src, wdir) or "")
    silent = dict(man, actions={k: v for k, v in man["actions"].items() if k != "show_history"})
    assert "show_history" in (validator._validate_actions_sync(silent, src, wdir) or "")
