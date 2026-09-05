"""The daemon against something on the machine that is NOT the engine (V2-575 · P0, security pass).

The sibling node asks "can a web page talk to it?" and answers with the token, the Origin check and the absent
CORS headers. This one asks the harder question: what does a caller who has read the source, controls a local
process and can point a DNS record at 127.0.0.1 actually get?

WHAT EACH SECTION IS FOR, because a guard whose reason is not written down is a guard somebody deletes:

  THE REBIND. The Origin check has a hole and it is not hypothetical. A page on `evil.example` whose DNS is
  re-pointed at 127.0.0.1 makes a SAME-ORIGIN request, and a same-origin request carries NO Origin header at
  all. Modern browsers still send `Sec-Fetch-Site`, so the older guard usually catches it — "usually" is one
  header away from nothing, and the engine has already paid for this exact class once against its own cluster
  control plane. What betrays the rebind is `Host`: the browser still names the site it THINKS it is on.

  JSON ONLY. A browser can send `text/plain` cross-origin with NO preflight — those are "simple requests", the
  one shape that gets past a CORS policy without asking. Requiring `application/json` forces a preflight, and
  the preflight never succeeds. This closes the vector on its own, independently of Origin and Sec-Fetch.

  ONE SHAPE OF REFUSAL. Every guard answers with the same 401 and the same sentence. Telling a caller WHICH one
  they tripped turns "try things until something works" into "read the error and adapt" — a free map of the
  defences. The precise reason goes to the audit log, where somebody entitled to know can read it.

  THE UNAUTHORIZED ONES ARE AUDITED. This was the gap: the old shape returned 401 before recording anything, so
  the single most security-relevant signal there is — a run of failed attempts — left no trace at all, in a log
  whose own docstring says refusals are the half that earns the file.

  A PIPE IS NOT A DOCUMENT. A named pipe inside a granted folder is not an attack, it is a Tuesday, and reading
  one blocks until somebody writes — forever, on a thread that is never coming back.

Every check has its counterweight in the same file: the legitimate call right next to the refused one still
works. A daemon that refuses everything passes any battery of leak tests and is, to the user, a broken product
with a good excuse.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture()
def live(tmp_path, monkeypatch):
    """A real daemon on a real ephemeral port, serving a real temp folder, with the throttle reset.

    The throttle is a module-level singleton on purpose (one process, one user), which makes it shared state
    between tests: a previous test's flood would otherwise add a real sleep to this one and, worse, decide
    whether this one's refusal gets recorded."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg
    from daemon.http import lifecycle
    from daemon.security import throttle

    dcfg.reset_cache()
    throttle.SHARED.note_success()

    docs = tmp_path / "Docs"
    docs.mkdir()
    (docs / "note.txt").write_text("hello", encoding="utf-8")
    dcfg.save({"roots": [str(docs)], "configured": True})

    server = lifecycle.build(port=0)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"base": f"http://127.0.0.1:{port}", "port": port, "token": dcfg.token(), "docs": docs}
    finally:
        server.shutdown()
        server.server_close()
        throttle.SHARED.note_success()
        dcfg.reset_cache()


