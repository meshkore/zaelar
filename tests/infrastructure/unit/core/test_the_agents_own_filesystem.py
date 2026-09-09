"""The agent's own filesystem (V2-638): one tree every widget shares, a boundary nothing crosses, and a
download policy that only brings home what the page can actually play.

Three things are pinned here, in the order they can hurt:

1. **The boundary.** Every path reaching `paths.resolve()` is untrusted — a magnet payload, model output, an
   HTTP query string. Escaping the library root means reading the operator's disk, so absolutes, `..` and a
   symlink planted INSIDE the library all have to answer `None`.
2. **The format policy.** The operator's rule: by default only fetch what the browser can play, with an
   explicit `keep` escape for «I want the file itself» (his pendrive case). This also fixes a real defect
   shipped in V2-637, where `.mkv`/`.avi` were treated as playable video — no mainstream browser decodes
   either, so the torrent client could pick a file it was structurally unable to show.
3. **The layout is genesis + overrides**, like the style policy of V2-633: renaming a folder must not reset
   the other four, and a rename must not be able to relocate the library by carrying a separator.
"""
from __future__ import annotations

import pytest

from library import formats, index, paths


@pytest.fixture
def lib(monkeypatch, tmp_path):
    """A library rooted in a temp workspace, with the override + genesis caches cleared around each case."""
    from nucleo import workspace as ws
    monkeypatch.setattr(ws, "root", lambda: tmp_path)
    paths._ov_cache.update(path=None, mtime=None, data={})
    paths.ensure()
    yield tmp_path
    paths._ov_cache.update(path=None, mtime=None, data={})


# ── 1 · the boundary ────────────────────────────────────────────────────────────────────────────────────────

def test_a_plain_relative_path_resolves_inside_the_library(lib):
    (paths.dir_for("video") / "film.mp4").write_bytes(b"x")
    p = paths.resolve("video/film.mp4")
    assert p is not None and p.is_file()


def test_absolute_paths_and_dotdot_are_refused(lib):
    assert paths.resolve("/etc/passwd") is None
    assert paths.resolve("../../etc/passwd") is None
    assert paths.resolve("video/../../../etc/passwd") is None
    assert paths.resolve("~/secrets") is None
    assert paths.resolve("") is None


def test_a_symlink_inside_the_library_cannot_be_used_to_leave_it(lib, tmp_path):
    """The one a naive string-prefix check misses: the PATH is inside, the FILE is not."""
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("private")
    link = paths.dir_for("documents") / "escape.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    assert paths.resolve("documents/escape.txt") is None


def test_a_renamed_folder_cannot_relocate_the_library(lib):
    """A folder NAME is one segment. A rename carrying a separator would move the whole tree."""
    paths.set_overrides({"folders": {"video": "../../../tmp/evil"}})
    d = paths.dir_for("video")
    assert d.parent == paths.root()          # still directly under the root, whatever was asked for
    assert ".." not in str(d)


# ── 2 · the format policy (the operator's default, and its escape hatch) ────────────────────────────────────

def test_mkv_and_avi_are_video_but_not_playable():
    """The V2-637 defect: these were listed as playable. No mainstream browser decodes either."""
    for name in ("film.mkv", "film.avi"):
        assert formats.kind_of(name) == "video"
        assert formats.browser_playable(name) is False


def test_the_formats_a_browser_really_plays():
    for name in ("a.mp4", "a.webm", "a.m4v", "a.mp3", "a.m4a", "a.opus", "a.flac", "a.pdf", "a.png"):
        assert formats.browser_playable(name) is True, name


def test_the_default_refuses_an_unplayable_file_and_keep_allows_it():
    assert formats.allowed("film.mkv") is False
    assert formats.allowed("film.mkv", keep=True) is True    # the operator's explicit pendrive case
    assert formats.allowed("film.mp4") is True


def test_a_refusal_names_the_file_and_offers_the_way_round():
    msg = formats.refusal("The Film.mkv")
    assert "The Film.mkv" in msg and ".mkv" in msg and "guardar" in msg


def test_kind_sorts_a_file_onto_its_shelf():
    assert formats.kind_of("song.mp3") == "audio"
    assert formats.kind_of("paper.pdf") == "document"
    assert formats.kind_of("pic.png") == "image"
    assert formats.kind_of("archive.zip") == "other"


