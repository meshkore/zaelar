"""
THE REPO ROOT DOES NOT STORE DATA — this repo is PUBLIC, and personal information escaped through here.

REAL LEAK (2026-08-12, found during a session reviewing loose files). `informe.json` was not merely uncommitted:
it was **versioned**, twice (816efd7, 8a959b8), and the copy remaining in HEAD was not an example — it was the
operator's vacation report with the travel dates, the budget, and the **ages of their children**.
In the public repository that anyone can clone.

The cause is structural, not an oversight: a Brain Worker writes its deliverable to a file using a **relative path
from its working directory**, and that directory is currently the engine root (`dispatch` explicitly requests this,
because writing outside it requires approval that no one will provide in headless mode). Nothing ignored it, so any
agent's `git add -A` would include it.

Ignoring the three names from that run does not close the class: the contract says «`informe.json` by itself» as an
EXAMPLE, and the next worker can call it whatever it wants. This test is the guard that does close the class — it
checks the only thing that truly matters: **that nothing ends up versioned at the root unless it is project code or
configuration**, regardless of its name or extension.

When it fails, the question is NOT “do I add this to the list?” It is: is this part of the project (→ add it to
`ALLOWED`, with a commit that justifies it), or is it a work artifact (→ it belongs in `.gitignore` or `TMP/`, never
in the repo)?
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

# What the engine root is allowed to version: project entry points, packaging, and startup. No data.
ALLOWED = {
    ".dockerignore", ".gitignore", "AGENTS.md", "CLAUDE.md", "Dockerfile", "Makefile", "README.md",
    "conftest.py", "constraints.txt", "fly.accounts.toml", "fly.toml", "requirements.txt", "ruff.toml",
    "version.py", "zaelar", "zaelar.ps1",
}


def _tracked_root_files() -> set[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ENGINE, capture_output=True, text=True, check=True).stdout
    return {line for line in out.splitlines() if line and "/" not in line}


def test_no_data_file_is_versioned_at_the_repo_root():
    extra = _tracked_root_files() - ALLOWED
    assert not extra, (
        "hay ficheros versionados en la raíz que no son del proyecto: " + ", ".join(sorted(extra))
        + ". Por aquí se colaron datos personales del operador a un repo PÚBLICO. Si es del proyecto, añádelo a "
          "ALLOWED en este test; si es un artefacto de trabajo, a .gitignore o a TMP/.")


def test_the_workers_draft_names_are_ignored():
    """The names that the `dispatch` contract suggests to the worker must be ignored TODAY, without depending on
    someone remembering later."""
    for name in ("informe.json", "fuentes.json", "resultados.json", "cualquier-cosa.json"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=ENGINE)
        assert r.returncode == 0, f"«{name}» en la raíz NO está ignorado — el próximo `git add -A` lo versiona"


def test_a_real_source_file_is_still_versionable():
    """The pattern must not be so broad that it prevents code from being versioned: if `.gitignore` started hiding
    source files, this guard would become the problem."""
    for name in ("version.py", "conftest.py", "Makefile"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=ENGINE)
        assert r.returncode != 0, f"«{name}» está ignorado y es del proyecto"
