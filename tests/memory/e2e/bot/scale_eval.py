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
    # Ver la nota gemela en tests/memory/e2e/bot/runner.py::_setup_env — pinea el backend para que MEDIR (esta
    # función) resuelva SIEMPRE al mismo espacio con el que se POBLÓ, en vez de re-sondear Ollama en caliente.
    os.environ.setdefault("ZAELAR_EMBED_BACKEND", "ollama")
    # carga las keys (OPENAI_API_KEY para el reranker OpenAI) igual que server/common.py
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env", override=False)
        load_dotenv(REPO / ".meshkore" / "credentials" / "zaelar.env", override=False)
    except Exception:
        pass


def _long_queries() -> list[dict]:
    """Queries de recall-largo del corpus. Excluye `stale_by_design` (V2-031, 2026-08-17): casos cuyo `want`
    es correcto POSICIONALMENTE (justo tras escribirse, que es como los corre el bot suite normal) pero deja
    de serlo contra el ESTADO FINAL — una batería POSTERIOR no relacionada supersede el mismo slot con otro
    propósito (encontrado con teléfono/móvil: la GOLD reutiliza operator.phone/operator.hardware en más de un
    sitio). No es un bug de memoria (el supersede "más reciente manda" es correcto); es un desajuste entre
    cómo se autoraron esas dos aserciones y cómo mide scale_eval (contra el final, no contra el momento)."""
    from tests.memory.e2e.bot import cases as C
    return [c for c in C.CASES
            if c.get("t") == "query" and c.get("via") == "long" and c.get("want") and not c.get("stale_by_design")]


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


def _superseded_blob() -> str:
    """Texto de recuerdos INVALIDADOS cuyo `slot` tiene HOY una fila VÁLIDA (V2-031, 2026-08-17): el writer
    garantiza como mucho 1 fila válida por slot, así que si el slot sigue teniendo una fila válida, cualquier
    fila inválida con ese MISMO slot fue una SUPERSESIÓN real (el "más reciente manda" del writer funcionando
    correctamente), no una pérdida de datos. Corpus con slots como `operator.car`/`operator.job`/
    `operator.hardware`/`operator.name`/`operator.phone` acumulan hasta 15 valores a lo largo de la batería
    (baterías de sesiones distintas testeando "el valor actual" sin saber que otra sesión seguiría cambiándolo
    después) — sin esto, cada valor intermedio se contaba como "write miss" contra el estado FINAL. Detectado a
    mano varias veces (Toyota/Ford/Deloitte/profesor/Juncadella/Richi) antes de generalizarlo aquí."""
    from memory import db as _db
    d = _db.get_db()
    valid_slots = {r["slot"] for r in d.query(
        "SELECT DISTINCT slot FROM memories WHERE valid=1 AND slot IS NOT NULL")}
    if not valid_slots:
        return ""
    ph = ",".join("?" * len(valid_slots))
    rows = d.query(f"SELECT text FROM memories WHERE valid=0 AND slot IN ({ph})", tuple(valid_slots))
    return "\n".join(_norm(r["text"]) for r in rows)


def _is_stored(wants: list[str], blob: str) -> bool:
    return any(_norm(w) in blob for w in wants)


def evaluate(limit: int = 10) -> dict:
    """Corre todas las queries de recall-largo por `retriever.search` y agrega recall@k/MRR/latencia. Excluye,
    ANTES de medir, las queries cuyo `want` solo aparece en un valor de slot ya legítimamente superado (ver
    `_superseded_blob`) — no serían justas contra el estado final del corpus con ningún retriever."""
    from memory import retriever

    blob = _durable_blob()             # snapshot para clasificar write vs retrieval
    superseded = _superseded_blob()
    qs = []
    superseded_excluded = 0
    for c in _long_queries():
        if not _is_stored(c["want"], blob) and _is_stored(c["want"], superseded):
            superseded_excluded += 1
            continue
        qs.append(c)
    n = len(qs)
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
        "superseded_excluded": superseded_excluded,
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
    # V2-114 F1 — la cinta del destilador. `--record` graba lo que el CORAZÓN decide (una vez, ~90 min);
    # `--replay` lo repite sin red en segundos. Ver `distiller_tape.py` para el porqué de la cinta secuencial.
    ap.add_argument("--record", metavar="PATH", default=None,
                    help="con --fresh: graba las decisiones del destilador a un fixture reutilizable")
    ap.add_argument("--replay", metavar="PATH", default=None,
                    help="con --fresh: repuebla replicando un fixture en vez de llamar al LLM (rápido, gratis)")
    args = ap.parse_args()
    if args.record and args.replay:
        ap.error("--record y --replay son excluyentes")
    if (args.record or args.replay) and not args.fresh:
        ap.error("--record/--replay solo tienen sentido con --fresh (es la fase de repoblación lo que se graba)")
    _setup_env()

    if args.fresh:
        import asyncio as _asyncio

        from tests.memory.e2e.bot import runner
        from tests.memory.e2e.bot import distiller_tape as _tape

        def _populate():
            # fix 2026-07-20: la API real del runner es la corrutina run_range, no un run() síncrono inexistente.
            _asyncio.run(runner.run_range(0, 10_000, fresh=True))

        if args.replay:
            with _tape.replay(args.replay) as t:
                _populate()
            st = t.stats()
            print(f"⏹  cinta: {st['hits']} aciertos · {st['misses']} sin entrada · "
                  f"cobertura {st['coverage']:.1%}" + (f" · {st['out_of_order']} fuera de orden"
                                                       if st["out_of_order"] else ""))
            if st["misses"]:
                print(f"   ⚠️  {st['misses']} frases sin entrada cayeron a la HEURÍSTICA — el número de esta "
                      f"corrida NO es comparable con uno de cinta completa")
        elif args.record:
            print("⟳ repoblando la persona (--fresh + --record, corpus completo, con LLM real)…")
            with _tape.record(args.record):
                _populate()
        else:
            print("⟳ repoblando la persona (--fresh, corpus completo)…")
            _populate()

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
