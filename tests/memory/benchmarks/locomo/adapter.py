"""LoCoMo adapter — measuring our memory on the SAME public benchmark the market players published on.

LoCoMo ("Evaluating Very Long-Term Conversational Memory of LLM Agents", Maharana et al. 2024) is the benchmark
Mem0, Zep and Graphiti all published against, which is the only reason it is the one worth running first: a
number nobody else reports is not a comparison. 10 conversations, 19 sessions each, 5,882 turns, 1,986 questions
in five categories (1 multi-hop · 2 temporal · 3 open-domain · 4 single-hop · 5 adversarial).

**The four declarations.** Every LoCoMo number in circulation is unreproducible without these, and most published
ones omit at least one. Ours are printed with every run and stored in its JSON:
  1. INGESTION — how the dialogue got into memory (`distill` = our real write-path core, one LLM call per turn;
     `verbatim` = each turn stored as-is, no distillation).
  2. RETRIEVAL — `memory.api.query()`, our real read path, with its `limit`.
  3. ANSWERER — the model that answers from the retrieved context, and NOTHING else.
  4. JUDGE — the model that grades, and the embedding backend underneath it all.

**Why the ingestion mode is a declaration and not a detail.** With `verbatim` this measures our RETRIEVER over raw
dialogue; with `distill` it measures our MEMORY (distiller + slots + supersede + graph + reranker). They are
different claims and the second is ~26 h of API calls for the full set, so a run that does not say which one it
used is not interpretable. Reporting `verbatim` as if it were the system would be the more flattering mistake in
one direction and the less flattering in the other — the ablation this repo already measured says verbatim
retrieval BEATS artifact-only retrieval (43.9% vs 28.0% on LoCoMo, third-party), so the honest configuration is
both, which is what V2-114 F4.2 is for.

**Known ceiling of the benchmark itself, stated up front.** The published audits of LoCoMo find ~6.4% of answer
keys wrong or unanswerable from the evidence, so ~93.6% is the practical ceiling, and an LLM judge accepts a
sizeable fraction of deliberately-wrong answers. That is a property of LoCoMo, not of any system measured on it —
it means small differences between published numbers are noise, and it is the reason to also run Locomo-Plus-style
variants later (F8). We do not get to claim precision the benchmark does not have.

**Isolation.** Every conversation runs in its OWN database under a temp root (`ZAELAR_DB`), never the operator's.
The real memory of the machine is never touched, read or written.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import time

# ── the four declarations, as data ───────────────────────────────────────────────────────────────────────────
ANSWERER_MODEL = os.getenv("LOCOMO_ANSWERER", "openai/gpt-4.1-mini")
JUDGE_MODEL = os.getenv("LOCOMO_JUDGE", "openai/gpt-4.1-mini")
BROKER_URL = "https://api.aimlapi.com/v1"          # house rule: everything through the one broker account

CATEGORY_NAMES = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop", 5: "adversarial"}

_ANSWER_SYSTEM = (
    "You answer a question about a long conversation using ONLY the retrieved memory below. "
    "Answer in as few words as possible — a name, a date, a short phrase. No explanation, no full sentences. "
    "If the memory does not contain the answer, reply exactly: NO INFORMATION AVAILABLE."
)

_JUDGE_SYSTEM = (
    "You grade one answer against a gold answer for a question about a conversation. "
    "Reply with exactly one word: CORRECT or WRONG. "
    "Grade on MEANING, not wording: a different date format, a first name where the gold says the full name, or a "
    "paraphrase all count as CORRECT. Extra correct detail is CORRECT. A missing or contradicted key fact is WRONG. "
    "If the gold answer says no information is available, then only a refusal to answer is CORRECT."
)


def load(path: str | pathlib.Path) -> list[dict]:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def sessions_in_order(conv: dict) -> list[tuple[str, str, list[dict]]]:
    """`[(session_key, date_time, turns)]` in chronological session order.

    The keys are `session_1`, `session_2`… so they must be sorted NUMERICALLY: string order puts `session_10`
    between 1 and 2, which would feed a long-term-memory benchmark its sessions out of order — silently, and in a
    way that only shows up as bad temporal-reasoning scores."""
    out = []
    for k in sorted((k for k in conv if re.fullmatch(r"session_\d+", k)),
                    key=lambda s: int(s.split("_")[1])):
        out.append((k, conv.get(f"{k}_date_time", ""), conv[k] or []))
    return out


def gold_answer(qa: dict) -> str:
    """Category 5 stores its key under `adversarial_answer`, and its POINT is that the right response is a refusal.
    Reading `answer` for every category would score category 5 against an empty string, i.e. reward any refusal
    and any hallucination equally."""
    if qa.get("category") == 5:
        return str(qa.get("adversarial_answer") or "no information available")
    return str(qa.get("answer", ""))


# ── ingestion ────────────────────────────────────────────────────────────────────────────────────────────────
def ingest_verbatim(conv: dict, *, speaker_of_interest: str | None = None) -> int:
    """Store every turn as a durable memory, attributed and dated, with NO distillation.

    This measures the RETRIEVER over raw dialogue. Attribution matters: LoCoMo questions name the speakers
    ("When did Caroline go to…"), so a turn stored without its speaker is unanswerable no matter how good
    retrieval is — that would be measuring our own formatting bug, not the system."""
    from memory import api as memapi
    n = 0
    for _key, when, turns in sessions_in_order(conv.get("conversation") or {}):
        for t in turns:
            speaker = (t.get("speaker") or "").strip()
            text = (t.get("text") or "").strip()
            if not text:
                continue
            stamped = f"[{when}] {speaker}: {text}" if when else f"{speaker}: {text}"
            memapi.write_now(stamped, level="long", kind="msg", importance=0.5)
            n += 1
    return n


async def ingest_distilled(conv: dict) -> int:
    """Feed every turn through the REAL write-path core (`nucleo/memory_agent.ingest_utterance`).

    This is the faithful "our memory" configuration and it is expensive: one LLM call per turn, ~5,882 turns for
    the full set. Use `--conversations` to run a labeled slice rather than pretending a partial run is a full one."""
    from nucleo import memory_agent
    n = 0
    for _key, when, turns in sessions_in_order(conv.get("conversation") or {}):
        for t in turns:
            speaker = (t.get("speaker") or "").strip()
            text = (t.get("text") or "").strip()
            if not text:
                continue
            stamped = f"[{when}] {speaker}: {text}" if when else f"{speaker}: {text}"
            try:
                await memory_agent.ingest_utterance(stamped)
            except Exception:  # noqa: BLE001
                pass       # one turn failing must not abort a multi-hour ingest; it shows up as a recall miss
            n += 1
    return n


# ── retrieval + answer + judge ───────────────────────────────────────────────────────────────────────────────
def retrieve(question: str, *, limit: int = 20) -> list[dict]:
    from memory import api as memapi
    return (memapi.query(question, limit=limit).get("memories") or [])


def answer(question: str, mems: list[dict]) -> str:
    from nucleo import memllm
    if not mems:
        return "NO INFORMATION AVAILABLE"
    ctx = "\n".join(f"- {m['text']}" for m in mems)
    out = memllm.chat_sync("rem", _ANSWER_SYSTEM, f"MEMORY:\n{ctx}\n\nQUESTION: {question}",
                           max_tokens=120, temperature=0.0, timeout=90.0,
                           model_override=ANSWERER_MODEL, url_override=BROKER_URL)
    return (out or "").strip()


def judge(question: str, gold: str, got: str) -> bool | None:
    """True/False, or **None when the judge itself did not answer** — which is not the same as WRONG and must not
    be counted as one. A judge outage scored as a wrong answer silently deflates the result and looks like a
    memory regression."""
    from nucleo import memllm
    if not (got or "").strip():
        return False
    out = memllm.chat_sync("rem", _JUDGE_SYSTEM,
                           f"QUESTION: {question}\nGOLD: {gold}\nANSWER: {got}",
                           max_tokens=6, temperature=0.0, timeout=90.0,
                           model_override=JUDGE_MODEL, url_override=BROKER_URL)
    if not out:
        return None
    up = out.strip().upper()
    if "CORRECT" in up and "INCORRECT" not in up:
        return True
    if "WRONG" in up or "INCORRECT" in up:
        return False
    return None


def declarations(ingest_mode: str, limit: int) -> dict:
    from memory import embeddings as _emb
    from memory import rerank as _rr
    try:
        rr = _rr.status()
    except Exception:  # noqa: BLE001
        rr = {}
    return {
        "ingestion": ingest_mode,
        "retrieval": f"memory.api.query(limit={limit})",
        "answerer": ANSWERER_MODEL,
        "judge": JUDGE_MODEL,
        "embedding": f"{_emb.active_backend()}:{_emb._active_model_name() or '-'}:{_emb.dim()}",
        "reranker": {k: rr.get(k) for k in ("provider", "model", "enabled", "available", "top_n")} if rr else None,
        "ts": int(time.time()),
    }
