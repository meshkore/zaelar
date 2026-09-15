"""The daemon as a PRODUCT, not a process (V2-575 · P1).

The other daemon nodes prove the thing works. This one proves somebody can GET it and STEER it: the icon knows
whether it is there, the screen hands over the right installer for the right machine, and the folder grant is
a deliberate act by the person in front of the screen rather than something a page they visited can do for
them.

THE TWO FAILURE DIRECTIONS ARE BOTH HERE, and the second is the one that gets skipped. A proxy that refuses
every browser is trivially safe and completely useless — the legitimate caller of `/api/daemon/*` IS a browser,
ours. So each guard is checked with a hostile request AND with the ordinary one it must not break.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import daemon_api

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    """A self-host engine whose state directory is empty: nothing installed, nothing running. The state
    directory is redirected at `_state_dir` rather than through the environment so the test can never read —
    or create — the real one belonging to whoever is running the suite."""
    monkeypatch.setattr(daemon_api, "_state_dir", lambda: tmp_path / "config" / "daemon")
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: False)
    app = FastAPI()
    app.include_router(daemon_api.router)
    return TestClient(app)


# ── the screen can do its job before anything is installed ────────────────────────────────────────────────

def test_with_nothing_installed_the_screen_still_has_an_installer_to_offer(client):
    """The state the download surface exists FOR. An earlier shape returned the download block only once the
    engine had seen a daemon, which is exactly backwards: the person who needs the file is the one who has
    never had it."""
    body = client.get("/api/daemon/status").json()
    assert body["installed"] is False and body["reachable"] is False and body["state"] == "off"
    platforms = body["downloads"]["platforms"]
    assert {"macos", "windows"} <= set(platforms)
    for assets in platforms.values():
        assert assets["artifact"].startswith("https://") and assets["installer"].startswith("https://")


def test_asking_about_the_daemon_does_not_leave_a_credential_behind(client, tmp_path):
    """⚠️ `daemon.config.load()` MINTS A TOKEN and writes `daemon.json` on first call, and `paths.state_dir()`
    creates the directory. Reaching for either from the engine would mean that opening the status icon on a
    cloud Volume — where no daemon will ever run — silently creates a file whose whole purpose is to hold a
    secret that grants access to somebody's documents. The route reads, and if there is nothing to read it
    says so."""
    client.get("/api/daemon/status")
    assert not (tmp_path / "config" / "daemon").exists(), "the status route created the daemon's state directory"


def test_the_download_points_at_the_version_this_engine_actually_carries(client):
    """Pinned to the daemon's own tag, not `releases/latest`. `latest` follows whatever was released last —
    including an engine release with no daemon assets in it — and a 404 on the one screen whose entire job is
    handing somebody a file is the most expensive kind of broken link."""
    body = client.get("/api/daemon/status").json()
    version = body["expected_version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"unreadable daemon version: {version!r}"
    assert body["downloads"]["tag"] == f"daemon-v{version}"
    assert f"daemon-v{version}" in body["downloads"]["platforms"]["macos"]["artifact"]


@pytest.mark.parametrize("agent,expected", [
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "macos"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "windows"),
])
def test_the_installer_offered_first_is_for_the_visitors_machine(client, agent, expected):
    """From the VISITOR's user-agent, never the engine's own platform: on a cloud account the engine is a Linux
    container, and offering a Linux build to somebody on a Mac is offering them nothing."""
    assert client.get("/api/daemon/status", headers={"User-Agent": agent}).json()["platform"] == expected


# ── the cloud case, said out loud instead of pretended ────────────────────────────────────────────────────

def test_a_cloud_engine_does_not_probe_a_loopback_it_does_not_own(tmp_path, monkeypatch):
    """The daemon is on the USER's computer. A cloud engine probing 127.0.0.1 would at best time out on every
    poll and at worst reach a daemon belonging to whoever else runs on that host — so it does not probe at all,
    and the payload says `remote` rather than inventing a connection state it cannot know."""
    calls = []
    monkeypatch.setattr(daemon_api, "_state_dir", lambda: tmp_path / "config" / "daemon")
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: True)

    async def _never(*args, **kwargs):
        calls.append(args)
        return 0, {}
    monkeypatch.setattr(daemon_api, "_call", _never)

    app = FastAPI(); app.include_router(daemon_api.router)
    body = TestClient(app).get("/api/daemon/status").json()
    assert body["state"] == "remote" and body["local"] is False
    assert not calls, "a cloud engine probed loopback for a daemon that cannot be there"
    assert body["downloads"]["platforms"], "the cloud case is exactly the one that needs the download"


def test_a_cloud_engine_refuses_to_grant_a_folder_it_cannot_see(tmp_path, monkeypatch):
    """Answering "ok" to a grant nobody could deliver would put the interface and the machine permanently out
    of step, with the user believing a folder is shared that is not."""
    monkeypatch.setattr(daemon_api, "_state_dir", lambda: tmp_path / "config" / "daemon")
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: True)
    app = FastAPI(); app.include_router(daemon_api.router)
    r = TestClient(app).post("/api/daemon/permissions/grant", json={"path": "/tmp"},
                             headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 409 and r.json()["error"] == "no_daemon_from_cloud"


# ── the proxy is not a way around the daemon's own guards ─────────────────────────────────────────────────

@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "cross-site"},                      # no Origin at all: the header still betrays it
    {"Origin": "https://evil.example"},                    # an old browser that sends no Sec-Fetch-*
])
def test_another_site_cannot_add_a_folder_on_the_users_behalf(client, headers, monkeypatch):
    """⚠️ THE HOLE THE PROXY WOULD OTHERWISE OPEN. The daemon refuses anything that smells of a browser; the
    engine cannot, because its legitimate caller is one. Without CORS a hostile page cannot READ our answer —
    but `grant` is a state change, so it never needs to: fire and forget, and a folder is on the allowlist
    with nothing on screen to show for it.

    `_call` is replaced so that a guard failure cannot reach a real daemon on the machine running the suite."""
    async def _boom(*args, **kwargs):
        raise AssertionError("the request reached the daemon: the cross-origin guard did not fire")
    monkeypatch.setattr(daemon_api, "_call", _boom)
    headers = {**headers, "Host": "testserver"}
    r = client.post("/api/daemon/permissions/grant", json={"path": "/tmp"}, headers=headers)
    assert r.status_code == 403 and r.json()["error"] == "cross_origin"


@pytest.mark.parametrize("headers", [
    {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},   # our own page
    {"Sec-Fetch-Site": "none"},                                          # typed into the address bar
    {},                                                                  # a server-side client: curl, a script
])
def test_our_own_page_is_not_locked_out_by_the_guard(client, headers, monkeypatch):
    """THE COUNTERWEIGHT, and the failure direction a leak test never catches: a guard comparing `Origin`
    against a hardcoded hostname would pass every hostile case above and lock the user out of their own
    interface, because this engine is reached as localhost, as local.zaelar.com and as whatever a cloud
    account resolves to."""
    seen = []

    async def _ok(cfg, path, payload=None):
        seen.append(path)
        return 200, {"ok": True, "roots": ["/tmp"]}
    monkeypatch.setattr(daemon_api, "_call", _ok)
    monkeypatch.setattr(daemon_api, "_daemon_config", lambda: {"port": 45817, "token": "x" * 64})
    r = client.post("/api/daemon/permissions/grant", json={"path": "/tmp"},
                    headers={**headers, "Host": "testserver"})
    assert r.status_code == 200 and r.json()["roots"] == ["/tmp"], r.text
    assert seen == ["/permissions/grant"]


def test_the_engine_never_proxies_a_file_route():
    """⚠️ A RATCHET, and the single most important line in this file. The daemon spends five guards making
    sure no page can ever read a file through it; proxying `files.read` here would hand that capability to
    every page that can reach the engine, through the engine's own front door and with the engine's own
    credentials. The browser has no use for file contents — the screen shows which folders are granted, not
    what is inside them — and the agent reads files server-side, in-process. If a future change needs a file
    route on this surface, that change needs a threat model, not a test edit."""
    paths = {route.path for route in daemon_api.router.routes}
    assert paths == {"/api/daemon/status",
                     "/api/daemon/permissions/grant",
                     "/api/daemon/permissions/revoke"}, f"the daemon proxy grew a route: {sorted(paths)}"
    source = (ENGINE / "server" / "daemon_api.py").read_text(encoding="utf-8")
    assert "/files/" not in source.split("SAME-ORIGIN")[-1].split('"""', 1)[-1], (
        "the proxy references a daemon file route outside its own docstring"
    )


