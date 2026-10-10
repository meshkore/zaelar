"""Each install issues its OWN certificate for local.zaelar.com — no key ships in the repo (2026-10-10).

Until that day every self-hosted install presented the same Let's Encrypt certificate, and its private key was
committed to the public repo. The key left the repo in the privacy purge; `scripts/tls_cert.py` replaces it with
a per-install certificate issued by mkcert's local CA. The decision has three outcomes and each one is pinned
here, with mkcert mocked (it is not installed on CI, and the real one would touch the trust store):

  · the pair is there and current → use it, run nothing;
  · it is missing (or expired) and mkcert is installed → issue one for local.zaelar.com, localhost, 127.0.0.1;
  · it is missing and there is no mkcert → HTTP only, and ONE line that says how to enable HTTPS.

And the guard that matters most for a public repo: whatever the launcher writes there is gitignored.

Run: .venv/bin/pytest tests/infrastructure/unit/test_each_install_issues_its_own_certificate.py -q
"""
import importlib.util
import subprocess
import types
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("tls_cert", ENGINE / "scripts" / "tls_cert.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)


def _pair(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "fullchain.pem").write_text("cert")
    (d / "privkey.pem").write_text("key")


class _FakeMkcert:
    """Records every call; `-cert-file X -key-file Y` writes X and Y like the real one."""

    def __init__(self, caroot: Path | None = None, rc: int = 0):
        self.calls: list[list[str]] = []
        self.caroot, self.rc = caroot, rc

    def __call__(self, cmd, **_kw):
        self.calls.append(list(cmd))
        if cmd[1:] == ["-CAROOT"]:
            return types.SimpleNamespace(returncode=0, stdout=str(self.caroot or ""), stderr="")
        if self.rc == 0 and "-cert-file" in cmd:
            Path(cmd[cmd.index("-cert-file") + 1]).write_text("cert")
            Path(cmd[cmd.index("-key-file") + 1]).write_text("key")
        return types.SimpleNamespace(returncode=self.rc, stdout="", stderr="boom" if self.rc else "")


def _never_run(*_a, **_k):
    raise AssertionError("nothing may be run when the decision is `use` or `http-only`")


def test_a_present_current_pair_is_used_and_nothing_runs(tmp_path):
    _pair(tmp_path)
    said: list[str] = []
    out = T.ensure(str(tmp_path), which=lambda _n: "/usr/bin/mkcert", run=_never_run, say=said.append,
                   expired=lambda _f: False)
    assert out == T.USE and said == []


def test_missing_pair_with_mkcert_issues_one_for_the_three_names(tmp_path):
    caroot = tmp_path / "ca"
    caroot.mkdir()
    (caroot / "rootCA.pem").write_text("ca")
    d = tmp_path / "certs"
    fake = _FakeMkcert(caroot)
    said: list[str] = []
    out = T.ensure(str(d), which=lambda _n: "/opt/mkcert", run=fake, say=said.append)
    assert out == T.USE
    issue = [c for c in fake.calls if "-cert-file" in c]
    assert len(issue) == 1
    assert issue[0][-3:] == ["local.zaelar.com", "localhost", "127.0.0.1"]
    assert (d / "fullchain.pem").is_file() and (d / "privkey.pem").is_file()
    assert not any("-install" in c for c in fake.calls), "mkcert -install touches the trust store: the user's call"
    assert not any("mkcert -install" in s for s in said), "the CA is installed: no hint needed"


def test_an_uninstalled_local_ca_still_issues_and_says_to_install_it(tmp_path):
    fake = _FakeMkcert(caroot=tmp_path / "empty-ca")      # no rootCA.pem there
    said: list[str] = []
    assert T.ensure(str(tmp_path / "c"), which=lambda _n: "mkcert", run=fake, say=said.append) == T.USE
    assert any("mkcert -install" in s for s in said)
    assert not any("-install" in c for c in fake.calls)


def test_an_expired_pair_is_reissued(tmp_path):
    _pair(tmp_path)
    fake = _FakeMkcert(tmp_path)
    assert T.decide(str(tmp_path), "mkcert", expired=lambda _f: True) == T.GENERATE
    T.ensure(str(tmp_path), which=lambda _n: "mkcert", run=fake, say=lambda _s: None, expired=lambda _f: True)
    assert any("-cert-file" in c for c in fake.calls)


def test_missing_pair_without_mkcert_is_http_only_with_one_hint(tmp_path):
    said: list[str] = []
    out = T.ensure(str(tmp_path / "none"), which=lambda _n: None, run=_never_run, say=said.append)
    assert out == T.HTTP_ONLY
    assert len(said) == 1 and "mkcert -install" in said[0] and "http://localhost:43917" in said[0]
    assert not (tmp_path / "none" / "privkey.pem").exists()


def test_a_failed_mkcert_falls_back_to_http_only(tmp_path):
    said: list[str] = []
    out = T.ensure(str(tmp_path / "c"), which=lambda _n: "mkcert", run=_FakeMkcert(rc=1), say=said.append)
    assert out == T.HTTP_ONLY and any("mkcert failed" in s for s in said)


def test_the_generated_pair_is_gitignored():
    """The launcher writes a PRIVATE KEY into the checkout; a public repo must never pick it up."""
    for name in ("fullchain.pem", "privkey.pem"):
        rel = f"certs/local.zaelar.com/{name}"
        r = subprocess.run(["git", "-C", str(ENGINE), "check-ignore", "-q", "--no-index", rel])
        assert r.returncode == 0, f"{rel} is not gitignored"
        tracked = subprocess.run(["git", "-C", str(ENGINE), "ls-files", "--error-unmatch", rel],
                                 capture_output=True)
        assert tracked.returncode != 0, f"{rel} is TRACKED — a private key in the public repo"


def test_the_server_and_the_launcher_agree_on_the_cert_dir_and_names():
    """The server only reads the pair; if the two drift, HTTPS silently never comes up."""
    server = (ENGINE / "server" / "__main__.py").read_text(encoding="utf-8")
    assert '"ZAELAR_TLS_CERT_DIR"' in server and '"local.zaelar.com"' in server
    assert f'"{T.CERT_NAME}"' in server and f'"{T.KEY_NAME}"' in server
    assert Path(T.DEFAULT_DIR) == ENGINE / "certs" / "local.zaelar.com"
