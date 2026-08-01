#
# Guard de confinamiento REAL del dev-worker (V2-076, auditoría 2026-07-26). Run:
# .venv/bin/pytest nucleo/test_dev_worker_guard.py -q
#
# Antes de este fix, Read/Write/Edit del dev-worker solo estaban "confinados" por una instrucción de prompt — un
# bug/prompt-injection podía leer fuera del cwd temporal. Este módulo es un hook PreToolUse real: lo crítico de
# seguridad es que `check()` deniegue cualquier ruta fuera de ZAELAR_DEV_WORKER_ROOT, para las tools con campo de
# ruta, y sea FAIL-OPEN (nunca tumba un worker legítimo) ante entradas raras.
#
import json
import os

from nucleo import dev_worker_guard as guard


def test_no_root_configured_allows_everything(monkeypatch):
    monkeypatch.delenv(guard._ROOT_ENV, raising=False)
    assert guard.check({"tool_name": "Read", "tool_input": {"file_path": "/etc/passwd"}}) is True


def test_read_inside_root_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv(guard._ROOT_ENV, str(tmp_path))
    f = tmp_path / "repo" / "main.py"
    f.parent.mkdir()
    f.write_text("x = 1")
    assert guard.check({"tool_name": "Read", "tool_input": {"file_path": str(f)}}) is True


def test_read_outside_root_denied(tmp_path, monkeypatch):
    monkeypatch.setenv(guard._ROOT_ENV, str(tmp_path / "workdir"))
    (tmp_path / "workdir").mkdir()
    secret = tmp_path / ".env"
    secret.write_text("API_KEY=xxx")
    assert guard.check({"tool_name": "Read", "tool_input": {"file_path": str(secret)}}) is False


def test_write_outside_root_denied(tmp_path, monkeypatch):
    monkeypatch.setenv(guard._ROOT_ENV, str(tmp_path / "workdir"))
    (tmp_path / "workdir").mkdir()
    target = tmp_path / "elsewhere" / "evil.py"
    assert guard.check({"tool_name": "Write", "tool_input": {"file_path": str(target)}}) is False


def test_relative_path_resolved_against_cwd(tmp_path, monkeypatch):
    root = tmp_path / "workdir"
    root.mkdir()
    monkeypatch.setenv(guard._ROOT_ENV, str(root))
    # ruta relativa "../../etc/passwd" desde el cwd DEL PROCESO (que el payload declara) — debe resolverse y
    # detectarse como fuera del root, no colarse por ser "relativa".
    assert guard.check({"tool_name": "Read", "cwd": str(root),
                        "tool_input": {"file_path": "../fuera.txt"}}) is False


def test_symlink_escape_denied(tmp_path, monkeypatch):
    root = tmp_path / "workdir"
    root.mkdir()
    monkeypatch.setenv(guard._ROOT_ENV, str(root))
    secret = tmp_path / "secret.txt"
    secret.write_text("s3cr3t")
    link = root / "sneaky"
    link.symlink_to(secret)
    # realpath() sigue el symlink → se resuelve fuera del root aunque el PATH nominal esté dentro.
    assert guard.check({"tool_name": "Read", "tool_input": {"file_path": str(link)}}) is False


def test_glob_grep_path_field_checked(tmp_path, monkeypatch):
    root = tmp_path / "workdir"
    root.mkdir()
    monkeypatch.setenv(guard._ROOT_ENV, str(root))
    assert guard.check({"tool_name": "Glob", "tool_input": {"path": str(tmp_path)}}) is False
    assert guard.check({"tool_name": "Grep", "tool_input": {"path": str(root)}}) is True


def test_glob_without_path_field_allowed_by_default(tmp_path, monkeypatch):
    # Glob/Grep sin `path` explícito buscan desde el cwd de la tool (ya confinado por el propio CLI) — el guard
    # no tiene nada que comprobar y no debe bloquear el uso normal.
    monkeypatch.setenv(guard._ROOT_ENV, str(tmp_path))
    assert guard.check({"tool_name": "Glob", "tool_input": {"pattern": "*.py"}}) is True


def test_unrelated_tool_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv(guard._ROOT_ENV, str(tmp_path))
    assert guard.check({"tool_name": "Bash", "tool_input": {"command": "python -m nucleo.git_cli clone repo"}}) is True


def test_main_fail_open_on_malformed_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("not json {{{"))
    rc = guard.main()
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == {}     # {} = allow (sin hookSpecificOutput) — fail-open


def test_main_denies_and_emits_reason(tmp_path, monkeypatch, capsys):
    root = tmp_path / "workdir"
    root.mkdir()
    monkeypatch.setenv(guard._ROOT_ENV, str(root))
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "secret.txt")}}
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    rc = guard.main()
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "secret.txt" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_settings_dict_shape():
    d = guard.settings_dict(python_exe="/usr/bin/python3")
    hooks = d["hooks"]["PreToolUse"][0]
    assert "Read" in hooks["matcher"] and "Write" in hooks["matcher"]
    assert hooks["hooks"][0]["type"] == "command"
    assert "nucleo.dev_worker_guard" in hooks["hooks"][0]["command"]
    assert "/usr/bin/python3" in hooks["hooks"][0]["command"]


def test_write_settings_file_roundtrips(tmp_path):
    p = str(tmp_path / "settings.json")
    guard.write_settings_file(p, python_exe="/usr/bin/python3")
    assert os.path.exists(p)
    with open(p) as fh:
        loaded = json.load(fh)
    assert loaded == guard.settings_dict(python_exe="/usr/bin/python3")
