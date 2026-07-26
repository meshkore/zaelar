#
# Dev worker acotado (V2-076, escalada de cluster con permiso de código). Run: .venv/bin/pytest nucleo/test_dev_worker.py -q
#
# La decisión de montar un dev worker es un helper PURO (testeable sin spawnear). Lo crítico de seguridad: solo se
# activa con `dev`+`repo`; sus tools son Read/Write/Edit + el PUENTE git (nunca Bash pelado); sin puentes de memoria;
# repo acotado. Sin `dev` → None → worker normal (cero regresión).
#
from nucleo import dispatch


def test_no_dev_context_returns_none():
    assert dispatch._dev_worker_params(None) is None
    assert dispatch._dev_worker_params({"src": "cluster", "trusted": False}) is None   # sin permiso de código
    assert dispatch._dev_worker_params({"dev": True}) is None                          # dev pero sin repo → None


def test_dev_context_scoped_params():
    p = dispatch._dev_worker_params({"dev": True, "repo": "meshkore/algo", "trusted": False})
    assert p is not None
    assert p["repo"] == "meshkore/algo"
    # git SOLO por el puente, nunca Bash pelado
    assert any("nucleo.git_cli" in t for t in p["tools"])
    assert not any(t == "Bash" or t.startswith("Bash(git") for t in p["tools"])
    # sin puentes de memoria + repo acotado
    assert p["env"]["ZAELAR_NO_BRIDGE_TOOLS"] == "1"
    assert p["env"]["ZAELAR_ALLOWED_REPO"] == "meshkore/algo"
    assert "PYTHONPATH" in p["env"]                          # el puente importable desde el cwd temporal


def test_dev_prompt_scopes_to_repo_and_bridge():
    pr = dispatch._dev_prompt("haz el backtester", "meshkore/algo").lower()
    assert "meshkore/algo" in pr and "git_cli" in pr
    assert "temporal" in pr or "aislada" in pr              # deja claro el aislamiento del cwd
