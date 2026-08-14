# Agent entrypoint

## Public source-language invariant

`engine/` is public. Comments, docstrings, inline explanations, and developer-facing notes must be in
English everywhere. Before adding or changing one, run `python tools/comment_language_audit.py` on the
touched path and translate any Spanish internal prose. Preserve Spanish only when it is intentional runtime
product content, localization data, or a test fixture whose purpose is to exercise Spanish behavior.

For the ongoing repository-wide migration, read
`.meshkore/docs/ops/comment-language-migration.md` first and update its ledger after each completed file.

This repository's complete engineering context is in `CLAUDE.md` and `.meshkore/`.
Read the relevant canonical document before changing a subsystem.

## Testing is part of every change

Before testing or adding tests, read **`tests/README.md`**. It is the operational contract shared by Codex,
Claude Code, humans and CI. The detailed playbook is **`.meshkore/docs/ops/zaelar-testing.md`** and the normalized
catalog contract is **`tests/platform/SCHEMA.md`**.

Hard rules:

- Tests live only under `tests/<suite>/`; do not recreate `test/`, `tester/` or scattered test roots.
- Prefer `./.venv/bin/python -m tests ...` over raw pytest so the run remains terminal-friendly and is also
  observable at the stable local URL `http://127.0.0.1:8765`.
- Preserve exit codes. A green UI or an LLM score never overrides a failed assertion.
- Use `--no-open` when acting headlessly; the Observatory server still starts so a human can watch it.
- Never test against the operator's real memory when an isolated test database/corpus is available.
- Do not run two Observatory-managed suites concurrently. Port `8765` represents one active/replayed run and
  intentionally hands off between executions.
- Do not pull/reset/checkout to "get the latest" before testing. The local working tree is the development truth.
- A new capability needs a mapped test in the owning `tests/<suite>/suite.json`; zero `unmapped` cases is the goal.
- If a change crosses domains or relies on previously created state, run `journey`; every later case rebuilds its
  causal prefix in an isolated engine. Read `tests/journey/README.md` before extending that chronology.