def call(live, path, *, token=None, headers=None, body=None, method=None, content_type="application/json"):
    """Returns (status, parsed-json). Errors come back as a status too — an HTTP guard's job is to answer, not
    to hang up, and a test that only ever sees exceptions cannot check what it said."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        live["base"] + path, data=data, method=method or ("POST" if data is not None else "GET"))
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    if data is not None and content_type is not None:
        request.add_header("Content-Type", content_type)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


# ── the rebind: a page that re-points DNS at 127.0.0.1 sends no Origin at all ──────────────────────────────

@pytest.mark.parametrize("host", ["evil.example", "evil.example:80", "attacker.test:9999"])
def test_a_request_naming_someone_elses_host_is_refused(live, host):
    """The rebind signature. A real client on this machine has no reason to name anything but loopback, so this
    costs a legitimate caller nothing and is the only thing left standing when Origin is absent by design."""
    status, body = call(live, "/files/read", token=live["token"], headers={"Host": host},
                        body={"path": str(live["docs"] / "note.txt")})
    assert status == 401, f"a request claiming to be for {host} was served"
    assert "text" not in body


def test_a_host_that_merely_starts_with_a_loopback_name_is_refused(live):
    """`startswith` is the wrong check and it is the one somebody reaches for: an attacker registers
    `127.0.0.1.evil.example` and a prefix comparison waves it through. Exact match, always."""
    status, _ = call(live, "/permissions", token=live["token"],
                     headers={"Host": "127.0.0.1.evil.example"})
    assert status == 401


def test_a_request_with_no_host_header_at_all_is_refused(live):
    """HTTP/1.1 requires one. Something that omits it is not a browser and not a well-formed client, and
    accepting it would leave a way to skip this guard entirely by simply not participating."""
    status, _ = call(live, "/permissions", token=live["token"], headers={"Host": ""})
    assert status == 401


def test_the_host_must_name_THIS_daemons_port(live):
    """A loopback name with the wrong port is still a rebind: the browser is naming a different service it
    believes it is talking to."""
    status, _ = call(live, "/permissions", token=live["token"],
                     headers={"Host": f"127.0.0.1:{live['port'] + 1}"})
    assert status == 401


@pytest.mark.parametrize("host_template", ["127.0.0.1:{port}", "localhost:{port}", "[::1]:{port}"])
def test_the_legitimate_loopback_names_still_work(live, host_template):
    """The counterweight, and the half that would have caught an over-strict rule: the engine reaches the
    daemon by whichever of these its client library picks, and refusing one of them breaks the product with
    every leak test still green."""
    status, body = call(live, "/files/read", token=live["token"],
                        headers={"Host": host_template.format(port=live["port"])},
                        body={"path": str(live["docs"] / "note.txt")})
    assert status == 200 and body["text"] == "hello"


# ── JSON only: the simple-request vector ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded",
                                          "multipart/form-data", None])
def test_a_body_that_is_not_declared_as_json_is_refused(live, content_type):
    """These three are exactly the types a browser may send cross-origin with no preflight. Requiring JSON means
    the browser must ask first, and the preflight never succeeds."""
    status, body = call(live, "/files/read", token=live["token"], content_type=content_type,
                        body={"path": str(live["docs"] / "note.txt")})
    assert status == 401, f"a body declared as {content_type} was served"
    assert "text" not in body


def test_a_json_body_with_a_charset_parameter_still_works(live):
    """`application/json; charset=utf-8` is what several HTTP clients send by default. Rejecting it would make
    the guard look like a broken daemon to whoever picked one of those."""
    status, body = call(live, "/files/read", token=live["token"],
                        content_type="application/json; charset=utf-8",
                        body={"path": str(live["docs"] / "note.txt")})
    assert status == 200 and body["text"] == "hello"


# ── every refusal looks the same from outside ─────────────────────────────────────────────────────────────

def test_all_the_guards_answer_with_the_same_words(live):
    """Five different failures, one answer. If they ever diverge, a caller can tell which guard they tripped and
    walk the defences one at a time."""
    target = {"path": str(live["docs"] / "note.txt")}
    answers = [
        call(live, "/files/read", body=target)[1],                                          # no token
        call(live, "/files/read", token="0" * 64, body=target)[1],                          # wrong token
        call(live, "/files/read", token=live["token"], headers={"Host": "evil.example"}, body=target)[1],
        call(live, "/files/read", token=live["token"], headers={"Origin": "https://x.test"}, body=target)[1],
        call(live, "/files/read", token=live["token"], content_type="text/plain", body=target)[1],
    ]
    assert all(a == answers[0] for a in answers), f"the refusals differ and can be told apart: {answers}"
    assert answers[0]["error"] == "unauthorized"
    for leak in ("host", "token", "origin", "content-type", "reason"):
        assert leak not in json.dumps(answers[0]).lower(), f"the refusal names the guard it tripped ({leak})"


# ── the unauthorized attempts ARE recorded ────────────────────────────────────────────────────────────────

def test_a_refused_attempt_lands_in_the_audit_log_with_its_real_reason(live):
    """The log is where the precise reason lives, since the response deliberately will not say it. A user asking
    "did anything try to talk to my daemon?" has no other place to look."""
    from daemon import audit
    call(live, "/files/read", token="0" * 64, body={"path": "x"})
    entries = audit.tail(20)
    assert any(e["outcome"] == "refused" and e.get("reason") == "bad_token" for e in entries), entries


def test_a_rebound_request_is_recorded_as_a_rebind_and_not_as_a_bad_token(live):
    """The two are different stories about what is happening to this machine, and collapsing them would make
    the log unable to answer the only question it is kept for."""
    from daemon import audit
    call(live, "/permissions", token=live["token"], headers={"Host": "evil.example"})
    assert any(e.get("reason") == "bad_host" for e in audit.tail(20))


def test_a_flood_of_refusals_is_collapsed_instead_of_written_out_in_full(live):
    """Recording every refusal plus "a local process can send thousands a second" is a way to fill the user's
    disk and, worse, to push the interesting line off the end of a rotated log."""
    from daemon import audit
    for _ in range(30):
        call(live, "/permissions", token="0" * 64)
    refusals = [e for e in audit.tail(200) if e.get("reason") == "bad_token"]
    assert 0 < len(refusals) < 30, f"{len(refusals)} lines for 30 attempts: the flood was not collapsed"


def test_the_throttle_delays_a_persistent_caller_but_never_a_first_failure():
    """A legitimate caller fails at most once, while it is being paired, and must pay nothing for it."""
    from daemon.security.throttle import FREE_FAILURES, MAX_DELAY_S, Throttle
    throttle = Throttle()
    for _ in range(FREE_FAILURES):
        _record, delay, _suppressed = throttle.note("bad_token")
        assert delay == 0, "an occasional failure is not a flood"
    delays = [throttle.note("bad_token")[1] for _ in range(50)]
    assert delays[0] > 0 and max(delays) <= MAX_DELAY_S, "the delay must ramp and must stay capped"


def test_a_successful_request_clears_the_slate():
    """Whatever was happening, it is not happening now — and a caller who mistypes their own token once must not
    be slowed down for the rest of the session."""
    from daemon.security.throttle import FREE_FAILURES, Throttle
    throttle = Throttle()
    for _ in range(FREE_FAILURES + 10):
        throttle.note("bad_token")
    throttle.note_success()
    assert throttle.note("bad_token")[1] == 0


# ── an internal error does not narrate itself to the caller ───────────────────────────────────────────────

def test_an_unexpected_failure_answers_without_leaking_its_text(live, monkeypatch):
    """Exception text here routinely contains absolute paths and internal names, and the caller that most wants
    to read it is the one that should not. It goes to the audit log instead, where the user can."""
    from daemon import audit
    from daemon.http import routes

    def boom(_request, _payload):
        raise RuntimeError("/Users/someone/private/thing.txt exploded")

    monkeypatch.setitem(routes.TABLE, ("POST", "/files/list"), boom)
    status, body = call(live, "/files/list", token=live["token"], body={})
    assert status == 500
    assert "exploded" not in json.dumps(body) and "/Users/" not in json.dumps(body)
    assert any(e["outcome"] == "error" and "exploded" in json.dumps(e.get("detail") or {})
               for e in audit.tail(20)), "the detail did not reach the log either, so it is simply lost"


# ── a body bigger than the cap, and numbers off the wire ──────────────────────────────────────────────────

def test_a_body_larger_than_the_cap_is_refused_before_it_is_read(live):
    from daemon.http.handler import MAX_BODY_BYTES
    status, body = call(live, "/files/read", token=live["token"],
                        body={"path": "x", "padding": "a" * (MAX_BODY_BYTES + 10)})
    assert status == 413 and body["error"] == "too_large"


@pytest.mark.parametrize("limit", ["lots", None, -5, 10 ** 9, 3.7, True, {"n": 1}])
def test_a_nonsense_number_behaves_like_an_absent_one(live, limit):
    """`int(payload["limit"])` raises on most of these, which the layer above turns into a 500 — an
    internal-error status for what is really a bad argument, every time an agent guesses a field wrong."""
    status, body = call(live, "/files/list", token=live["token"],
                        body={"path": str(live["docs"]), "limit": limit})
    assert status == 200 and isinstance(body["entries"], list)


def test_a_caller_cannot_raise_its_own_read_cap(live):
    """The cap exists so one request cannot pull a huge file through the relay. A caller that could name its own
    number would not be capped at all."""
    from daemon.fs.entries import MAX_READ_BYTES
    status, body = call(live, "/files/read", token=live["token"],
                        body={"path": str(live["docs"] / "note.txt"), "max_bytes": MAX_READ_BYTES * 100})
    assert status == 200 and len(body["text"]) <= MAX_READ_BYTES


# ── the admission decision, as a pure function ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("peer,expected", [
    ("127.0.0.1", True), ("127.0.0.53", True), ("::1", True), ("::ffff:127.0.0.1", True),
    ("192.168.1.40", False), ("10.0.0.2", False), ("8.8.8.8", False), ("", False), ("localhost", False),
])
def test_only_this_machine_counts_as_loopback(peer, expected):
    """Belt to the bind's braces. If the bind address is ever widened by accident — an env var, a well-meaning
    "make it reachable from my phone" patch — this is what still refuses the LAN."""
    from daemon.security import guards
    assert guards.is_loopback(peer) is expected


def test_a_caller_from_the_network_is_refused_whatever_else_it_carries():
    from daemon.security import guards
    verdict = guards.admit(method="GET", path="/health", headers={"Host": "127.0.0.1:45817"},
                           peer_ip="192.168.1.40", port=45817, expected_token="t",
                           public_paths=frozenset({"/health"}), has_body=False)
    assert not verdict.ok and verdict.reason.startswith("off_machine")


def test_a_daemon_that_cannot_read_its_own_token_serves_nothing():
    """Serving files with an empty expected token would be serving them with no authentication at all — and an
    empty string compares equal to an empty bearer, so failing OPEN here is one typo away."""
    from daemon.security import guards
    verdict = guards.admit(method="POST", path="/files/read", headers={"Host": "127.0.0.1:45817",
                                                                      "Authorization": "Bearer "},
                           peer_ip="127.0.0.1", port=45817, expected_token="",
                           public_paths=frozenset({"/health"}), has_body=False)
    assert not verdict.ok and verdict.reason == "no_local_token"


# ── the never-served list ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/home/u/Docs/.env", "/home/u/Docs/.env.production",           # a project has three of these, not one
    "/home/u/Docs/project/.git/config",                            # a remote URL can carry a token
    "/home/u/Docs/vault.kdbx", "/home/u/Docs/work.ovpn",
    "/home/u/Library/Cookies/Cookies.binarycookies",               # session tokens for every site
    "/home/u/Docs/Chrome/Default/Login Data",
    "/home/u/.bash_history", "/home/u/Docs/.zsh_history",          # people paste tokens into terminals
    "/home/u/Docs/.aws/credentials", "/home/u/Docs/secrets/api.txt",
    "/home/u/Docs/key.pem", "/home/u/Docs/id_ed25519", "/home/u/Docs/id_rsa.pub",
    "/home/u/Docs/.npmrc", "/home/u/Docs/.pgpass",
])
def test_a_secret_is_refused_by_its_name(path):
    from daemon.security import denylist
    assert denylist.reason_for(Path(path)) is not None, f"{path} is served"


@pytest.mark.parametrize("path", [
    "/home/u/Docs/invoice.pdf", "/home/u/Docs/notes.md", "/home/u/Docs/private/diary.txt",
    "/home/u/Docs/environment-report.txt", "/home/u/Docs/keys-to-the-city.txt",
    "/home/u/Docs/project/src/main.py", "/home/u/Docs/.gitignore", "/home/u/Docs/photo.jpeg",
])
def test_an_ordinary_document_is_not(path):
    """The direction that gets forgotten. `private/` in particular is an ordinary English word and a folder real
    people really have — refusing it inside a folder they granted would be the broken-product failure."""
    from daemon.security import denylist
    assert denylist.reason_for(Path(path)) is None, f"{path} was refused"


def test_the_match_survives_a_change_of_case_or_unicode_form():
    """macOS filesystems are case-insensitive and store names decomposed, so `.SSH` and a composed spelling of
    the same name are the SAME FILE to the operating system and must be the same name here."""
    from daemon.security import denylist
    assert denylist.reason_for(Path("/home/u/.SSH/id_rsa")) is not None
    assert denylist.reason_for(Path("/home/u/Docs/KEY.PEM")) is not None


@pytest.mark.parametrize("raw,shape", [
    ("C:\\Docs\\notes.txt:hidden", "stream"),
    ("\\\\server\\share\\payroll.xlsx", "share"),
    ("C:\\Docs\\NUL", "device"),
    ("/home/u/Docs/COM1", "device"),
])
def test_windows_syntax_that_reaches_past_a_name_is_refused(raw, shape, monkeypatch):
    """After resolution these are invisible: an alternate data stream keeps the visible filename, so every name
    check sees `notes.txt` while the read returns the stream instead of the file."""
    from daemon.security import denylist
    if shape in ("stream", "share"):
        monkeypatch.setattr(denylist.os, "name", "nt")
    assert denylist.windows_reason(raw) is not None


def test_an_ordinary_windows_path_is_not_mistaken_for_one(monkeypatch):
    """`C:` is a drive, not a stream. The counterweight without which the rule refuses every path on Windows."""
    from daemon.security import denylist
    monkeypatch.setattr(denylist.os, "name", "nt")
    assert denylist.windows_reason("C:\\Users\\u\\Documents\\report.docx") is None


# ── folders that are never "the user's documents" ─────────────────────────────────────────────────────────

def test_granting_the_whole_home_folder_is_refused(tmp_path, monkeypatch):
    """A name list is not a boundary. Home holds thousands of things that are not on it — app databases, mail
    stores, local storage — so granting it is granting the machine minus a list, which is not what the user
    thinks they are agreeing to."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg, permissions
    dcfg.reset_cache()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: home))
    with pytest.raises(permissions.Refusal) as e:
        permissions.grant(str(home))
    assert e.value.code == "too_broad" and "home" in e.value.message.lower()
    dcfg.reset_cache()


