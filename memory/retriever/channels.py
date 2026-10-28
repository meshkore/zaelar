"""The retriever's channels: scoring constants, the lanes, vector / paraphrase / FTS search, RRF and recency."""
import math
import os
import re
import struct

from .. import db as _db

# Score weights (tunable per profile).
ALPHA = 0.45   # semantic relevance (fusion)
BETA = 0.25    # recency
GAMMA = 0.20   # importance
DELTA = 0.10   # use weight
RRF_K = 60
RECENCY_HALFLIFE_DAYS = 7.0

# Candidate pool BEFORE RRF (V2-031 T2: 40 → 100). The reranker only cross-encodes its own `top_n` after fusion,
# so a wider pool gives RRF more surface without making the cross-encoder dearer.
POOL_K = int(os.getenv("ZAELAR_RETRIEVER_POOL_K", "100"))

_FTS_TOKEN = re.compile(r"\w+", re.UNICODE)


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _fts_query(prompt: str) -> str:
    """Free prompt → a safe FTS5 query: an OR of tokens with PREFIX STEMS (no syntax errors).

    Spanish is highly inflected and the writer canonicalises person/tense («estoy aprendiendo» → «aprende»), so the
    query's exact token misses the stored one. Content tokens (≥5) are cut to 6 chars + `*` («aprend*» matches
    aprende/aprendiendo/aprender). It only widens the FTS channel; RRF + the vector channel keep precision.
    Stopwords and very short tokens are dropped (a `de*` would match everything)."""
    terms: list[str] = []
    for t in _FTS_TOKEN.findall(prompt.lower()):
        if t in _FTS_STOP:
            continue
        if len(t) >= 5:
            terms.append(f"{t[:6]}*")        # prefix stem (6 chars) → covers Spanish inflection
        elif len(t) >= 3:
            terms.append(f'"{t}"')           # short content token (numbers, acronyms) → exact
    return " OR ".join(terms)


# ES/EN stopwords (function words + META recall verbs, not content), kept out of FTS.
# ⚠️ The recall verbs («recuerdas», «dime», «sabes») are META, not the fact sought: unfiltered, «recuer*» matches
# every «recuérdame…» in the store and BURIES the real answer.
_FTS_STOP = frozenset(
    "de la el los las un una unos unas y o a en con por para del al es son era mi mis tu tus su sus me te se "
    "lo le nos os que qué cual cuál como cómo donde dónde cuando cuándo mas más pero si sí no ni ya "
    "va van voy vas vais esta estan están estoy estas estás estamos ando anda andas hay ha han he has "
    "recuerdas recuerda recuérdame recuerdame acuerdas acuerda acuerdo dime dímelo sabes cuéntame cuentame "
    "cuenta quién quien qué hago hice había tengo tienes tuve algún alguna algo cosa "
    "the of to in on at is are was for and or my your his her remember recall tell know what did do i you".split()
)


# ── LANES (V2-802 T-03) ──────────────────────────────────────────────────────────────────────────────────
# Inbound messages (`kind='msg'`: what OTHER people wrote) and the operator's own memory are two questions; in one
# pool the inbox wins by volume. The lane is applied INSIDE each channel (a top-K the inbox already filled cannot
# be fixed by filtering afterwards), and `all` never fuses them: own lane first, then the message lane.
#   · `own`      — everything except inbound messages (the operator-fact recall: turn recall, worker dossier).
#   · `messages` — only inbound messages.
#   · `all`      — own lane, then message lane; a message never outranks an own row.
LANE_OWN = "own"
LANE_MESSAGES = "messages"
LANE_ALL = "all"
_VEC_LANE_OVERFETCH = 4     # vec0 KNN cannot take a JOIN (see vec_search_paraphrases): over-fetch, then filter


def _lane_sql(lane: str, col: str = "kind") -> str:
    """The SQL condition that keeps a row in `lane` ('' for `all`). One home for the rule, read by every channel."""
    if lane == LANE_OWN:
        return f"{col} != 'msg'"
    if lane == LANE_MESSAGES:
        return f"{col} = 'msg'"
    return ""


