"""tests/memory/e2e/bot/embed_bench.py — benchmark de EMBEDDINGS locales a escala (V2-031 T1).

Copia la BD del bot, la RE-EMBEBE con un modelo candidato (`memory/reembed.py`) y corre `scale_eval` → compara
`found@10`/recall@k contra embeddinggemma (768). El embedding fija el TECHO del retriever (found@10): un modelo
más fuerte sube ese techo, que ni el reranker ni el grafo pueden superar. No toca la BD de producción del bot.

Uso:
  ./.venv/bin/python -m tests.memory.e2e.bot.embed_bench --model bge-m3 --provider ollama
  ./.venv/bin/python -m tests.memory.e2e.bot.embed_bench --model intfloat/multilingual-e5-large --provider fastembed
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import time

REPO = pathlib.Path(__file__).resolve().parents[4]
LOGDIR = REPO / ".meshkore" / "logs" / "membot"
SRC_DB = REPO / "memory" / "_data" / "zaelar.membot.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="modelo de embedding candidato (p. ej. bge-m3)")
    ap.add_argument("--provider", default="ollama", help="ollama | fastembed")
    ap.add_argument("--rerank", default="local", help="proveedor de rerank durante la medición (local|off|openai)")
    args = ap.parse_args()

    safe = args.model.replace("/", "_")
    dst = REPO / "memory" / "_data" / f"zaelar.membot.embed-{safe}.db"
    for suf in ("", "-wal", "-shm"):
        p = pathlib.Path(str(SRC_DB) + suf)
        if p.exists():
            shutil.copy(p, str(dst) + suf)
    # sidecar de firma: se re-sella tras el reembed
    pathlib.Path(str(dst) + ".embedsig").unlink(missing_ok=True)

    os.environ["ZAELAR_DB"] = str(dst)
    os.environ["ZAELAR_EMBED_BACKEND"] = args.provider
    os.environ["ZAELAR_EMBED_MODEL"] = args.model
    os.environ["MEMORY_RERANK"] = args.rerank
    os.environ.setdefault("MEM_PROCESSOR", "1")

    from memory import db as _db, embeddings as _emb, reembed
    _db.reset_db(); _emb.reset()
    print(f"▶ embed_bench · modelo={args.model} ({args.provider}) · dim={_emb.dim()} · rerank={args.rerank}")

    t0 = time.time()
    rep_re = reembed.reembed()
    print(f"  re-embed: {rep_re.get('reindexed')}/{rep_re.get('total')} en {time.time()-t0:.0f}s · sig={reembed.signature()}")

    from tests.memory.e2e.bot import scale_eval
    rep = scale_eval.evaluate(limit=10)
    rep.update({"model": args.model, "provider": args.provider, "dim": _emb.dim(),
                "rerank": args.rerank, "signature": reembed.signature()})
    LOGDIR.mkdir(parents=True, exist_ok=True)
    out = LOGDIR / f"embed-{safe}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  found@10={rep['found_rate']:.1%}  recall@1={rep['recall@1']:.1%}  @3={rep['recall@3']:.1%}  "
          f"@5={rep['recall@5']:.1%}  MRR={rep['mrr']:.3f}  lat_p50={rep['lat_p50_ms']}ms")
    print(f"  → {out}")


if __name__ == "__main__":
    main()
