# LoCoMo — the public benchmark the market players published on

`LoCoMo` ("Evaluating Very Long-Term Conversational Memory of LLM Agents", Maharana et al. 2024) is the only
benchmark worth running FIRST, for one reason: Mem0, Zep and Graphiti all published against it. A number nobody
else reports is not a comparison.

**Shape of the dataset**: 10 conversations · 19 sessions each · **5,882 turns** · **1,986 questions** in five
categories — `1` multi-hop, `2` temporal, `3` open-domain, `4` single-hop, `5` adversarial (the correct response
is a refusal; the key lives under `adversarial_answer`, not `answer`).

Not vendored here (2.8 MB of third-party data, and this repo is public):

```bash
curl -sL -o /tmp/locomo10.json \
  https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json
```

## Running it

```bash
# fast slice: retriever over raw dialogue, one conversation, all its questions (~15 min)
ZAELAR_EMBED_BACKEND=fastembed ./.venv/bin/python -m tests.memory.benchmarks.locomo.run \
    --data /tmp/locomo10.json --conversations 1 --ingest verbatim --label c0_verbatim

# faithful: every turn through the REAL write-path core (~1.8 h per conversation, real API cost)
MESHKORE_MEMORY_URL=http://127.0.0.1:9/v1 ./.venv/bin/python -m tests.memory.benchmarks.locomo.run \
    --data /tmp/locomo10.json --conversations 1 --ingest distill --label c0_distill
```

Each conversation runs in its **own** temp database. The operator's memory is never read or written — LoCoMo's
conversations share first names, so a leak between them would look like excellent multi-hop recall.

`MESHKORE_MEMORY_URL=http://127.0.0.1:9/v1` makes the cluster-observation synthesizer fail INSTANTLY instead of
waiting out its timeout against a busy Ollama. Without it a run can sit at 1.4% CPU looking slow when it is just
queued — the same trap that stalled a replay of the distiller tape.

## The four declarations

A LoCoMo number without these is not reproducible, and most published ones omit at least one. They are printed
with every run and stored in its JSON:

| | what it pins down |
|---|---|
| **ingestion** | `distill` (our real write-path core, one LLM call per turn) or `verbatim` (turns stored as-is) |
| **retrieval** | `memory.api.query(limit=N)` — the real read path |
| **answerer** | the model that answers from the retrieved context, and nothing else |
| **judge** | the model that grades — plus the embedding backend and reranker underneath it all |

**Why ingestion is a declaration and not a detail.** `verbatim` measures our RETRIEVER over raw dialogue;
`distill` measures our MEMORY (distiller + slots + supersede + graph + reranker). Those are different claims. And
the direction of the difference is not obvious: the controlled ablation says **verbatim retrieval BEATS
artifact-only retrieval** (43.9% vs 28.0% on LoCoMo; 67.4% vs 45.4% on LongMemEval-S, third-party), because
distilling into structure discards information the raw utterance had. So neither mode flatters us by default, and
the configuration we actually want is **both** — the pill as the answer, the raw utterance as an extra retrieval
path (V2-114 F4.2). Reporting either mode as "the system" without saying which is the mistake to avoid.

## Known ceiling of the benchmark itself

Stated up front, because it bounds what any of these numbers can mean:

- Published audits find **~6.4% of LoCoMo answer keys wrong or unanswerable** from the cited evidence → **~93.6%
  is the practical ceiling**, not 100%.
- An LLM judge accepts a sizeable share of deliberately-wrong answers, so the judge is a noise floor of its own.
- Therefore **small gaps between published numbers are noise.** That is a property of LoCoMo, not of any system
  measured on it, and it is the reason to also run Locomo-Plus-style variants (which strip the superficial cues
  that let a system score without real recall — Mem0 went 57.24 → 15.80 under that treatment).

We do not get to claim precision the benchmark does not have.

## Language

LoCoMo is ENGLISH, and this memory is monolingual by design — it lives in the OPERATOR's language and the
distiller TRANSLATES what arrives in another one. So a `distill` run against LoCoMo should have the operator
language set to English, or the benchmark measures our translation on top of our recall. The `verbatim` mode is
unaffected (nothing is rewritten).

## Results

Recorded in `.meshkore/logs/membot/locomo-<label>.json` with the declarations attached, and summarized in the
V2-114 initiative's log — never as a bare percentage.