def _keep_lane(pairs: list[tuple[int, float]], lane: str, k: int) -> list[tuple[int, float]]:
    """Filter a ranked (id, score) list to `lane`, keeping its order, capped at `k`."""
    cond = _lane_sql(lane)
    if not cond or not pairs:
        return pairs[:k]
    ids = [p[0] for p in pairs]
    ph = ",".join("?" * len(ids))
    keep = {r["id"] for r in _db.get_db().query(f"SELECT id FROM memories WHERE id IN ({ph}) AND {cond}", ids)}
    return [p for p in pairs if p[0] in keep][:k]


def vec_search(query_vec: list[float], k: int = POOL_K, lane: str = "all") -> list[tuple[int, float]]:
    db = _db.get_db()
    if not db.vec_available:
        return []
    try:
        fetch = k if lane == "all" else k * _VEC_LANE_OVERFETCH
        rows = db.query(
            "SELECT memory_id, distance FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (_pack(query_vec), fetch),
        )
        return _keep_lane([(r["memory_id"], r["distance"]) for r in rows], lane, k)
    except Exception:
        return []


def vec_search_paraphrases(query_vec: list[float], k: int = POOL_K, lane: str = "all") -> list[tuple[int, float]]:
    """V2-031 T2: `vec_search()` over `vec_paraphrases`, mapped back to the REAL `memory_id` via `paraphrase_index`.
    A paraphrase is never a result by itself — one more ranked list for `rrf()`, so a pill matched by its own
    vector AND a paraphrase accumulates both signals."""
    db = _db.get_db()
    if not db.vec_available:
        return []
    try:
        # sqlite-vec needs the `LIMIT`/`k=?` ON the KNN query itself — a JOIN in the same query breaks the KNN plan
        # (`OperationalError: A LIMIT or 'k = ?' constraint is required`). Two steps: bare KNN, then map ids.
        hits = db.query(
            "SELECT id, distance FROM vec_paraphrases WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (_pack(query_vec), k if lane == "all" else k * _VEC_LANE_OVERFETCH),
        )
        if not hits:
            return []
        pids = [h["id"] for h in hits]
        placeholders = ",".join("?" * len(pids))
        rows = db.query(
            f"SELECT id, memory_id FROM paraphrase_index WHERE id IN ({placeholders})", pids)
        mid_by_pid = {r["id"]: r["memory_id"] for r in rows}
        return _keep_lane([(mid_by_pid[h["id"]], h["distance"]) for h in hits if h["id"] in mid_by_pid], lane, k)
    except Exception:
        return []


def fts_search(prompt: str, k: int = POOL_K, lane: str = "all") -> list[tuple[int, float]]:
    db = _db.get_db()
    if not db.fts_available:
        return []
    q = _fts_query(prompt)
    if not q:
        return []
    try:
        cond = _lane_sql(lane, "m.kind")
        if cond:
            # The lane goes INSIDE the top-K: FTS5 ranks in the same query as the JOIN, so the K slots are spent
            # on rows of this lane only.
            rows = db.query(
                "SELECT f.rowid AS rowid, bm25(fts_memories) AS rank FROM fts_memories f "
                f"JOIN memories m ON m.id = f.rowid WHERE fts_memories MATCH ? AND {cond} ORDER BY rank LIMIT ?",
                (q, k),
            )
        else:
            rows = db.query(
                "SELECT rowid, bm25(fts_memories) AS rank FROM fts_memories "
                "WHERE fts_memories MATCH ? ORDER BY rank LIMIT ?",
                (q, k),
            )
        return [(r["rowid"], r["rank"]) for r in rows]
    except Exception:
        return []


def rrf(*ranked_lists: list[tuple[int, float]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal Rank Fusion. Each list is ordered best→worst; the score is Σ 1/(k+rank)."""
    scores: dict[int, float] = {}
    for lst in ranked_lists:
        for rank, (mid, _) in enumerate(lst, start=1):
            scores[mid] = scores.get(mid, 0.0) + 1.0 / (k + rank)
    return scores


def _recency(last_access: int | None, now: int) -> float:
    if not last_access:
        return 0.0
    days = max(0.0, (now - last_access) / 86400.0)
    return math.pow(2.0, -days / RECENCY_HALFLIFE_DAYS)
