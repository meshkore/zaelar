"""Run LoCoMo against our memory. Every conversation gets its OWN isolated DB; the operator's memory is untouched.

    ./.venv/bin/python -m tests.memory.benchmarks.locomo.run --data /path/locomo10.json \
        --conversations 1 --ingest verbatim --qa-limit 60

Reports accuracy overall and PER CATEGORY, because the categories measure different things and a single number
hides which one a change actually moved (temporal reasoning is the one this repo has open findings about).
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import pathlib
import sys
import tempfile
import time

REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))


def _pin_language(code: str) -> str:
    """Pin the memory's canonical language, AFTER `server.common` — which is the only way it holds.

    Our memory is MONOLINGUAL by design (2026-07-10): the distiller writes every pill in the OPERATOR's language,
    translating whatever comes in another. That is right for the product and it is a CONFOUND for this benchmark:
    LoCoMo is English, the published numbers store English as English, and with a Spanish operator our distiller
    translated the whole corpus to Spanish and then answered English questions against Spanish pills — a
    cross-lingual penalty baked into the score that no competitor's number carries.

    And it cannot be set from the outside: `config/settings.py` maps `stt_language` -> `ZAELAR_LANGUAGE` and
    `load_into_env` applies it with **override**, so `ZAELAR_LANGUAGE=en ./run` silently comes back as `es`
    (measured 2026-08-18: the env var went in as `en` and `langs.current_code()` answered `es`). Hence the order
    here — import first, pin after — and hence it is a DECLARATION and not a flag: a LoCoMo number that does not
    say which language the memory stored is not comparable with anyone's."""
    os.environ["ZAELAR_LANGUAGE"] = code
    return code


