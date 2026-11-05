---
title: Zaelar Docs & Structure Sync
category: ops
updated: 2026-07-02
owner: ricart
status: current
---

# Docs and structure sync workflow — "sync the documentation"

**Trigger:** runs **automatically** whenever a change touches the project's **structure** or its
**documentation/context** — and on demand when the operator says *"sync the documentation"* / *"run the docs
sync"*. The goal: the documentation, the context (`CLAUDE.md`), the architecture (including its diagram) and
what someone cloning the repo reads (`README.md`) **never fall behind** the code. It codifies these
instructions so they do not have to be repeated each time.

> Complements [[zaelar-change-protocol]] (which closes **one** change) and [[zaelar-audit-workflow]] (which
> audits the **whole** system). This is the **docs↔structure coherence** step that runs INSIDE the change
> protocol (its step 4) and can also be run on its own.

---

## 0. When it applies (does my change touch structure or docs?)

It applies if the change does ANY of these:
- adds/renames/moves a **module or folder**, or changes the root layout;
- adds a **dependency or install step** (something someone would have to install/configure);
- introduces a new **decision, invariant, security policy or setting**;
- changes a **flow** that is already drawn in a diagram or described in a canonical doc;
- adds/removes a relevant **route, endpoint, env var or command**.

If it touches none of these (e.g. an internal fix with no observable effect), this workflow is not needed.

## 1. Guiding principle: cross-platform, tied to nobody

zaelar must run on **macOS, Windows and Linux**. When documenting installation or commands:
- give the command **per OS** when it differs (e.g. `make install-stt` on mac vs `scripts/*.ps1` on Windows);
- do not assume `brew`/`apt`/`bash` are universal — mark them as OS-specific and offer the alternative;
- providers (STT/TTS/brain) are **interchangeable** through env/config: never hardcode a vendor in the docs.

## 2. Sync checklist (tick everything that applies)

| If the change… | Update |
|---|---|
| adds/removes/moves a module or folder | `.meshkore/public/cluster.yaml` (modules) · `CLAUDE.md` (§Modules/layout) · `.meshkore/docs/modules/zaelar-modules.md` · the **diagram** in `.meshkore/docs/architecture/zaelar-architecture.md` |
| adds a dependency or install step | **`README.md`** (root, per OS) · `.meshkore/docs/ops/zaelar-ops.md` (§Prerequisites + the relevant section) |
| introduces a decision/invariant | `.meshkore/docs/criteria.md` · the matching category doc (architecture/product/security/…) |
| touches security (cluster channel, permissions, secrets) | `.meshkore/docs/security/zaelar-security.md` · the trust-boundaries subsection of `zaelar-architecture.md` · `CLAUDE.md` |
| changes a flow that is already drawn | the matching **ASCII diagram** in `zaelar-architecture.md` (never leave the drawing stale) |
| adds a route/endpoint/env/command | the doc that describes it (ops/architecture) · `config/.env.example` if it is an env var |
| changes the structure, commands, suites, catalogue or protocol of testing | `tests/README.md` · `.meshkore/docs/ops/zaelar-testing.md` · `tests/TESTMAP.md`/`tests/platform/SCHEMA.md` as appropriate · `CLAUDE.md` and `AGENTS.md` if what agents must do changes |
| **touches the FlashBrain TOOL catalogue** (`nucleo/flash/router.py::TOOLS`: adds/removes/renames a tool, changes its description or gating) | the **canonical doc `zaelar-architecture.md §8`** (single source) · the public diagram `/technology/flashbrain`, outside this repo (only if the change matters to an outside reader — a MANUAL step) · `tests/agent_headless/unit/flash/test_router.py` · re-check the contextual gating in `nucleo/turn/pipeline.py` (the one turn, both channels) · `CLAUDE.md` if a rule changes. Every tool must be JUSTIFIED and fit the turn flow (no dead/stale entries). |
| is visible to someone cloning the repo | **`README.md`** (whenever what to install/how to start changes) |

## 3. Golden rule: "it appears in all three places"

Every concept that matters must be findable in: **(a) the context** (`CLAUDE.md` / `criteria.md`), **(b) the
canonical documentation** (`.meshkore/docs/<category>/`), and **(c) the architecture** (`zaelar-architecture.md`,
including its diagram if the concept is structural or about a flow). If something is only in the code, it is
not documented.

For testing, the same rule takes four layers without duplicating instructions: `CLAUDE.md`/`AGENTS.md` route the
agent, `tests/README.md` gives the operational contract, `zaelar-testing.md` explains the deep diagnosis and
`tests/platform/SCHEMA.md` fixes the machine contract. A change to the test platform must keep all four coherent.

## 4. Verification

- **Links**: new `[text](path)` links resolve (correct relative paths). No dangling references in the
  canonical-docs table of `CLAUDE.md`.
- **Code↔doc coherence**: what the doc says matches the code (real file/env/command names).
- **Cross-platform**: every install instruction has its per-OS variant or says explicitly that it is specific
  to one.
- Then continue with [[zaelar-change-protocol]] (version → log/initiative → commit → push where applicable).

## 5. Summary for the operator
One line: what was synced (README/CLAUDE/architecture/diagram/category docs), and what is left open.