def test_the_refusal_the_daemon_wrote_is_the_one_the_user_reads(client, monkeypatch):
    """`daemon/fs/roots.py` goes to real trouble to say "that is your entire home folder — choose the folders
    you actually want me to work with". Collapsing that into "could not add folder" throws away the only part
    of the answer the user can act on, which is the whole V2-421/V2-507 lesson."""
    async def _refuse(cfg, path, payload=None):
        return 403, {"ok": False, "error": "too_broad", "message": "'/Users/x' is your entire home folder."}
    monkeypatch.setattr(daemon_api, "_call", _refuse)
    monkeypatch.setattr(daemon_api, "_daemon_config", lambda: {"port": 45817, "token": "x" * 64})
    r = client.post("/api/daemon/permissions/grant", json={"path": "/Users/x"},
                    headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 403
    assert "entire home folder" in r.json()["message"]


# ── the build, the installer and the screen agree about the file names ────────────────────────────────────

def _suffixes() -> list[str]:
    workflow = (ENGINE / ".github" / "workflows" / "daemon-artifacts.yml").read_text(encoding="utf-8")
    return re.findall(r"suffix:\s*(\S+)", workflow)


def _published_names() -> set[str]:
    """Every filename the release ends up carrying.

    Built by joining the two halves that decide it — the workflow declares which suffixes exist, and
    `release_names.py` owns the templates each build name is published under — rather than grepping the
    workflow for literals it no longer contains. A test that grepped for a literal would pass just as happily
    against a workflow that produced none of them."""
    spec = importlib.util.spec_from_file_location(
        "daemon_release_names_under_test", ENGINE / "daemon" / "packaging" / "release_names.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    names = set()
    for suffix in _suffixes():
        for _build_name, template in module._RENAMES:
            names.add(template.format(suffix=suffix))
        names.add(f"SHA256SUMS-{suffix}")
    # The architecture-independent scripts, copied once by the workflow's own step.
    workflow = (ENGINE / ".github" / "workflows" / "daemon-artifacts.yml").read_text(encoding="utf-8")
    names |= set(re.findall(r"(zaelar-daemon-(?:un)?install-[\w.-]+)", workflow))
    names |= set(re.findall(r"\b(get\.(?:sh|ps1))\b", workflow))
    return names


def test_the_release_gives_each_platform_its_own_file_names():
    """Both runners used to produce `zaelar-daemon.pyz`, `manifest.json` and `SHA256SUMS` under those exact
    names, and the release job flattens every downloaded artifact into one upload — so one platform's files
    silently overwrote the other's. With three jobs now (Apple Silicon, Intel, Windows) the collision would be
    three-way, which is why the names are generated from the suffix rather than written out."""
    suffixes = _suffixes()
    assert len(set(suffixes)) == len(suffixes), f"two build jobs claim the same suffix: {suffixes}"
    assert {"macos", "macos-x86_64", "windows"} <= set(suffixes), (
        f"a platform people install on is not built: {suffixes}"
    )
    names = _published_names()
    for suffix in suffixes:
        for template in ("zaelar-daemon-{s}", "SHA256SUMS-{s}", "manifest-{s}.json"):
            assert template.format(s=suffix) in names, f"{template.format(s=suffix)} is never produced"


def test_an_intel_mac_is_not_handed_an_apple_silicon_binary():
    """⚠️ A PyInstaller bundle carries a real interpreter compiled for ONE architecture, and `macos-latest` has
    been arm64 since macos-14. Without a second Mac job an Intel user downloaded a file that fails with "bad
    CPU type in executable" — which reads as a corrupt download, not as a wrong build. The bootstrap picks by
    `uname -m`, which is why it can be right where a user-agent cannot."""
    script = (ENGINE / "daemon" / "packaging" / "get.sh").read_text(encoding="utf-8")
    assert "uname -m" in script
    assert "arm64)" in script and "x86_64)" in script
    assert "zaelar-daemon-macos-x86_64" in script


def test_every_asset_the_screen_links_to_is_one_the_release_publishes():
    """The three-way join this node exists for: the API names a file, the workflow produces it, the installer
    accepts it. Any two of those agreeing is not enough."""
    names = _published_names()
    for platform, assets in daemon_api._ASSETS.items():
        for filename in assets.values():
            assert filename in names, f"{platform}: the screen offers {filename} and no release makes it"


# ── the one-line command, which is the path people actually take ──────────────────────────────────────────

@pytest.mark.parametrize("script", ["get.sh", "get.ps1"])
def test_the_bootstrap_the_command_runs_exists_and_asks_for_no_password(script):
    """⚠️ The whole reason the command is the main path: macOS quarantine and the Windows Mark of the Web are
    written by whatever SAVED the file, and `curl`/`Invoke-WebRequest` do not write them. A daemon that arrives
    this way raises no Gatekeeper dialog and no SmartScreen panel, unsigned, with no developer account. That
    property is worth nothing if the script then asks for an administrator password."""
    text = (ENGINE / "daemon" / "packaging" / script).read_text(encoding="utf-8").lower()
    for elevation in ("sudo ", "runas", "-verb runas", "requireadministrator"):
        assert elevation not in text, f"{script} escalates ({elevation.strip()!r})"


@pytest.mark.parametrize("script,hasher", [("get.sh", "shasum -a 256"), ("get.ps1", "Get-FileHash")])
def test_nothing_is_executed_before_its_checksum_is_checked(script, hasher):
    """⚠️ THE ORDER IS THE POINT, not the presence of a hash. Piping a script into a shell is as safe as its
    origin and no safer, so the least this can do is prove the binary that arrived is the binary that was
    built — while it is still an inert blob in a temp directory, BEFORE it is made executable, moved, or handed
    to launchd. A checksum verified after the install would be a comment, not a control.

    What it is NOT is provenance: two files from the same release agreeing catches a corrupt download and an
    altered mirror, and whoever can replace one can replace the other. That needs a signature."""
    text = (ENGINE / "daemon" / "packaging" / script).read_text(encoding="utf-8")
    assert hasher in text, f"{script} never hashes what it downloaded"
    verified_at = text.index(hasher)
    invocation = 'bash "$WORK/install.sh"' if script == "get.sh" else "& $installer"
    ran_at = text.index(invocation)
    assert verified_at < ran_at, f"{script} runs the installer before checking the download"


@pytest.mark.parametrize("script", ["get.sh", "get.ps1"])
def test_the_bootstrap_installs_a_DAEMON_release_and_not_merely_the_latest(script):
    """`releases/latest` follows whatever was released last, and this repository also tags the engine — so the
    newest release regularly carries no daemon assets at all. Filtering tags by prefix is what stops the
    command from failing on a perfectly healthy repository."""
    text = (ENGINE / "daemon" / "packaging" / script).read_text(encoding="utf-8")
    assert "daemon-v" in text, f"{script} does not filter releases by the daemon's tag prefix"
    # The USAGE, not the word: both scripts explain in a comment why `releases/latest` is wrong, and a test
    # that forbade the substring would be tripped by its own documentation.
    assert "releases/latest/download" not in text, f"{script} builds a URL from the wrong release"


def test_the_command_the_screen_shows_runs_the_script_the_repo_ships():
    """The fourth joint: the words on screen have to be the file that exists. A command with a typo in its URL
    is indistinguishable, to the user, from a product that does not work."""
    downloads = daemon_api._downloads("0.2.0")["platforms"]
    for platform, entry in downloads.items():
        script = daemon_api._BOOTSTRAP[platform]["script"]
        assert (ENGINE / "daemon" / "packaging" / script).is_file(), f"{script} is offered and does not exist"
        assert script in entry["command"] and entry["bootstrap"].endswith(script)
    assert downloads["macos"]["command"].startswith("curl ")
    assert downloads["windows"]["command"].startswith("irm ")


def test_the_screen_leads_with_the_command_and_not_with_a_download_button():
    """The direct file still works and is still offered — but it is the path that COSTS a security dialog,
    because a browser is what marks a download as quarantined. Leading with it would mean every user meets
    "Windows protected your PC" on a product whose main claim is that it is careful with their machine."""
    screen = (ENGINE / "frontend" / "app" / "components" / "DaemonSetup.js").read_text(encoding="utf-8")
    # ⚠️ The command must be in the element that DISPLAYS it, not merely mentioned somewhere in the file. A
    # first version of this check looked for `current().command` anywhere, and deleting the `<code>` block left
    # it green — the copy button still referenced the same expression, so the test passed over a screen where
    # the command was invisible and only copyable by a button labelled "Copy" with nothing above it.
    shown = re.search(r'class:\s*"dsx-cmd"\s*\}\s*,\s*\(\)\s*=>\s*current\(\)\.command', screen)
    assert shown, "the install command is not rendered in the block that shows it"
    command_at = shown.start()
    manual_at = screen.index('h("details"')
    assert command_at < manual_at, "the manual download is shown above the command"
    assert "daemon.manual.body" in screen, "the screen never warns that the manual path raises a dialog"


# ── the interface: the icon, the screen, the words ────────────────────────────────────────────────────────

def test_the_icon_is_visible_to_the_people_who_most_need_it():
    """⚠️ Every other control in the TopBar is hidden behind `store.cloudProfile()`, and copying that pattern
    here would hide the daemon from exactly the audience that cannot solve the problem any other way: somebody
    on a cloud account, whose own computer is the one thing the cloud agent cannot reach."""
    topbar = (ENGINE / "frontend" / "app" / "components" / "TopBar.js").read_text(encoding="utf-8")
    block = topbar.split('id: "daemonBtn"')[0].rsplit('h("button"', 1)[-1]
    assert "cloudProfile" not in block, "the daemon icon was gated on the profile that needs it most"
    assert "daemonBtn" in topbar and "DESKTOP_ICON" in topbar


def test_the_setup_screen_is_a_registered_surface_and_not_voice_addressable():
    """`system-surfaces.js` is the only source of truth for what the frontend mounts, so a component that is
    not in it is a component that does not exist. `name: null` because the thing behind the icon is an install
    step and a permission grant — both deliberate clicks, neither a sentence anybody says out loud."""
    surfaces = (ENGINE / "frontend" / "app" / "core" / "system-surfaces.js").read_text(encoding="utf-8")
    entry = surfaces.split('id: "daemon-setup"')[1].split("},")[0]
    assert "DaemonSetup" in entry and "name: null" in entry and "aliases: null" in entry


def test_no_label_on_the_daemon_screen_shows_a_raw_key():
    """`t()` returns the KEY when a bundle is missing it, and the key is truthy — so a missing translation does
    not fall back to English, it renders `daemon.folders.revoke` on a button. Both shipped bundles are checked,
    because the Spanish one is the operator's own interface."""
    used = set()
    for name in ("app/components/DaemonSetup.js", "app/components/TopBar.js",
                 "mobile/app/shell/MenuSheet.js"):
        text = (ENGINE / "frontend" / name).read_text(encoding="utf-8")
        used |= {m for m in re.findall(r't\("([a-z0-9_.]+)"\)', text)
                 if m.startswith("daemon.") or m == "topbar.daemon.title"}
    assert len(used) >= 20, f"only {len(used)} keys found — the scan stopped matching the source"
    for lang in ("en", "es"):
        bundle = json.loads((ENGINE / "i18n" / "bundles" / f"{lang}.json").read_text(encoding="utf-8"))
        missing = sorted(used - set(bundle))
        assert not missing, f"{lang}.json is missing {missing}"


def test_the_screen_admits_what_it_cannot_do_from_the_cloud():
    """The conservative-documentation rule (INI-026 B5) applied to a product screen. A cloud user can download
    the daemon today; wiring it to the cloud agent is the relay, which is not built. A download screen that
    implied otherwise would be the fastest possible way to earn "it doesn't work"."""
    for lang in ("en", "es"):
        bundle = json.loads((ENGINE / "i18n" / "bundles" / f"{lang}.json").read_text(encoding="utf-8"))
        limit = bundle["daemon.remote.limit"]
        assert len(limit) > 40 and ("built" in limit or "construyendo" in limit), limit


def test_a_phone_is_told_why_it_cannot_do_this_rather_than_shown_a_dead_control():
    """A desktop daemon is not installed from a phone. The mobile row therefore REPORTS and does not act — but
    omitting it entirely would read as "there is no daemon" instead of "you cannot set it up from here"."""
    sheet = (ENGINE / "frontend" / "mobile" / "app" / "shell" / "MenuSheet.js").read_text(encoding="utf-8")
    row = sheet.split("daemon.mobile.row")[0].rsplit("h(\"div\"", 1)[-1]
    assert "zm-row-static" in row, "the mobile daemon row is not the static, non-tappable kind"
    assert "daemon.mobile.hint" in sheet
