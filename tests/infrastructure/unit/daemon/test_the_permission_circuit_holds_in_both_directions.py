"""The daemon's permission circuit (V2-575 · P0) — the gate that decides what of the user's disk an agent sees.

TWO DIRECTIONS, and the second one is why this file is long. A permission test that only checks refusals passes
perfectly on a daemon that refuses everything, and a daemon that refuses everything looks — to the user — exactly
like a broken product with a good excuse. So every escape here has a sibling assertion that the legitimate thing
right next to it is still ALLOWED.

The sharpest case is the macOS one: `~/Documents` is frequently a symlink into `~/Library/Mobile Documents/…`
when iCloud Drive is on. A circuit that resolves the request but not the ROOT refuses the user their own
Documents folder — and it refuses it while every escape test still passes, so nothing would have caught it.
"""
import json
import os
import sys

import pytest


@pytest.fixture()
def daemon(tmp_path, monkeypatch):
    """A daemon whose whole world is a temp directory.

    `ZAELAR_WORKSPACE` alone is not isolation: `daemon.config` caches the file in memory on first read, and a
    module imported by an earlier test would serve the operator's real allowlist from that cache. Resetting it
    on both sides of the test is what makes the isolation real."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg
    dcfg.reset_cache()
    yield tmp_path
    dcfg.reset_cache()


@pytest.fixture()
def allowed(daemon, tmp_path):
    """One granted folder with a file in it, plus an ungranted sibling holding a secret."""
    from daemon import config as dcfg

    inside = tmp_path / "Papers"
    inside.mkdir()
    (inside / "invoice.txt").write_text("total 42 euros", encoding="utf-8")
    outside = tmp_path / "Private"
    outside.mkdir()
    (outside / "secret.txt").write_text("do not read me", encoding="utf-8")
    dcfg.save({"roots": [str(inside)], "configured": True})
    return inside, outside


# ── the direction everybody remembers: escapes are refused ────────────────────────────────────────────────

def test_a_dotdot_walk_out_of_an_allowed_folder_is_refused(allowed):
    from daemon import permissions
    inside, outside = allowed
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve(str(inside / ".." / "Private" / "secret.txt"))
    assert e.value.code == "outside_allowlist"


def test_a_symlink_that_leaves_the_allowed_folder_is_refused(allowed):
    """The one that a check-before-resolve implementation gets wrong: the link LIVES inside the granted folder,
    so every string comparison says it is fine right up until you follow it."""
    from daemon import permissions
    inside, outside = allowed
    link = inside / "shortcut.txt"
    link.symlink_to(outside / "secret.txt")
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve(str(link))
    assert e.value.code == "outside_allowlist"


def test_an_absolute_path_outside_every_root_is_refused(allowed):
    from daemon import permissions
    _inside, outside = allowed
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve(str(outside / "secret.txt"))
    assert e.value.code == "outside_allowlist"


def test_a_relative_path_is_refused_rather_than_joined_to_something(allowed):
    from daemon import permissions
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve("../../etc/passwd")
    assert e.value.code == "relative_path"


def test_a_credential_is_refused_even_inside_a_folder_the_user_granted(allowed):
    """"The user allowed their home directory" must never mean "the agent may read the SSH key"."""
    from daemon import permissions
    inside, _outside = allowed
    ssh = inside / ".ssh"
    ssh.mkdir()
    (ssh / "id_rsa").write_text("PRIVATE KEY", encoding="utf-8")
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve(str(ssh / "id_rsa"))
    assert e.value.code == "sensitive"

    (inside / "server.pem").write_text("cert", encoding="utf-8")
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve(str(inside / "server.pem"))
    assert e.value.code == "sensitive"


def test_the_daemons_own_state_directory_is_never_readable_through_it(daemon, tmp_path):
    """`daemon.json` holds the API token: whoever reads it can read every folder the user granted. Granting the
    workspace root is a plausible thing for a self-hoster to do, and it must not hand over the key."""
    from daemon import config as dcfg, permissions
    from daemon.paths import config_file
    dcfg.save({"roots": [str(tmp_path)], "configured": True})
    assert config_file().exists()
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve(str(config_file()))
    assert e.value.code == "protected"


def test_granting_a_credential_folder_is_refused_at_the_wizard_too(daemon, tmp_path):
    """The boundary has to hold at the point where folders are ADDED, or the user can hand the daemon `~/.ssh`
    through the picker and every later check will agree it is allowed."""
    from daemon import permissions
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    with pytest.raises(permissions.Refusal) as e:
        permissions.grant(str(ssh))
    assert e.value.code == "sensitive"
    assert permissions.roots() == []


def test_granting_the_whole_disk_is_refused(daemon):
    from daemon import permissions
    root = os.path.abspath(os.sep)
    with pytest.raises(permissions.Refusal) as e:
        permissions.grant(root)
    assert e.value.code == "too_broad"


# ── the direction that gets forgotten: legitimate access still works ──────────────────────────────────────

def test_a_file_inside_an_allowed_folder_is_allowed(allowed):
    from daemon import files
    inside, _ = allowed
    out = files.read_file(str(inside / "invoice.txt"))
    assert out["ok"] and "42 euros" in out["text"]


def test_a_root_that_is_itself_a_symlink_still_works(daemon, tmp_path):
    """The macOS iCloud case. `~/Documents` → `~/Library/Mobile Documents/…` is normal, not an attack, and a
    circuit that resolves only the request refuses the user their own files while every escape test above still
    passes. This is the assertion that catches it."""
    from daemon import config as dcfg, files

    real = tmp_path / "MobileDocuments"
    real.mkdir()
    (real / "note.txt").write_text("hello from iCloud", encoding="utf-8")
    link = tmp_path / "Documents"
    link.symlink_to(real, target_is_directory=True)

    dcfg.save({"roots": [str(link)], "configured": True})
    out = files.read_file(str(link / "note.txt"))
    assert "hello from iCloud" in out["text"]
    # And through the resolved name too — the agent may have been handed either form.
    assert "hello from iCloud" in files.read_file(str(real / "note.txt"))["text"]


def test_a_symlink_that_stays_inside_the_allowed_folder_is_allowed(allowed):
    """Not every link is an escape. Refusing all of them would be easy and would break a filesystem people
    actually organize with."""
    from daemon import files
    inside, _ = allowed
    (inside / "deep").mkdir()
    (inside / "deep" / "real.txt").write_text("still inside", encoding="utf-8")
    (inside / "alias.txt").symlink_to(inside / "deep" / "real.txt")
    assert "still inside" in files.read_file(str(inside / "alias.txt"))["text"]


def test_a_tilde_path_is_expanded_not_refused(daemon, tmp_path, monkeypatch):
    """Users — and models quoting users — write `~/Documents`. Refusing it as "not absolute" would be correct
    by the letter and useless in practice."""
    from daemon import config as dcfg, permissions
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    docs = tmp_path / "Docs"
    docs.mkdir()
    (docs / "a.txt").write_text("x", encoding="utf-8")
    dcfg.save({"roots": [str(docs)], "configured": True})
    assert permissions.resolve("~/Docs/a.txt") == (docs / "a.txt").resolve()


# ── refusals say what the boundary is (V2-421/V2-507) ─────────────────────────────────────────────────────

def test_a_refusal_names_the_folders_that_are_available(allowed):
    """A bare 403 makes the agent guess, and a guessing agent tells the user something invented. The refusal
    carries the allowlist so the engine can say something true."""
    from daemon import permissions
    inside, outside = allowed
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve(str(outside / "secret.txt"))
    assert str(inside) in e.value.message
    assert e.value.folders == [str(inside)]


def test_with_no_folders_granted_the_refusal_says_so_instead_of_saying_not_found(daemon):
    """"There is nothing there" and "you never let me look" are different sentences, and the second is the one
    that tells the user what to do."""
    from daemon import permissions
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve("/anywhere/at/all.txt")
    assert e.value.code == "no_folders"


# ── the limits are stated, not hidden (decision 7: on demand, no index) ───────────────────────────────────

def test_a_search_that_stops_early_says_that_it_stopped(allowed, monkeypatch):
    """A search that quietly gave up is indistinguishable from a search that found everything — and the agent
    would report the second."""
    from daemon import files
    inside, _ = allowed
    for i in range(12):
        (inside / f"report-{i}.txt").write_text("x", encoding="utf-8")
    out = files.search("report", raw_path=str(inside), limit=5)
    assert len(out["hits"]) == 5
    assert out["stopped_early"] == "limit"

    full = files.search("report", raw_path=str(inside), limit=100)
    assert full["stopped_early"] is None and len(full["hits"]) == 12


def test_a_truncated_read_says_it_was_truncated(allowed):
    from daemon import files
    inside, _ = allowed
    (inside / "long.txt").write_text("a" * 5000, encoding="utf-8")
    out = files.read_file(str(inside / "long.txt"), max_bytes=100)
    assert out["truncated"] is True and len(out["text"]) == 100
    assert files.read_file(str(inside / "long.txt"))["truncated"] is False


def test_search_prunes_a_subtree_it_would_refuse_anyway(allowed):
    """Not an optimization detail — it is what keeps a granted home directory from costing a minute per search,
    and it must not change the answer."""
    from daemon import files
    inside, _ = allowed
    ssh = inside / ".ssh"
    ssh.mkdir()
    (ssh / "known_hosts").write_text("secret-marker", encoding="utf-8")
    out = files.search("known_hosts", raw_path=str(inside), content=True)
    assert out["hits"] == []


def test_listing_shows_a_link_out_as_blocked_rather_than_hiding_it(allowed):
    """The user can see the alias in Finder. An agent that cannot must be able to say why, or the user concludes
    the file is missing."""
    from daemon import files
    inside, outside = allowed
    (inside / "escape").symlink_to(outside)
    kinds = {e["name"]: e["kind"] for e in files.list_dir(str(inside))["entries"]}
    assert kinds["escape"] == "blocked"
    assert kinds["invoice.txt"] == "file"


# ── writing does not exist in v1 (P5) ─────────────────────────────────────────────────────────────────────

def test_the_daemon_has_no_write_path_at_all(allowed):
    """The irreversible half is P5, behind its own confirmation. This asserts the ABSENCE, because a write that
    appears by accident would pass every test above — they all only ever read."""
    import inspect
    from daemon import files
    src = inspect.getsource(files)
    for forbidden in ("open(", "write_text", "unlink", "rmtree", "os.remove", "mkdir", "rename"):
        if forbidden == "open(":
            # `permissions.open_read` is the read path; the bare builtin must not appear with a write mode.
            assert '"w"' not in src and "'w'" not in src, "files.py opened something for writing"
            continue
        assert forbidden not in src, f"files.py contains {forbidden!r}: writing is P5, not v1"


# ── "Documents by default" means proposed, not already granted ────────────────────────────────────────────

def test_a_fresh_install_can_read_nothing_until_the_user_chooses(daemon):
    """The first version of this seeded `roots` with `~/Documents` on first run, which is the obvious reading of
    "Documents by default" and is wrong: installing the daemon would make every document on the machine
    readable before the user had been shown a single screen.

    This test is the boundary. `candidates()` still marks Documents as the suggested entry, so a user who clicks
    straight through the wizard gets the documented default — having seen it."""
    from daemon import config as dcfg, permissions
    cfg = dcfg.load()
    assert cfg["roots"] == []
    assert cfg["configured"] is False
    with pytest.raises(permissions.Refusal) as e:
        permissions.resolve(str(tmp := (daemon / "anything.txt")))
    assert e.value.code == "no_folders", tmp


def test_documents_is_the_entry_the_wizard_pre_checks(daemon, tmp_path, monkeypatch):
    from daemon import permissions
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    (home / "Downloads").mkdir()
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: home))
    suggested = {c["label"]: c["suggested"] for c in permissions.candidates()}
    assert suggested.get("Documents") is True
    assert suggested.get("Downloads") is False


# ── the config file is a credential file ──────────────────────────────────────────────────────────────────

@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes; Windows inherits the per-user ACL instead")
def test_daemon_json_is_not_readable_by_other_users(daemon):
    from daemon import config as dcfg
    from daemon.paths import config_file
    dcfg.save({"configured": True})
    mode = config_file().stat().st_mode & 0o777
    assert mode == 0o600, f"daemon.json is {oct(mode)}: it holds the API token"


def test_the_token_is_generated_once_and_survives_a_reload(daemon):
    from daemon import config as dcfg
    first = dcfg.token()
    assert len(first) >= 32
    dcfg.reset_cache()
    assert dcfg.token() == first


def test_a_corrupt_config_falls_back_to_defaults_instead_of_refusing_to_run(daemon):
    """A daemon that will not start because its config is torn is a daemon the user cannot fix, since the way
    to fix it is through the daemon."""
    from daemon import config as dcfg
    from daemon.paths import config_file
    dcfg.save({"configured": True})
    dcfg.reset_cache()
    config_file().write_text("{not json", encoding="utf-8")
    cfg = dcfg.load()
    assert cfg["port"] and cfg["token"]


def test_an_unknown_key_in_the_config_cannot_become_an_allowlist_entry(daemon):
    """Forward compatibility that widens permissions is not compatibility."""
    from daemon import config as dcfg
    from daemon.paths import config_file
    dcfg.load()
    config_file().write_text(json.dumps({"roots": [], "extra_roots": ["/"], "evil": True}), encoding="utf-8")
    dcfg.reset_cache()
    cfg = dcfg.load()
    assert cfg["roots"] == []
    assert "evil" not in cfg and "extra_roots" not in cfg
