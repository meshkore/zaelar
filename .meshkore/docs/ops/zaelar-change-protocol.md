---
title: Zaelar Change Protocol
category: ops
updated: 2026-07-09
owner: ricart
status: current
---

# Zaelar change protocol — "run the protocol"

**Trigger:** when the operator says **"run the protocol"** (or "pasa el protocolo", "close the change"), the
agent runs THIS checklist end to end for the change it has just made. The point is not having to remember,
every time, what closing a major change involves.

> Scope: applies to **major changes** (new feature, systemic fix, change of structure/decision).
> A typo or a trivial tweak only needs a commit; the operator will say if he wants the full protocol.

---

## Checklist (in order)

### 1. Restart the system and check its health
- `make run` (= `BRAIN=nucleo`, the default brain) after stopping the previous instance on `:43917`.
- Check: `curl -sf localhost:43917/api/brain` answers, and the log shows the brain starting with no errors.
- The change must be **loaded and running** before it is called good.

### 2. Verify the change
- Run whichever verification applies: `make test`, `make smoke`, or a targeted repro against the real binary
  (e.g. the barge-in harness). A change is **not** closed without evidence that it does what it says.
- If it touches voice: remember that **voice in/out is only the interface** — the brain's conversation must
  stay coherent and two-way. See the key decisions in `CLAUDE.md`.

### 3. Bump the version (semver)
- Product version in `.meshkore/public/cluster.yaml` → the `version:` field.
- `fix` → PATCH · `feat` → MINOR · breaking/structural → MAJOR (while <1.0, MINOR for features).
- Tag the commit: `git tag vX.Y.Z`.

### 4. Document it in the MeshKore standard
- **Work log** (mandatory): one entry per touched module in the module's local log folder, with front matter
  (`id, title, status, priority, owner, initiative, created, updated`) + body (What was done · Files touched ·
  Verification).
- **Initiative**: anchor the task to an initiative in the local planning folder (MeshKore standard §24); for new
  work, create one. Update the affected initiative's `status`/`updated`.
- **Do NOT** edit the daemon-generated planning state by hand.
- **Canonical context** (`.meshkore/docs/<category>/`): update ONLY if the change introduced decisions,
  criteria, settings or structural changes. Categories: architecture, product, ops, conventions, modules,
  security. A new module is declared in `cluster.yaml`.
- **`.meshkore/docs/criteria.md`**: add a line only if a standing rule changed.
- **Memory**: save anything non-obvious (symptom→cause→invariant) as `feedback`/`project` so the mistake is not
  repeated.

### 5. Commit
- Descriptive message (`feat:`/`fix:`/`refactor:`/`docs:` …), with a body explaining the why.
- Code **and** documentation go in the same change closure.
- End with the trailers required by `CLAUDE.md`.

### 6. Push
- Follow the push policy in `CLAUDE.md` and `cluster.yaml`.
- Remote: `origin` (github.com:asimovia/zaelar): `git push origin main --tags`.

---

## Summary for the operator (at the end)
Report one line per item: what was done, what was verified, which version, what was documented, and what is
**waiting on his decision**.
