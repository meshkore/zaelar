# Annex — Playbook for the 1000-STEP CYCLE (memory re-verification)

> Reusable document: how to repeat FROM SCRATCH the cycle that takes Zaelar's memory to **≥1000 verified
> requests** (STATE/SHORT/LONG + the remaining typologies), in an autonomous loop. Dated results are archived
> under `tests/memory/e2e/bot/resultados/<date>-ciclo-1000/`.

## What it tests (and why)

The **memory test-bot** (`tests/memory/e2e/bot/`) role-plays a PERSONA talking to Zaelar over a LONG
conversation and, for every step, verifies that the HUMAN-like memory does the right thing along the **REAL
path** (writing through the local LLM CORE `ingest_utterance`; reading the way the FlashBrain's `_brain_view`
does = `memory_cache._compose` + `compose_recall`, WITHOUT an LLM). It does not measure what the bot SAYS but
what the memory DOES.

**The dimensions (A–Y + Z/AA/AB/AC)** — map in `TAXONOMY.md`. Core: **STATE** (A, Y), **SHORT** (B), **LONG**
(C). The rest: dedup/supersede (D), discard/abstention (E), graph/category (F), multi-source (G), quarantine (H),
interests (I), temporal (J), scale (K), forgetting/consolidation (L), contradictions (M), privacy/forgetting (N),
routines (O), adversarial (P), cross-source (Q), multilingual (R), episodic (S), vocab-gap (T), multi-hop (U),
verbosity (V), standing instructions (W), implicit invalidation (X), and the state-of-the-art set:
memory→action (Z), anti-hallucination (AA), temporal validity/as-of (AB), cross-session identity (AC). SOTA
grounding in `RESEARCH.md`.

## How to run it

```bash
./.venv/bin/python -m tests.memory.e2e.bot.runner --coverage        # coverage per dimension (pick a gap)
./.venv/bin/python -m tests.memory.e2e.bot.runner --next 80         # advance 80 on the accumulated DB (coherent persona)
./.venv/bin/python -m tests.memory.e2e.bot.runner --fresh --range 0 <N>   # GOLD pass (clean linear replay)
./.venv/bin/python -m tests.memory.e2e.bot.runner --catalog         # regenerates CATALOG.md
```

**Two corpora:** `--corpus v1` (default) = the GOLD corpus `cases.py` (the operator persona); `--corpus v2` =
`cases2.py`, a second, unrelated persona for genericity/multi-operator coverage, plus dimensions AD–AG:
multilingual `change` signal, lineage collapse by slot alias, worker writes through `remember_external`, and
`heal_slots`. DB/progress/catalogue are ISOLATED per corpus → running one never touches the other. Extra step
types: `worker_write`, `slot_count`, `heal_slots`. `python -m …runner --corpus v2 --fresh --range 0 N`.

Requires **local Ollama** (CORE `qwen2.5:*`, embeddings `embeddinggemma`). An **ISOLATED** DB
(`memory/_data/zaelar.membot.db`, gitignored) — never the real profile. JSON report + progress in
`.meshkore/logs/membot/`. The GOLD pass is long (the dimension-K scale cases seed thousands of embeddings);
launch it with `python -u` (unbuffered) to watch progress, and check that it is not stuck on I/O (0% CPU
sleeping).

## The CYCLE (autonomous loop `/loop 10m`, ADVANCE-FIRST strategy)

Each iteration (10 min): **overlap guard** (`pgrep -f memory.bot.runner`; only ONE runner) → advance a wave of
80 (`--next 80`) → **triage ONLY that wave's ❌** → `pytest -k memory` green → commit → entry in the tester's
log. Once `done_upto ≥ corpus` it switches to **GOLD MODE**: `--fresh --range 0 <N>` in the background, triage
its report, RE-launch, until **0 ❌** → deliverables + STOP the loop.

**Do NOT re-verify prefixes after each wave** (the LLM writer is non-deterministic, so a small share of cases
flip-flop between fresh runs; re-verifying in a loop would just churn).

### Classifying each ❌ (the key decision)

- **(a) REAL memory bug** → fix the **CODE** as an improvement (`nucleo/memory_agent/processor/distill.py`,
  `nucleo/memory_agent.py`, `memory/api.py`, `memory/retriever.py`, `memory/writer.py`, `memory/consolidator.py`,
  `nucleo/flash/*`). **NEVER soften the test.** Add a regression guard test.
- **(b) FLAKY** (passed before on a fresh run, differs now with no code change → variable canonicalisation by
  the CORE) → **ROBUST anchor**: a stable token + a query with a lexical bridge, or the category's PRIMARY member
  (verify with a `_brain_view` probe, not by re-running the whole wave).
- **(c) TEST-FLAW** (bad anchor, substring collision, unrealistic layer/recall expectation) → fix the case.

Telling them apart is the heart of the cycle: a bug is fixed in code; a flaky case or a test flaw gets a
harder anchor.

### How often it evaluates and QUESTIONS itself

- **Every ~50 steps**: re-read `EXIGENCIA.md` and audit 2–3 random cases (quality control).
- **Every ~100 steps**: one web search for a state-of-the-art memory benchmark/design → note it in `RESEARCH.md`
  and apply whatever improves the system.
- **On every GOLD**: the fresh gold pass is the final judge; its report is triaged down to 0 ❌.

## KNOWN phenomena (not to be mistaken for bugs)

1. **CORE non-determinism**: qwen2.5 (even at temperature 0) canonicalises the same input with different
   wording between runs → anchor on the stable token + bridged queries. This is where flaky cases come from.
2. **Recall at scale**: with hundreds of memories the LOCAL embedding (embeddinggemma) loses precision → a
   SAVED fact may not surface without lexical overlap. It is a model limit, not a bug (the same limit appears in
   the published state of the art). Test it with natural questions that name the entity / use the concrete term.
3. **Anchor collision**: 3-letter markers ("aja") collide with common words ("trAbAJA") → anchor on a
   distinctive phrase or a unique token.

## How to repeat from scratch

1. `--coverage` to see the corpus and the layers. Step 0, ALIGNMENT: does it cover the changes of the last
   48 h? (`git log --since`). If not, add the scenario FIRST.
2. Launch the loop `/loop 10m <cycle prompt>` (dedicated branch `feat/memoria-<something>`). Advance first.
3. When the GOLD closes green: archive the report under `resultados/<date>-ciclo-1000/`, regenerate the HTML
   table (`~/.meshkore/tmp/zaelar-ciclo-1000-memoria.html`), record it in the tester's log, and run the
   **alignment review**.

## Run artefacts

Each run leaves, under `resultados/<date>-ciclo-1000/`: the GOLD report (`gold-report.json`) and, outside the
repo, an HTML table of every request (typology · layer · anchor · result) at
`~/.meshkore/tmp/zaelar-ciclo-1000-memoria.html`. Code fixes found by a cycle land as ordinary commits, each
with its regression guard test.