@pytest.mark.skipif(os.name == "nt", reason="POSIX system paths")
def test_granting_a_system_folder_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg, permissions
    dcfg.reset_cache()
    with pytest.raises(permissions.Refusal) as e:
        permissions.grant("/etc")
    assert e.value.code == "too_broad"
    dcfg.reset_cache()


def test_a_real_folder_inside_home_is_still_grantable(tmp_path, monkeypatch):
    """The counterweight: the rule refuses the CONTAINER, never the folders the wizard exists to offer."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg, permissions
    dcfg.reset_cache()
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: home))
    assert permissions.grant(str(home / "Documents")) == [str((home / "Documents").resolve())]
    dcfg.reset_cache()


# ── a pipe is not a document ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipes")
def test_reading_a_named_pipe_is_refused_instead_of_hanging(tmp_path, monkeypatch):
    """MEASURED with the guard removed, on macOS: the read does not hang, it returns an EMPTY STRING — so the
    agent is handed a document that looks blank and reports the file as empty. That is the quieter of the two
    harms and the one that actually happened here; the loud one is real elsewhere, since a blocking read on a
    pipe whose writer never writes, or on a character device, does not come back at all, and the thread it is
    on is a thread the daemon never gets again. The open uses O_NONBLOCK so the descriptor can be inspected
    before anybody tries either."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg, files, permissions
    dcfg.reset_cache()
    docs = tmp_path / "Docs"
    docs.mkdir()
    os.mkfifo(docs / "pipe")
    dcfg.save({"roots": [str(docs)], "configured": True})

    with pytest.raises(permissions.Refusal) as e:
        files.read_file(str(docs / "pipe"))
    assert e.value.code == "not_a_file"
    dcfg.reset_cache()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipes")
