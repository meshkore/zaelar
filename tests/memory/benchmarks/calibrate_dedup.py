"""tests/memory/benchmarks/calibrate_dedup.py — MEASURE the semantic-dedup thresholds of the ACTIVE embedding model (V2-824).

    sqlite3 memory/_data/zaelar.db ".backup /tmp/zaelar-copy.db"   # ALWAYS a copy (`.backup` folds the WAL in; a
    ./.venv/bin/python -m tests.memory.benchmarks.calibrate_dedup --db /tmp/zaelar-copy.db   # plain `cp` of a live WAL db misses rows)
    ./.venv/bin/python -m tests.memory.benchmarks.calibrate_dedup --db /tmp/zaelar-copy.db --backend ollama --model embeddinggemma

The two thresholds in `memory/dedup_thresholds.py` are geometry — how far apart two phrasings of ONE fact land in
ONE model's space — and a number measured on one model means nothing on another (audit 2026-07-26: the
embeddinggemma 0.45 fused two unrelated sentences on fastembed). So a model gets a row only from a measurement,
and this is the measurement. It prints; it never writes the table — a human reads the distributions and decides.
It lives with the benchmarks, not in `memory/`: reading WORDS (the negation rewrite) is an instrument, never product.

THREE CLASSES OF PAIRS, built from a REAL database (no LLM, no network beyond the embedder itself):

  · ECHOES OF ONE FACT — a durable pill and the paraphrases REM already stored for it (`paraphrase_index`, written by
    `rem.index_paraphrases`). Same fact, other words: the pairs dedup MUST merge. Without paraphrases in the copy
    there is nothing to measure here, and the script says so instead of inventing echoes.
  · SAME ENTITY, DIFFERENT FACT — two durable pills linked `about` the same concept node (`edges`) whose texts are
    not each other's paraphrase. Same person/topic, other information: the pairs dedup MUST NOT merge («Laura es mi
    jefa» vs «Laura me pidió el informe»).
  · NEGATIONS — a pill against its own negation, produced by a small deterministic rewrite for the commonest
    Spanish and English verb forms («le gusta» → «no le gusta», «is» → «is not»). Only pills a rule reaches are
    used, and the count says how many. A negation shares every word with its source and means the opposite: it is
    the pair an embedder places closest while dedup must keep it apart, so it bounds the threshold from above.

For each class it prints the distribution of cosine similarity (and the L2 distance between L2-normalised vectors,
which is what the writer compares: d² = 2 − 2·cos) and then SUGGESTS:

  · REM `rem_min_sim`   = the highest similarity any non-echo pair reached (negations and same-entity), plus a
                           margin, provided it still sits below the echoes' 10th percentile — otherwise «no safe
                           threshold», which is also an answer;
  · writer `writer_max_dist` = the distance equivalent of the same point.

Every number is printed with its sample size. A suggestion from 8 pairs is a hint, not a calibration.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sqlite3
import sys


# ── deterministic negation (ES + EN, the commonest forms only; everything else is skipped and counted) ────────
_NEG_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(le|les|me|te|nos) (gusta|gustan|encanta|encantan|interesa|interesan|molesta|molestan)\b", re.I),
     r"no \1 \2"),
    (re.compile(r"\b(es|son|está|están|tiene|tienen|vive|viven|trabaja|trabajan|quiere|quieren|prefiere|prefieren|"
                r"suele|suelen|puede|pueden|va|van|hay)\b", re.I), r"no \1"),
    (re.compile(r"\b(is|are|was|were|has|have|does|do|can|will)\b", re.I), r"\1 not"),
    (re.compile(r"\b(likes|loves|prefers|wants|lives|works|needs)\b", re.I), r"doesn't \1"),
]
_ALREADY_NEG = re.compile(r"\b(no|nunca|jamás|not|never|n't)\b", re.I)


def negate(text: str) -> str | None:
    """One negation of `text`, or None when no rule applies or the sentence is already negative."""
    if _ALREADY_NEG.search(text):
        return None
    for rx, rep in _NEG_RULES:
        if rx.search(text):
            out = rx.sub(rep, text, count=1)
            return out if out != text else None
    return None


# ── pairs from a real database ─────────────────────────────────────────────────────────────────────────────────
_DURABLE = ("SELECT id, text FROM memories WHERE valid=1 AND level IN ('mid','long') "
            "AND kind NOT IN ('conv','concept','insight') AND slot IS NULL "
            "AND (meta IS NULL OR meta NOT LIKE '%\"trust\": \"untrusted\"%')")


def _rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    try:
        return list(conn.execute(sql, args))
    except sqlite3.Error as e:
        print(f"note: query skipped on this copy ({e}) — the class it feeds will report n=0", file=sys.stderr)
        return []


def echoes(conn: sqlite3.Connection, cap: int) -> list[tuple[str, str]]:
    rows = _rows(conn, "SELECT m.text AS a, p.text AS b FROM paraphrase_index p JOIN memories m ON m.id = p.memory_id "
                       "WHERE m.valid=1 AND m.level IN ('mid','long') AND m.kind NOT IN ('conv','concept','insight')")
    pairs = [(r["a"], r["b"]) for r in rows if (r["a"] or "").strip() and (r["b"] or "").strip()
             and r["a"].strip().lower() != r["b"].strip().lower()]
    return pairs[:cap]


def same_entity(conn: sqlite3.Connection, cap: int, seed: int) -> list[tuple[str, str]]:
    """Two durable pills `about` the same concept node, excluding literal repeats and stored paraphrases."""
    by_concept: dict[int, list[str]] = {}
    for r in _rows(conn, "SELECT e.to_id AS c, m.text AS t FROM edges e JOIN memories m ON m.id = e.from_id "
                         "JOIN memories cn ON cn.id = e.to_id WHERE e.type='about' AND cn.kind='concept' "
                         "AND m.valid=1 AND m.level IN ('mid','long') AND m.kind NOT IN ('conv','concept','insight') "
                         "AND m.slot IS NULL"):
        if (r["t"] or "").strip():
            by_concept.setdefault(int(r["c"]), []).append(r["t"].strip())
    para = {(a.lower(), b.lower()) for a, b in echoes(conn, 10 ** 6)}
    rng = random.Random(seed)
    pairs: list[tuple[str, str]] = []
    for texts in by_concept.values():
        uniq = sorted({t for t in texts}, key=str.lower)
        if len(uniq) < 2:
            continue
        idx = list(range(len(uniq)))
        rng.shuffle(idx)
        for i in range(0, len(idx) - 1, 2):
            a, b = uniq[idx[i]], uniq[idx[i + 1]]
            if a.lower() == b.lower() or (a.lower(), b.lower()) in para or (b.lower(), a.lower()) in para:
                continue
            pairs.append((a, b))
    rng.shuffle(pairs)
    return pairs[:cap]


def negations(conn: sqlite3.Connection, cap: int) -> tuple[list[tuple[str, str]], int]:
    rows = _rows(conn, _DURABLE)
    pairs: list[tuple[str, str]] = []
    for r in rows:
        n = negate((r["text"] or "").strip())
        if n:
            pairs.append((r["text"].strip(), n))
        if len(pairs) >= cap:
            break
    return pairs, len(rows)


# ── measurement ────────────────────────────────────────────────────────────────────────────────────────────────
def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[k]


def _dist(cos: float) -> float:
    return math.sqrt(max(0.0, 2.0 - 2.0 * cos))


def measure(pairs: list[tuple[str, str]], embed_batch) -> list[float]:
    if not pairs:
        return []
    flat = [t for p in pairs for t in p]
    vecs = embed_batch(flat)
    return [_cos(vecs[2 * i], vecs[2 * i + 1]) for i in range(len(pairs))]


def summary(name: str, sims: list[float]) -> dict:
    return {"class": name, "n": len(sims),
            "cos": {"min": _pct(sims, 0), "p10": _pct(sims, .10), "p50": _pct(sims, .50),
                    "p90": _pct(sims, .90), "max": _pct(sims, 1)},
            "dist": {"min": _dist(_pct(sims, 1)), "p50": _dist(_pct(sims, .5)), "max": _dist(_pct(sims, 0))}}


def suggest(echo: list[float], entity: list[float], neg: list[float], margin: float = 0.02) -> dict:
    """The point every non-echo pair sits below and every echo (p10) sits above — or «none» when they cross."""
    ceiling_non_echo = max(entity + neg) if (entity or neg) else None
    floor_echo = _pct(echo, .10) if echo else None
    out: dict = {"non_echo_max_cos": ceiling_non_echo, "echo_p10_cos": floor_echo}
    if ceiling_non_echo is None or floor_echo is None:
        out["verdict"] = "insufficient data — need both echoes and non-echo pairs"
        return out
    sim = ceiling_non_echo + margin
    if sim >= floor_echo:
        out["verdict"] = (f"NO SAFE THRESHOLD on this model: the closest non-echo ({ceiling_non_echo:.3f}) is not "
                          f"below the echoes' p10 ({floor_echo:.3f}) — leave semantic dedup OFF (exact/slot only)")
        return out
    out.update({"rem_min_sim": round(sim, 3), "writer_max_dist": round(_dist(sim), 3),
                "verdict": "a row for `memory/dedup_thresholds.py` — if the sample sizes above are worth trusting"})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True, help="a COPY of a real zaelar.db (opened read-only)")
    ap.add_argument("--backend", default="", help="ZAELAR_EMBED_BACKEND for this run (openai|ollama|…); default: the config")
    ap.add_argument("--model", default="", help="ZAELAR_EMBED_MODEL for this run; default: the config")
    ap.add_argument("--cap", type=int, default=300, help="max pairs per class")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if args.backend:
        os.environ["ZAELAR_EMBED_BACKEND"] = args.backend
    if args.model:
        os.environ["ZAELAR_EMBED_MODEL"] = args.model
    from memory import embeddings as _emb
    from memory import dedup_thresholds as _thr
    _emb.reset()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    echo_pairs = echoes(conn, args.cap)
    ent_pairs = same_entity(conn, args.cap, args.seed)
    neg_pairs, durable_n = negations(conn, args.cap)

    e = measure(echo_pairs, _emb.embed_batch)
    if _emb.last_degraded:
        print("the embedder is degraded (no key, no server): nothing measured", file=sys.stderr)
        return 2
    s = measure(ent_pairs, _emb.embed_batch)
    n = measure(neg_pairs, _emb.embed_batch)
    model = _thr.active_model() or _emb.active_backend()
    report = {
        "model": model, "backend": _emb.active_backend(), "dim": _emb.dim(), "db": args.db,
        "durable_pills": durable_n,
        "classes": [summary("echoes (pill vs its stored paraphrase)", e),
                    summary("same entity, different fact (shared concept)", s),
                    summary("negations (pill vs its own negation)", n)],
        "current_row": _thr.for_model(model),
        "suggested": suggest(e, s, n),
        "examples": {"echo": echo_pairs[:3], "same_entity": ent_pairs[:3], "negation": neg_pairs[:3]},
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"model {report['model']} · backend {report['backend']} · {report['dim']} dims · {durable_n} durable pills")
    for c in report["classes"]:
        k = c["cos"]
        print(f"  {c['class']:<48} n={c['n']:<4} cos min {k['min']:.3f} p10 {k['p10']:.3f} p50 {k['p50']:.3f} "
              f"p90 {k['p90']:.3f} max {k['max']:.3f}  (dist p50 {c['dist']['p50']:.3f})")
    print(f"  current row: {report['current_row'] or 'none (semantic dedup OFF on this model)'}")
    sg = report["suggested"]
    print(f"  suggested: {json.dumps({k: v for k, v in sg.items() if k != 'verdict'})}")
    print(f"  verdict: {sg['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
