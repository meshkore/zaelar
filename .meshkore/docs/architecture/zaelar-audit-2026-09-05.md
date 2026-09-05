---
title: Zaelar System Audit — 2026-09-05
category: architecture
updated: 2026-09-05
owner: ricart
status: current
audit_of: e4b5336 (v3.25, BUILD 10, clean tree)
---

# System audit — 2026-09-05

Full run of `zaelar-audit-workflow.md`: recon → parallel fan-out over the four canonical domains (A core
voice/brain/memory/bus/server · B frontend/widgets · C cluster-channel security, adversarial · D docs↔code
alignment) plus a fifth professionalization dimension (E: tooling, CI, typing, error handling, dependencies),
one subagent per domain, every claim backed by `file:line`. The security suite was executed (50/50 green,
0.74 s) and the architecture ratchet was executed (RED — see findings). Per the workflow, this audit fixes
nothing: remediation is tracked task-by-task in roadmap initiative **V2-601** (local), each task to be closed
individually with the change protocol.

> Detailed security findings (exploitation scenarios, bypass constructions) are deliberately NOT reproduced
> in this public document — they live in V2-601 with the full report. Here: control + verdict only.

## Executive summary

The system is in substantially better shape than its size suggests, and better than the previous audit
(2026-07-26): the containment mechanisms are real and bite (architecture ratchet, dependency-direction
ratchet 7.32 green with zero new edges, single-writer memory held by construction, closed observer families,
5,263+ deterministic tests at a 1.45:1 test:prod LOC ratio, 77.5% type-annotation coverage). The genuine gaps
concentrate in one theme: **the controls only work when something runs them, and no robot does** — the
architecture ratchet is red on clean main in four files and nobody saw it, there is no CI on push/PR (the
only workflow compiles on release tags), no linter or type-checker ever verifies anything, and there is no
dependency lockfile while the whole LiveKit plugin stack floats unpinned. The second theme is the known
fail-open asymmetry: the "a failure never touches the voice" policy is applied ~1,900 times in production,
but only the memory subsystem internalized the second half ("a failure never stays a warning" →
health_state); the server lifespan still degrades a failed subsystem mount to one WARNING among hundreds of
INFO lines. Legal: the repo declares itself open source with no LICENSE file and redistributes MIT-vendored
code without the upstream license text — an operator decision already pending in INI-027 §9.

## Verdict highlights by domain