def test_a_search_walks_past_a_pipe_instead_of_stopping_on_it(tmp_path, monkeypatch):
    """The counterweight that matters more than the refusal: one odd file in a folder must not cost the user
    the whole search."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg, files
    dcfg.reset_cache()
    docs = tmp_path / "Docs"
    docs.mkdir()
    os.mkfifo(docs / "report-pipe")
    (docs / "report-real.txt").write_text("findable", encoding="utf-8")
    dcfg.save({"roots": [str(docs)], "configured": True})

    out = files.search("report", raw_path=str(docs), content=True)
    assert any(h["name"] == "report-real.txt" for h in out["hits"])
    dcfg.reset_cache()


# ── the descriptor really is the file the circuit approved ────────────────────────────────────────────────

@pytest.mark.skipif(sys.platform not in ("darwin",) and not sys.platform.startswith("linux"),
                    reason="the kernel only names an open descriptor's path on macOS and Linux")
def test_the_kernel_confirms_where_an_open_descriptor_points(tmp_path):
    """The check that closes the window `O_NOFOLLOW` cannot: a directory swapped in the MIDDLE of the path is
    invisible to a flag that only looks at the last component. If this ever returns None on a supported
    platform, the third guard has silently stopped running."""
    from daemon.fs.safeopen import real_path_of
    target = tmp_path / "thing.txt"
    target.write_text("x", encoding="utf-8")
    fd = os.open(target, os.O_RDONLY)
    try:
        assert real_path_of(fd) is not None
        assert Path(real_path_of(fd)).resolve() == target.resolve()
    finally:
        os.close(fd)


def test_an_ordinary_read_still_goes_through_the_hardened_open(tmp_path, monkeypatch):
    """The direction that would have caught an over-strict verification: every one of these guards sits on the
    only path a legitimate read takes."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg, files
    dcfg.reset_cache()
    docs = tmp_path / "Docs"
    docs.mkdir()
    (docs / "a.txt").write_text("readable", encoding="utf-8")
    dcfg.save({"roots": [str(docs)], "configured": True})
    assert files.read_file(str(docs / "a.txt"))["text"] == "readable"
    dcfg.reset_cache()


