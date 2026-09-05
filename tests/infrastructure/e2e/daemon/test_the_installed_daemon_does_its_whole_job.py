"""The daemon a user actually INSTALLS, exercised end to end over real HTTP (V2-575 · P0).

WHY THIS EXISTS AS ITS OWN TEST. The unit nodes (7.34/7.35/7.36) each hold one half of the daemon still: the
permission circuit is called in-process, the HTTP guards run a handler against a server built inside the test,
and the boot wiring is a source read. All three can be green while the thing a user installs does not start —
`python -m daemon` resolves its own state directory, reads its own config, binds its own port and serves its
own routes, and NOT ONE of those steps is exercised by calling a function.

So this boots the real process, the way `scripts/zaelar.py` boots it, and drives EVERY capability it currently
has through the same door the engine will use: `POST /files/...` with a bearer token over loopback. Nothing is
mocked and no function is called directly — if it passes, the daemon works.

SELF-CONTAINED AND NON-DESTRUCTIVE, deliberately: it builds a throwaway workspace with its own documents, its
own `daemon.json` and its own PORT, so it can never touch the operator's files, never collide with the daemon
their engine may have running on 45817, and never leave state behind. Same contract as the mobile render tests
(`tests/browser/e2e/mobile/`), for the same reason: a test that needs the operator's live instance is a test
nobody runs.

Run:  ./.venv/bin/python -m pytest tests/infrastructure/e2e/daemon/ -q
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]      # tests/infrastructure/e2e/daemon/ → four levels up is engine/
TOKEN = "e2e-" + "0" * 60                          # fixed so the test can assert the guard, never a real secret
BOOT_TIMEOUT_S = 15.0


# ── the throwaway installation ────────────────────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _listening(port: int, timeout: float = 0.4) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _make_documents(root: Path) -> Path:
    """A small tree with one of everything the circuit has an opinion about."""
    docs = root / "Documents"
    (docs / "notes").mkdir(parents=True)
    (docs / "notes" / "shopping.md").write_text("milk\nbread\nbudget: 40 EUR\n", encoding="utf-8")
    (docs / "report-2026.txt").write_text("Quarterly report. The magic word is SALAMANDER.\n", encoding="utf-8")
    (docs / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    # A credential file INSIDE the granted folder: allow-listing a folder must not allow-list its secrets.
    (docs / ".env").write_text("SECRET=hunter2\n", encoding="utf-8")

    # Somewhere outside the allowlist, and a symlink pointing at it from inside.
    private = root / "private"
    private.mkdir()
    (private / "keys.txt").write_text("do not read me\n", encoding="utf-8")
    try:
        (docs / "escape").symlink_to(private, target_is_directory=True)
    except OSError:                       # pragma: no cover — Windows without developer mode
        pass
    return docs


@pytest.fixture(scope="module")
def daemon(tmp_path_factory):
    """The real `python -m daemon`, in its own workspace, on its own port."""
    ws = tmp_path_factory.mktemp("daemon-e2e")
    docs = _make_documents(ws)
    port = _free_port()

    state = ws / "config" / "daemon"
    state.mkdir(parents=True)
    (state / "daemon.json").write_text(json.dumps({
        "version": 1, "port": port, "token": TOKEN, "roots": [], "configured": False,
    }), encoding="utf-8")

    env = dict(os.environ)
    env["ZAELAR_WORKSPACE"] = str(ws)
    # The daemon's HOME is the workspace, not the runner of the tests: `permissions.candidates()` scans
    # `Path.home()` for the usual folders, and reading the REAL home made this test pass on the operator's Mac
    # by accident (his ~/Documents exists) and fail on any machine without one — CI found it on its first run
    # (2026-09-05). The workspace already carries the Documents this fixture creates.
    env["HOME"] = str(ws)
    env["PYTHONPATH"] = str(ENGINE) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([sys.executable, "-m", "daemon"], cwd=str(ENGINE), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"the daemon exited during boot ({proc.returncode}):\n{proc.stdout.read()}")
        if _listening(port):
            break
        time.sleep(0.05)
    else:
        proc.kill()
        raise AssertionError(f"the daemon never listened on {port} within {BOOT_TIMEOUT_S}s")

    try:
        yield {"port": port, "ws": ws, "docs": docs, "proc": proc, "state": state}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:   # pragma: no cover
            proc.kill()


# ── the door the engine will use ──────────────────────────────────────────────────────────────────────────

def call(daemon, method: str, path: str, body: dict | None = None, *, token: str | None = TOKEN,
         headers: dict | None = None) -> tuple[int, dict]:
    url = f"http://127.0.0.1:{daemon['port']}{path}"
    data = json.dumps(body or {}).encode() if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# ── it boots, and says what it can do ─────────────────────────────────────────────────────────────────────

def test_the_installed_daemon_boots_and_answers(daemon):
    status, body = call(daemon, "GET", "/health", token=None)
    assert status == 200 and body["daemon"] == "zaelar"
    assert body["configured"] is False, "a fresh install has not been configured by anyone yet"
    assert body["capabilities"] == ["files.list", "files.read", "files.search"], (
        "the engine reads this to decide what it may offer the user; a capability listed here that P0 does not "
        "have is a promise the product cannot keep"
    )


def test_a_browser_cannot_reach_the_running_daemon(daemon):
    """Guard 2 against the LIVE process, not a handler in a test harness. Any page the operator has open can
    `fetch('http://127.0.0.1:<port>/files/read')`, so this is the one that matters most."""
    status, body = call(daemon, "POST", "/files/read", {"path": "x"}, headers={"Origin": "https://evil.example"})
    assert status == 401 and body["error"] == "unauthorized"

    status, _ = call(daemon, "GET", "/health", token=None, headers={"Sec-Fetch-Site": "cross-site"})
    assert status == 401, "even the public route is refused to a browser"


def test_no_token_is_no_access(daemon):
    assert call(daemon, "GET", "/permissions", token=None)[0] == 401
    assert call(daemon, "GET", "/permissions", token="not-the-token")[0] == 401


# ── nothing is readable until the user says so ────────────────────────────────────────────────────────────

def test_a_fresh_install_reads_nothing_and_proposes_documents(daemon):
    """The load-bearing half of the permission circuit: installing the daemon grants NOTHING. Documents is what
    the wizard PROPOSES (`suggested`), never what is already readable."""
    status, body = call(daemon, "GET", "/permissions")
    assert status == 200
    assert body["roots"] == [], "a fresh install has access to nothing at all"
    assert isinstance(body["candidates"], list) and body["candidates"], "the wizard needs folders to offer"
    assert all(set(c) >= {"path", "label", "suggested"} for c in body["candidates"])
    assert sum(1 for c in body["candidates"] if c["suggested"]) <= 1, (
        "at most one pre-checked entry, or 'Documents by default' stops meaning anything"
    )


def test_reading_before_granting_says_so(daemon):
    status, body = call(daemon, "POST", "/files/read", {"path": str(daemon["docs"] / "report-2026.txt")})
    assert status == 403 and body["error"] == "no_folders", (
        "the refusal has to name the boundary, not be a bare 403 (V2-421/V2-507)"
    )


# ── the whole job, once a folder is granted ───────────────────────────────────────────────────────────────

def test_granting_a_folder_then_listing_reading_and_searching_it(daemon):
    docs = daemon["docs"]

    status, body = call(daemon, "POST", "/permissions/grant", {"path": str(docs)})
    assert status == 200 and body["roots"] == [str(docs.resolve())], (
        "the allowlist stores the RESOLVED root; on macOS ~/Documents is often a symlink into iCloud, and a "
        "circuit that stores the unresolved path refuses the user their own documents"
    )

    # With no path, listing IS the allowlist — the wizard's first screen.
    status, body = call(daemon, "POST", "/files/list", {})
    assert status == 200 and body["roots"] == [str(docs.resolve())]

    status, body = call(daemon, "POST", "/files/list", {"path": str(docs)})
    assert status == 200
    names = {e["name"]: e for e in body["entries"]}
    assert "notes" in names and names["notes"]["kind"] == "folder"
    assert names["report-2026.txt"]["textual"] is True
    assert names["photo.png"]["image"] is True

    status, body = call(daemon, "POST", "/files/read", {"path": str(docs / "report-2026.txt")})
    assert status == 200 and "SALAMANDER" in body["text"] and body["truncated"] is False

    status, body = call(daemon, "POST", "/files/search", {"query": "shopping"})
    assert status == 200 and any(h["name"] == "shopping.md" for h in body["hits"])
    assert body["stopped_early"] in (None, "", False), "a small tree must not hit any budget"

    status, body = call(daemon, "POST", "/files/search", {"query": "salamander", "content": True})
    assert status == 200 and any(h["name"] == "report-2026.txt" for h in body["hits"]), (
        "searching inside files is the capability /health advertises"
    )


def test_a_read_that_hits_the_cap_says_it_was_truncated(daemon):
    """A silent truncation is a lie the agent repeats as if it were the whole document."""
    status, body = call(daemon, "POST", "/files/read",
                        {"path": str(daemon["docs"] / "report-2026.txt"), "max_bytes": 10})
    assert status == 200 and body["truncated"] is True and len(body["text"]) == 10


def test_a_binary_file_is_refused_with_the_reason(daemon):
    status, body = call(daemon, "POST", "/files/read", {"path": str(daemon["docs"] / "photo.png")})
    assert status == 403 and body["error"] == "binary"


# ── the escapes, against the live process ─────────────────────────────────────────────────────────────────

def test_walking_out_with_dotdot_is_refused(daemon):
    escape = str(daemon["docs"] / ".." / "private" / "keys.txt")
    status, body = call(daemon, "POST", "/files/read", {"path": escape})
    assert status == 403 and body["error"] == "outside_allowlist"
    assert body["folders"] == [str(daemon["docs"].resolve())], "the refusal says which folders DO work"


def test_a_symlink_out_of_the_granted_folder_is_refused(daemon):
    if not (daemon["docs"] / "escape").is_symlink():
        pytest.skip("this filesystem would not create the symlink")
    status, body = call(daemon, "POST", "/files/read", {"path": str(daemon["docs"] / "escape" / "keys.txt")})
    assert status == 403 and body["error"] == "outside_allowlist", (
        "resolving the request is what catches this: the path is INSIDE the granted folder until you follow it"
    )


def test_a_credential_file_inside_a_granted_folder_is_still_refused(daemon):
    status, body = call(daemon, "POST", "/files/read", {"path": str(daemon["docs"] / ".env")})
    assert status == 403 and body["error"] == "sensitive", (
        "granting a folder is not granting its secrets"
    )


def test_the_daemons_own_state_is_not_readable_through_it(daemon):
    call(daemon, "POST", "/permissions/grant", {"path": str(daemon["ws"])})
    try:
        status, body = call(daemon, "POST", "/files/read", {"path": str(daemon["state"] / "daemon.json")})
        assert status == 403, "daemon.json holds the API token: reading it would hand over every future request"
        assert body["error"] in ("protected", "sensitive")
    finally:
        call(daemon, "POST", "/permissions/revoke", {"path": str(daemon["ws"])})


def test_an_unknown_route_is_a_404_not_a_crash(daemon):
    status, body = call(daemon, "POST", "/files/delete", {"path": "x"})
    assert status == 404 and body["error"] == "unknown_route", (
        "writing is P5; asking for it must be a clean refusal, never a stack trace"
    )


# ── taking it back ────────────────────────────────────────────────────────────────────────────────────────

def test_revoking_a_folder_actually_stops_the_reading(daemon):
    """The user taking a permission back is the half a permission circuit is JUDGED on. If revoke only edits a
    file the running daemon has already cached, the wizard's 'remove folder' button lies."""
    docs = daemon["docs"]
    target = str(docs / "report-2026.txt")
    assert call(daemon, "POST", "/files/read", {"path": target})[0] == 200

    status, body = call(daemon, "POST", "/permissions/revoke", {"path": str(docs)})
    assert status == 200 and body["roots"] == []

    status, body = call(daemon, "POST", "/files/read", {"path": target})
    assert status == 403 and body["error"] == "no_folders"

    call(daemon, "POST", "/permissions/grant", {"path": str(docs)})     # leave it as we found it


