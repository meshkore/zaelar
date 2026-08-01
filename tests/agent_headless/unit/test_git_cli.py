#
# Puente git acotado (V2-076). Run: .venv/bin/pytest nucleo/test_git_cli.py -q
#
# Lo CRÍTICO de seguridad: el dev worker (que puede servir a una charla agente-agente) solo puede tocar el repo
# AUTORIZADO por el operador; cualquier otro repo o la ausencia de autorización se RECHAZA. Se prueban las guardas
# sin red (no clonan de verdad).
#
from nucleo import git_cli


class _NS:
    def __init__(self, **kw): self.__dict__.update(kw)


def test_clone_refused_without_authorized_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("ZAELAR_ALLOWED_REPO", raising=False)
    called = {"run": False}
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: called.__setitem__("run", True) or 0)
    rc = git_cli.cmd_clone(_NS(dir=str(tmp_path / "wd"), repo=""))
    assert rc == 2 and called["run"] is False            # sin repo autorizado → NO ejecuta git


def test_clone_refuses_non_allowlisted_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    called = {"run": False}
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: called.__setitem__("run", True) or 0)
    rc = git_cli.cmd_clone(_NS(dir=str(tmp_path / "wd"), repo="atacante/otro-repo"))
    assert rc == 2 and called["run"] is False            # repo distinto al autorizado → RECHAZADO


def test_clone_allows_authorized_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    seen = {}
    monkeypatch.setattr(git_cli, "_run", lambda args, cwd=None: seen.__setitem__("args", args) or 0)
    rc = git_cli.cmd_clone(_NS(dir=str(tmp_path / "wd"), repo="meshkore/algo"))
    assert rc == 0 and "git" in seen["args"][0] and "meshkore/algo" in " ".join(seen["args"])


def test_push_refused_without_authorized_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("ZAELAR_ALLOWED_REPO", raising=False)
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: 0)
    assert git_cli.cmd_push(_NS(dir=str(tmp_path))) == 2


def test_commit_refuses_non_git_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: 0)
    assert git_cli.cmd_commit(_NS(dir=str(tmp_path), message="x")) == 2   # no hay .git → falla limpio


# --- Hallazgo P0 (auditoría 2026-07-26): commit/push deben RE-VERIFICAR el origin real, no solo que exista .git ---

def test_commit_refuses_dir_with_wrong_origin(monkeypatch, tmp_path):
    """El caso crítico: `dir` ES un repo git (p.ej. un clon de OTRO repo, o el propio repo del motor) pero su
    `origin` NO es el autorizado — antes se aceptaba con solo comprobar que `.git` existiera."""
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cli, "_origin_url", lambda d: "https://github.com/atacante/otro.git")
    called = {"run": False}
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: called.__setitem__("run", True) or 0)
    rc = git_cli.cmd_commit(_NS(dir=str(tmp_path), message="x"))
    assert rc == 2 and called["run"] is False


def test_push_refuses_dir_with_wrong_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cli, "_origin_url", lambda d: "")   # origin reescrito/ausente
    called = {"run": False}
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: called.__setitem__("run", True) or 0)
    rc = git_cli.cmd_push(_NS(dir=str(tmp_path)))
    assert rc == 2 and called["run"] is False


def test_commit_and_push_allowed_with_matching_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cli, "_origin_url", lambda d: "https://github.com/meshkore/algo.git")
    seen = []
    monkeypatch.setattr(git_cli, "_run", lambda args, cwd=None: seen.append(args) or 0)
    assert git_cli.cmd_commit(_NS(dir=str(tmp_path), message="x")) == 0
    assert git_cli.cmd_push(_NS(dir=str(tmp_path))) == 0
    assert any("push" in a for a in seen)