# ── 3 · the layout: genesis defaults, operator overrides, and filing ────────────────────────────────────────

def test_genesis_gives_every_shelf_a_folder(lib):
    f = paths.folders()
    assert set(f) == set(paths.KINDS)
    for k in paths.KINDS:
        assert paths.dir_for(k).is_dir()


def test_renaming_one_folder_leaves_the_others_alone(lib):
    before = paths.folders()
    paths.set_overrides({"folders": {"video": "peliculas"}})
    after = paths.folders()
    assert after["video"] == "peliculas"
    assert {k: v for k, v in after.items() if k != "video"} == {k: v for k, v in before.items() if k != "video"}


def test_the_policy_is_operator_overridable(lib):
    assert paths.browser_playable_only() is True          # genesis default
    paths.set_overrides({"browser_playable_only": False})
    assert paths.browser_playable_only() is False


def test_a_file_is_filed_onto_the_shelf_its_kind_belongs_to(lib):
    src = paths.downloads_dir() / "The Film.mp4"
    src.write_bytes(b"data")
    out = index.file_into_place(src)
    assert out["ok"]
    assert out["rel"].startswith(paths.folders()["video"] + "/")
    assert not src.exists()                                # moved out of the sandbox, not copied


def test_filing_never_overwrites_an_existing_file(lib):
    (paths.dir_for("video") / "The Film.mp4").write_bytes(b"original")
    src = paths.downloads_dir() / "The Film.mp4"
    src.write_bytes(b"new")
    out = index.file_into_place(src)
    assert out["ok"] and "(1)" in out["rel"]
    assert (paths.dir_for("video") / "The Film.mp4").read_bytes() == b"original"


def test_the_record_a_widget_consumes_carries_url_and_playability(lib):
    (paths.dir_for("video") / "film.mp4").write_bytes(b"x" * 10)
    rec = index.entry_for("video/film.mp4")
    assert rec["kind"] == "video" and rec["playable"] is True
    assert rec["url"].startswith("/api/library/stream?path=")
    assert rec["mime"] == "video/mp4"


def test_an_unplayable_file_is_listed_with_a_download_url_and_no_stream_url(lib):
    (paths.dir_for("video") / "film.mkv").write_bytes(b"x")
    rec = index.entry_for("video/film.mkv")
    assert rec["playable"] is False
    assert rec["url"] == ""                                # never mount a <video> over it
    assert rec["download_url"]                             # but it is still reachable — the pendrive case


def test_listing_filters_by_shelf_and_skips_partial_files(lib):
    (paths.dir_for("video") / "a.mp4").write_bytes(b"x")
    (paths.dir_for("audio") / "b.mp3").write_bytes(b"x")
    (paths.downloads_dir() / "half.mp4.part").write_bytes(b"x")
    names = {r["name"] for r in index.listing()}
    assert names == {"a.mp4", "b.mp3"}                     # a half-written piece file is not a library item
    assert {r["name"] for r in index.listing("audio")} == {"b.mp3"}


# ── 4 · the connector switch: declared defaults are the defaults ────────────────────────────────────────────

def test_a_connector_declared_enabled_is_enabled_before_anyone_writes_the_store(monkeypatch, tmp_path):
    """The bug this fixes: `enabled()` consulted the store and an env var but never `_DEFAULTS`, so a
    connector shipped ON answered False on every install where nobody had written the store — i.e. every
    fresh one. It hid because all four pre-existing connectors default to False."""
    from config import connectors as cfg
    monkeypatch.setattr(cfg, "_PATH", tmp_path / "connectors.json")
    assert cfg.enabled("torrent") is True        # declared {"enabled": True}
    assert cfg.enabled("whatsapp") is False      # declared False — unchanged
    assert cfg.enabled("nonexistent") is False


def test_the_operator_can_switch_the_download_client_off(monkeypatch, tmp_path):
    from config import connectors as cfg
    from connectors.torrent import service
    monkeypatch.setattr(cfg, "_PATH", tmp_path / "connectors.json")
    monkeypatch.setattr(service.session, "available", lambda: True)
    assert service.available() is True
    cfg.set("torrent", {"enabled": False})
    assert service.available() is False
    assert "desactivado" in service.unavailable_reason()
    # and with it off, nothing reaches the network
    assert service.search_and_play("anything")["ok"] is False