# ── the record of what was opened ─────────────────────────────────────────────────────────────────────────

def test_the_audit_log_records_what_was_allowed_AND_what_was_refused(daemon):
    """Only logging successes would make the log useless for the one question it exists to answer: did anything
    try to reach outside what I allowed?"""
    status, body = call(daemon, "POST", "/audit", {"limit": 200})
    assert status == 200
    ops = {(e["op"], e["outcome"]) for e in body["entries"]}
    assert ("files.read", "ok") in ops
    assert ("files.read", "refused") in ops
    assert ("permissions.grant", "ok") in ops
    assert ("permissions.revoke", "ok") in ops
    assert any(e["op"] == "daemon.start" for e in body["entries"]), "the process logged its own start"


def test_a_relay_caller_is_marked_in_the_log(daemon):
    """P3 forward-compat, and it is an audit property, not a feature: when a cloud agent reaches in, the user's
    log has to say it was the cloud and not their own engine."""
    call(daemon, "POST", "/files/list", {}, headers={"X-Zaelar-Relay": "1"})
    _, body = call(daemon, "POST", "/audit", {"limit": 50})
    assert any(e["caller"] == "relay" for e in body["entries"])


def test_the_state_stays_private_on_disk(daemon):
    """0600 on the file that holds the token, checked on the file the RUNNING daemon wrote."""
    mode = (daemon["state"] / "daemon.json").stat().st_mode & 0o777
    if os.name != "nt":
        assert mode == 0o600, f"daemon.json is {oct(mode)}; anyone on this machine could read the token"