def _fresh_db(root: pathlib.Path, tag: str) -> None:
    """Point the whole memory subsystem at a brand-new DB. Per conversation, so no cross-contamination: LoCoMo's
    conversations share first names, and a leak between them would look like excellent multi-hop recall."""
    os.environ["ZAELAR_DB"] = str(root / f"locomo-{tag}.db")
    from memory import db as _db
    _db.reset_db()
    _db.get_db()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/private/tmp/claude-501/locomo10.json")
    ap.add_argument("--conversations", type=int, default=1, help="how many conversations (10 = full set)")
    ap.add_argument("--ingest", choices=["verbatim", "distill"], default="verbatim")
    ap.add_argument("--qa-limit", type=int, default=0, help="cap questions per conversation (0 = all)")
    ap.add_argument("--categories", default="", help="comma-separated category ids, e.g. 1,2,4")
    ap.add_argument("--limit", type=int, default=20, help="retrieval limit passed to memory.api.query")
    ap.add_argument("--label", default="locomo")
    ap.add_argument("--lang", default="en",
                    help="canonical language the memory stores in (LoCoMo is English; see _pin_language)")
    args = ap.parse_args()

    import server.common  # noqa: F401  — loads the credential store into env (the broker key lives there)
    _pin_language(args.lang)          # MUST come after the import above — it overrides ZAELAR_LANGUAGE
    from tests.memory.benchmarks.locomo import adapter as A

    data = A.load(args.data)[: args.conversations]
    cats = {int(c) for c in args.categories.split(",") if c.strip()} or None
    root = pathlib.Path(tempfile.mkdtemp(prefix="locomo-"))

    rows: list[dict] = []
    t0 = time.time()
    for ci, conv in enumerate(data):
        _fresh_db(root, f"c{ci}")
        ti = time.time()
        if args.ingest == "distill":
            n = asyncio.run(A.ingest_distilled(conv))
        else:
            n = A.ingest_verbatim(conv)
        print(f"[conv {ci}] ingested {n} turns in {time.time() - ti:.1f}s ({args.ingest})", flush=True)

        qa = [q for q in (conv.get("qa") or []) if (cats is None or q.get("category") in cats)]
        if args.qa_limit:
            qa = qa[: args.qa_limit]
        twins = A.name_swap_twins(conv)     # cat-5 asked about the WRONG person — see that function
        for qi, q in enumerate(qa):
            question = q.get("question") or ""
            gold = A.gold_answer(q)
            mems = A.retrieve(question, limit=args.limit)
            got = A.answer(question, mems)
            verdict = A.judge(question, gold, got)
            rows.append({"conv": ci, "category": q.get("category"), "q": question,
                         "gold": gold, "got": got, "verdict": verdict, "retrieved": len(mems),
                         "name_swap": question in twins})
            if (qi + 1) % 10 == 0:
                ok = sum(1 for r in rows if r["verdict"] is True)
                gr = sum(1 for r in rows if r["verdict"] is not None)
                print(f"  [conv {ci}] {qi + 1}/{len(qa)} · acc {ok}/{gr} = "
                      f"{(ok / gr * 100 if gr else 0):.1f}%", flush=True)

    graded = [r for r in rows if r["verdict"] is not None]
    ungraded = len(rows) - len(graded)
    ok = sum(1 for r in graded if r["verdict"])
    per_cat: dict = collections.defaultdict(lambda: [0, 0])
    for r in graded:
        per_cat[r["category"]][1] += 1
        per_cat[r["category"]][0] += 1 if r["verdict"] else 0

    decl = A.declarations(args.ingest, args.limit)
    decl["language"] = args.lang
    print("\n" + "=" * 72)
    print(f"LoCoMo [{args.label}] · {len(data)} conversation(s) · {len(rows)} questions · "
          f"{time.time() - t0:.0f}s")
    print("  DECLARATIONS (a LoCoMo number without these is not reproducible):")
    for k in ("ingestion", "language", "retrieval", "answerer", "judge", "embedding"):
        print(f"    {k:10s} {decl[k]}")
    print(f"    reranker   {decl['reranker']}")
    print(f"\n  accuracy: {ok}/{len(graded)} = {(ok / len(graded) * 100 if graded else 0):.1f}%"
          f"{f'   ({ungraded} ungraded — judge did not answer, NOT counted wrong)' if ungraded else ''}")
    for cat in sorted(per_cat):
        c_ok, c_n = per_cat[cat]
        print(f"    cat {cat} {A.CATEGORY_NAMES.get(cat, '?'):12s} {c_ok}/{c_n} = {c_ok / c_n * 100:.1f}%")

    # The number to compare a CHANGE against. `adapter.name_swap_twins` explains why: those questions ask about
    # the wrong person and keep the right person's answer, so scoring well on them requires ignoring attribution —
    # a memory that gets attribution RIGHT is penalised. Reported next to the total rather than instead of it: the
    # total is what the market published, so it is what makes us comparable, and this one is what tells us whether
    # a change helped. Both, always, or the next reader picks whichever flatters the change.
    swap = [r for r in graded if r.get("name_swap")]
    clean = [r for r in graded if not r.get("name_swap")]
    if swap and clean:
        s_ok = sum(1 for r in swap if r["verdict"])
        c_ok = sum(1 for r in clean if r["verdict"])
        print(f"\n  excluding NAME-SWAPPED questions: {c_ok}/{len(clean)} = {c_ok / len(clean) * 100:.1f}%"
              f"   ← compare CHANGES on this one")
        print(f"    (the {len(swap)} excluded scored {s_ok}/{len(swap)} = {s_ok / len(swap) * 100:.1f}%; there,"
              f" a HIGHER score means WORSE attribution — see adapter.name_swap_twins)")

    print("\n  NOTE: published audits find ~6.4% of LoCoMo answer keys wrong/unanswerable → ~93.6% is the")
    print("  practical ceiling, and an LLM judge accepts a share of deliberately-wrong answers. Small gaps")
    print("  between published numbers are noise; this is a property of the benchmark, not of any system.")
    print("=" * 72)

    out = REPO / ".meshkore/logs/membot" / f"locomo-{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"declarations": decl, "n": len(rows), "graded": len(graded),
                               "ungraded": ungraded, "correct": ok,
                               "accuracy": (ok / len(graded)) if graded else 0.0,
                               # Stored so a past run can be RE-READ against the name-swap finding without
                               # re-running it: the four arms measured before 2026-08-19 have no such field, and
                               # their `rows` carry the question text, which is enough to recompute it.
                               "name_swap_excluded": len(swap),
                               "accuracy_excluding_name_swaps": (
                                   sum(1 for r in clean if r["verdict"]) / len(clean)) if clean else None,
                               "per_category": {str(k): per_cat[k] for k in per_cat},
                               "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
