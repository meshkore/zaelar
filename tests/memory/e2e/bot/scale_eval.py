"""tests/memory/e2e/bot/scale_eval.py — harness de RECALL A ESCALA (reranker A/B) (V2-030).

Mide la CALIDAD del retriever LARGO (`memory/retriever.search`) sobre la BD **AISLADA** ya poblada con la persona
del bot (cientos de recuerdos). Es el número que movemos con el reranker: para cada query de recall-largo del
corpus (`t=query`, `via=long`, con `want`) calcula el RANGO del primer resultado que contiene el ancla esperada
→ **recall@1/3/5/10**, **MRR** y **latencia**. No usa LLM en la lectura (invariante V2-013): mide el camino real.

A/B del reranker: se corre dos veces cambiando el proveedor por env/config (`MEMORY_RERANK=off|openai|local`).
El harness NO reconstruye la persona por defecto (reutiliza `zaelar.membot.db` acumulada); `--fresh` la repuebla
corriendo el runner de cero (lento: CORAZÓN LLM configurado por cada save).

Uso:
  ./.venv/bin/python -m tests.memory.e2e.bot.scale_eval                 # mide sobre la BD actual
  MEMORY_RERANK=openai ./.venv/bin/python -m tests.memory.e2e.bot.scale_eval --label openai
  ./.venv/bin/python -m tests.memory.e2e.bot.scale_eval --fresh         # repuebla y mide
  ./.venv/bin/python -m tests.memory.e2e.bot.scale_eval --ab            # corre off vs config actual y compara

BD aislada: `ZAELAR_DB=memory/_data/zaelar.membot.db` (gitignored). El perfil REAL no se toca.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import time
import unicodedata

REPO = pathlib.Path(__file__).resolve().parents[4]
LOGDIR = REPO / ".meshkore" / "logs" / "membot"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _setup_env():
    os.environ.setdefault("ZAELAR_DB", str(REPO / "memory" / "_data" / "zaelar.membot.db"))
    os.environ.setdefault("MEM_PROCESSOR", "1")
    # carga las keys (OPENAI_API_KEY para el reranker OpenAI) igual que server/common.py
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env", override=False)
        load_dotenv(REPO / ".meshkore" / "credentials" / "zaelar.env", override=False)
    except Exception:
        pass


def _long_queries() -> list[dict]:
    from tests.memory.e2e.bot import cases as C
    return [c for c in C.CASES if c.get("t") == "query" and c.get("via") == "long" and c.get("want")]


def _rank_of(results: list[dict], wants: list[str]) -> int | None:
    """Rango (1-indexado) del primer resultado cuyo texto contiene ALGUNA ancla esperada. None si no aparece."""
    wants = [_norm(w) for w in wants]
    for i, m in enumerate(results, start=1):
        txt = _norm(m.get("text", ""))
        if any(w in txt for w in wants):
            return i
    return None


def _durable_blob() -> str:
    """Texto de TODOS los recuerdos durables válidos (mid/long), normalizado — para saber si un hecho ESTÁ
    guardado (write-completeness) con independencia de si se recupera (retrieval)."""
    from memory import db as _db
    rows = _db.get_db().query("SELECT text FROM memories WHERE valid=1 AND level IN ('mid','long')")
    return "\n".join(_norm(r["text"]) for r in rows)


def _is_stored(wants: list[str], blob: str) -> bool:
    return any(_norm(w) in blob for w in wants)


def evaluate(limit: int = 10) -> dict:
    """Corre todas las queries de recall-largo por `retriever.search` y agrega recall@k/MRR/latencia."""
    from memory import retriever

    qs = _long_queries()
    n = len(qs)
    blob = _durable_blob()             # snapshot para clasificar write vs retrieval
    ranks: list[int | None] = []
    lat_ms: list[float] = []
    misses: list[dict] = []
    write_miss = retrieval_miss = stored = found_stored = 0
    for c in qs:
        t0 = time.perf_counter()
        res = retriever.search(c["q"], limit=limit, expand=True, reinforce=False)
        lat_ms.append((time.perf_counter() - t0) * 1000.0)
        r = _rank_of(res, c["want"])
        ranks.append(r)
        is_stored = _is_stored(c["want"], blob)
        if is_stored:
            stored += 1
            if r is not None:
                found_stored += 1
        if r is None or r > 3:
            if is_stored:
                retrieval_miss += 1
            else:
                write_miss += 1
            misses.append({"q": c["q"], "want": c["want"], "rank": r, "dim": c.get("dim"),
                           "miss": "retrieval" if is_stored else "write"})

    def rec_at(k: int) -> float:
        hit = sum(1 for r in ranks if r is not None and r <= k)
        return hit / n if n else 0.0

    mrr = sum((1.0 / r) for r in ranks if r) / n if n else 0.0
    lat_ms.sort()
    p50 = lat_ms[len(lat_ms) // 2] if lat_ms else 0.0
    p95 = lat_ms[int(len(lat_ms) * 0.95)] if lat_ms else 0.0
    return {
        "n": n,
        "recall@1": round(rec_at(1), 4),
        "recall@3": round(rec_at(3), 4),
        "recall@5": round(rec_at(5), 4),
        "recall@10": round(rec_at(10), 4),
        "mrr": round(mrr, 4),
        "found_rate": round(sum(1 for r in ranks if r is not None) / n, 4) if n else 0.0,
        # DESCOMPOSICIÓN del techo (V2-031): cuánto es de ESCRITURA y cuánto de RECUPERACIÓN.
        "write_completeness": round(stored / n, 4) if n else 0.0,                 # % de queries cuyo dato SÍ está guardado
        "retrieval_at10_given_stored": round(found_stored / stored, 4) if stored else 0.0,
        "write_miss": write_miss,
        "retrieval_miss": retrieval_miss,
        "lat_p50_ms": round(p50, 1),
        "lat_p95_ms": round(p95, 1),
        "misses": misses,
    }


def _corpus_size() -> dict:
    from memory import db as _db
    d = _db.get_db()
    return {
        "total": d.query_one("SELECT COUNT(*) c FROM memories")["c"],
        "durable": d.query_one("SELECT COUNT(*) c FROM memories WHERE valid=1 AND level IN ('mid','long')")["c"],
    }


def _rerank_status() -> dict:
    try:
        from memory import rerank
        return rerank.status()
    except Exception:
        return {"provider": "off", "available": False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="repuebla la persona de cero (lento) antes de medir")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--label", default=None, help="etiqueta del run (p. ej. off/openai/local)")
    args = ap.parse_args()
    _setup_env()

    if args.fresh:
        import asyncio as _asyncio

        from tests.memory.e2e.bot import runner
        print("⟳ repoblando la persona (--fresh, corpus completo)…")
        # fix 2026-07-20: la API real del runner es la corrutina run_range, no un run() síncrono inexistente.
        _asyncio.run(runner.run_range(0, 10_000, fresh=True))

    size = _corpus_size()
    rr = _rerank_status()
    label = args.label or rr.get("provider", "off")
    print(f"▶ scale_eval [{label}] · corpus {size['durable']} durables / {size['total']} total · rerank={rr}")
    t0 = time.time()
    rep = evaluate(limit=args.limit)
    rep.update({"label": label, "corpus": size, "rerank": rr, "elapsed_s": round(time.time() - t0, 1)})

    LOGDIR.mkdir(parents=True, exist_ok=True)
    out = LOGDIR / f"scale-{label}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  n={rep['n']}  found={rep['found_rate']:.1%}")
    print(f"  recall@1={rep['recall@1']:.1%}  @3={rep['recall@3']:.1%}  "
          f"@5={rep['recall@5']:.1%}  @10={rep['recall@10']:.1%}")
    print(f"  MRR={rep['mrr']:.3f}  lat p50={rep['lat_p50_ms']}ms p95={rep['lat_p95_ms']}ms")
    print(f"  ── descomposición ──  WRITE-completeness={rep['write_completeness']:.1%}  ·  "
          f"RETRIEVAL@10|guardado={rep['retrieval_at10_given_stored']:.1%}")
    print(f"  misses: {rep['write_miss']} ESCRITURA (no guardado) · {rep['retrieval_miss']} RECUPERACIÓN (guardado, no top-3)  ·  → {out}")


if __name__ == "__main__":
    main()