# ── the terminal, which is the only way to see the token ──────────────────────────────────────────────────

def _cli(daemon, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["ZAELAR_WORKSPACE"] = str(daemon["ws"])
    env["PYTHONPATH"] = str(ENGINE) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "daemon", *args], cwd=str(ENGINE), env=env,
                          capture_output=True, text=True, timeout=30)


def test_the_cli_reports_the_running_daemon(daemon):
    r = _cli(daemon, "status")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["running"] is True and out["port"] == daemon["port"]
    assert out["roots"] == [str(daemon["docs"].resolve())]


def test_the_cli_prints_the_token_because_nothing_else_can(daemon):
    r = _cli(daemon, "token")
    assert r.returncode == 0 and r.stdout.strip() == TOKEN


def test_the_cli_can_grant_and_revoke_and_says_a_restart_is_needed(daemon):
    """The running daemon has the allowlist cached in memory, so a terminal grant does not take effect until it
    restarts. Saying so beats letting the user watch a granted folder stay invisible and conclude the permission
    system is broken."""
    sub = daemon["docs"] / "notes"
    r = _cli(daemon, "allow", str(sub))
    assert r.returncode == 0 and "restart" in r.stdout.lower()

    r = _cli(daemon, "deny", str(sub))
    assert r.returncode == 0

    r = _cli(daemon, "allow", str(daemon["ws"] / "private" / "keys.txt"))
    assert r.returncode != 0, "granting a file rather than a folder is refused"