# ── the state on disk ─────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes; Windows inherits the per-user ACL instead")
def test_the_audit_log_is_as_private_as_the_token_beside_it(tmp_path, monkeypatch):
    """A list of every path the agent opened is a map of the user's life. The log of what was protected must not
    be the thing that leaks."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import audit
    from daemon.paths import audit_file
    audit.record("test.op", outcome="ok")
    assert (audit_file().stat().st_mode & 0o777) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_the_state_directory_does_not_list_to_other_users(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon.paths import state_dir
    assert stat.S_IMODE(state_dir().stat().st_mode) == 0o700


def test_the_token_can_be_replaced_without_losing_the_allowlist(tmp_path, monkeypatch):
    """A credential with no way to replace it is a credential you cannot respond to. The workaround people find
    on their own is deleting the config, which throws away every folder they chose along with the secret."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg
    dcfg.reset_cache()
    docs = tmp_path / "Docs"
    docs.mkdir()
    dcfg.save({"roots": [str(docs)], "configured": True})
    before = dcfg.token()
    after = dcfg.rotate_token()
    assert after != before and len(after) >= 32
    assert dcfg.load()["roots"] == [str(docs)]
    dcfg.reset_cache()


def test_a_truncated_token_on_disk_is_replaced_rather_than_trusted(tmp_path, monkeypatch):
    """A SHORT token is worse than a missing one: it looks configured and is guessable. A file edited by hand,
    or torn by a crash, is exactly how one appears."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg
    from daemon.paths import config_file
    dcfg.load()
    config_file().write_text(json.dumps({"token": "abc", "roots": []}), encoding="utf-8")
    dcfg.reset_cache()
    assert len(dcfg.load()["token"]) >= 32
    dcfg.reset_cache()


# ── the shape of the package itself ───────────────────────────────────────────────────────────────────────

def test_the_fs_package_does_not_shadow_its_own_submodules():
    """This cost a boot. `fs/__init__.py` re-exported the FUNCTION `roots` over the SUBMODULE of the same name,
    so `from daemon.fs import roots` handed a function to code that wanted the module — and it does not fail at
    import, it fails on the first attribute access, in whichever file happened to write the shorter import."""
    import daemon.fs as fs
    for name in ("roots", "listing", "reading", "searching", "safeopen", "entries", "refusal"):
        assert isinstance(getattr(fs, name), types.ModuleType), (
            f"daemon.fs.{name} is not the submodule any more — something re-exported a name over it"
        )


def test_nothing_in_the_fs_package_can_write_to_the_users_disk():
    """The irreversible half is a later phase, behind its own confirmation. This asserts the ABSENCE, because a
    write that appeared by accident would pass every other test in the suite — they all only ever read.

    Scanned over the whole package rather than one file, and that is the point: the old version read
    `files.py`, which is now a re-export shim. A shim has no write path by construction, so the check would have
    gone on passing while the real code grew one."""
    package = Path(__file__).resolve().parents[4] / "daemon" / "fs"
    forbidden = ("write_text", "write_bytes", "unlink", "rmtree", "os.remove", "os.mkdir", "os.rename",
                 "os.replace", "shutil.")
    offenders = []
    for module in sorted(package.rglob("*.py")):
        source = module.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                offenders.append(f"{module.name}: {token}")
        if '"w"' in source or "'w'" in source or '"a"' in source or "'a'" in source:
            offenders.append(f"{module.name}: opened something for writing")
    assert not offenders, f"the read-only half of the daemon can write: {offenders}"