**A — core (voice/nucleo/memory/bus/server):** 8 OK · 4 DRIFT · 1 BROKEN. The BROKEN is a cross-loop
`asyncio.Lock` in the memory-ingest path (`nucleo/memory_agent/ingest.py:36`) shared by the voice loop and
the probe loop — reproducibly poisons under contention and silently loses ingest writes. The V2-554
open item (create_app's broad except swallowing four routers on fatal misconfig) is confirmed still open.
`/api/cron` mounts unconditionally while the loop that fires jobs is brain-gated. Layering: 7.32 ran green,
zero undeclared new edges.

**B — frontend/widgets:** 5 OK · 5 DRIFT. All 14 widgets audited; textContent discipline holds in 12/14.
Main items: a third, client-side copy of the close-phrase rule reopens V2-600 (`services/voiceCommands.js`);
the widget generator runs with repo-root cwd (prompt-only confinement, and it ships both CLAUDE.md files —
including the private workspace one — to the external provider on every generation); the `results` widget
violates the widget contract twice and keeps `make test-widgets` permanently red; the stdlib gate can be
laundered via sibling modules. The desktop/mobile shared-by-import boundary genuinely holds.

**C — cluster security (adversarial):** defense-in-depth is real and mostly where the docs say: tools off in
code, identity-safe system, closed tag allowlist, deny-all perms with the objective double-key, fence with
forgery neutralization, trailer always last, outbound scan on both doors, fail-closed transport, flood cap
with no leak path found. Security suite 50/50. Findings are seams BETWEEN layers, not absent controls: one
P1 (a fallback path that launders peer text past neutralization into a trusted prompt block — one-line fix),
and a cluster of P2/P3 (jail fail-open stacking, dev-worker env inheritance, a rebind-residual GET, unicode
edge cases). None grants a peer direct execution; all still require model cooperation against a trailer that
goes last. Details in V2-601.

**D — docs alignment:** the exercised-daily surfaces align (9/9 sampled CLAUDE.md decisions verified against
code; roadmap alive and dated; release seal works as V2-553 mandates). Drift concentrates where no ratchet
watches: `cluster.yaml` frozen at 2.88 for 24 days with the engine at 3.25, module list stale both
directions, `models.default.json` contradicting itself about AIMLAPI, module logs abandoned. Language rule:
commits/initiatives/new code now 100% English in sample; Spanish .py backlog down from 68% (2026-08-29) to
~15-24% depending on measure; the real queue is 22/36 canonical docs. **CLAUDE.md is 886 KB growing
~21 KB/day (~210k tokens) — already impossible for any agent to load whole**, which turns the
context-that-every-agent-reads into a nondeterministic slice; needs a compaction policy before it defeats
its own purpose.

**E — professionalization (measured, not estimated):** zero lint/format/type-check config; one CI workflow
(release tags only, compileall); typing 77.5% fully annotated (server 33%, bus 32% at the low end) with no
checker; `except Exception`: 1,917 in production of which 667 pass-only and 755 silent-fallback (74% leave
no trace) — a class with ≥4 paid incidents on record; requirements 11/32 unversioned incl. all
livekit-plugins, no lockfile; 15/15 parallel-impl markers at the ratchet ceiling with the probe/voice pair
still ~2,700 vs ~1,087 lines; 4 mechanisms of logging coexisting; packaging run-in-place by design.

## Consolidated findings (index — detail in V2-601)

| Prio | Id | One line |
|---|---|---|
| P0 | T-01 | Architecture ratchet RED at HEAD (4 files over ceiling) — pay by extraction, never by raising ceilings |
| P0 | T-02 | No CI on push/PR — deterministic testmap must run automatically (root cause of T-01) |
| P0 | T-03 | No LICENSE on a self-declared open-source repo + missing MIT attribution for vendored bridge (operator decision) |
| P0 | T-04 | Widget generator: repo-root cwd → prompt-only confinement + private context sent to external provider |
| P0 | T-05 | Cluster synthesis fallback launders peer text past fence neutralization (one-line fix + test) |
| P1 | T-06 | Cross-loop asyncio.Lock in memory ingest — silent write loss under voice+probe contention |
| P1 | T-07 | Client copy of close-phrase rule reopens V2-600 ("cierra la pantalla completa" → closeAll) |
| P1 | T-08 | create_app broad except still swallows 4 routers on fatal misconfig (V2-554 open item) |
| P1 | T-09 | Dev-worker jail fail-open ×3 + inherits full operator environment |
| P1 | T-10 | results widget contract violations keep make test-widgets permanently red |
| P1 | T-11 | No lockfile; voice stack unpinned; no Python version guard |
| P1 | T-12 | Ruff F-rules + incremental mypy (catches the NameError-swallowed-by-fail-open class) |
| P1 | T-13 | /api/cron accepts jobs that can never fire when BRAIN≠nucleo |
| P1 | T-14 | Rebind-residual GET reads cluster status cross-origin |
| P2 | T-15..T-26 | NucleoLLMStream split · one house for phrase→action · silent-swallow ratchet + lifespan health_state · CLAUDE.md compaction (⚖️) · frontend size ratchet · validator gaps · cluster.yaml regen · models table contradictions · restore 109 destroyed comments · docs sync · server.* direction table · small security seams |
| P3 | T-27..T-29 | Dead files/ shim · legacy session.js/stt.js · language-backlog ratchet · stale citations & root clutter |

## Comparison with 2026-07-26 audit

Closed since then: the dev-worker jail exists as code (PreToolUse hook) and rlimits are wired; the
objective gate is applied; redaction suffixes unified; single model table (V2-500); admission allowlist
(server/ingress). Still open from then: the env-scrub half of sandbox.py; the create_app swallow (newly
documented as V2-554); the license decision. New since then: the ratchet-red/CI gap — which is also the
reason several of these were found by an audit instead of by a robot.