def test_the_cli_refuses_to_grant_a_sensitive_folder(daemon):
    r = _cli(daemon, "allow", str(Path.home() / ".ssh"))
    assert r.returncode != 0 and r.stderr.strip(), "and it says why"


def test_the_cli_without_a_command_explains_itself(daemon):
    r = _cli(daemon, "wat")
    assert r.returncode == 2 and "python -m daemon" in r.stderr


# ── and it lets go of the port ────────────────────────────────────────────────────────────────────────────

def test_stopping_the_daemon_frees_its_port(tmp_path):
    """An orphan holding the port is the failure `scripts/zaelar.py` and the launcher sweep exist for, and it is
    silent: the next start dies on EADDRINUSE with nothing pointing at the cause."""
    port = _free_port()
    state = tmp_path / "config" / "daemon"
    state.mkdir(parents=True)
    (state / "daemon.json").write_text(json.dumps(
        {"version": 1, "port": port, "token": TOKEN, "roots": [], "configured": False}), encoding="utf-8")

    env = dict(os.environ)
    env["ZAELAR_WORKSPACE"] = str(tmp_path)
    env["PYTHONPATH"] = str(ENGINE) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([sys.executable, "-m", "daemon"], cwd=str(ENGINE), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline and not _listening(port):
        time.sleep(0.05)
    assert _listening(port), "it never came up"

    proc.terminate()
    proc.wait(timeout=5)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _listening(port):
        time.sleep(0.05)
    assert not _listening(port), f"port {port} is still held after the daemon stopped"
