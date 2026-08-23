"""memory/consolidator.py — el "sueño" de la memoria (V2-002 · T49).

Job periódico, SIN prisa (lo dispara el loop orquestador en V2-005: diario/horario/por tamaño). Comprime,
deduplica, aplica el decay temporal y borra por peso SOLO si se supera el límite de almacenamiento — nunca los
`pinned`. Respaldado por investigación 2026 (curva de Ebbinghaus, FadeMem).

Piezas (deterministas, sin LLM aquí — la compresión SEMÁNTICA por clustering la aporta el agente de memoria
del SlowBrain en V2-006 vía el hook `summarize_fn`):

  - `promote(...)`   — corto viejo → 'mid'; mid viejo → 'long' (por edad). Con `summarize_fn` opcional, agrupa
                       y resume (pluggable; V2-006).
  - `dedup(...)`     — fusiona recuerdos de texto idéntico (normalizado): conserva el de mayor peso, transfiere
                       aristas y acceso, borra los demás. (La dedup por similitud de embedding es opcional.)
  - `decay(...)`     — `weight *= e^(−λ·Δt)` para los NO accedidos (λ≈0.001/día). El acceso RESETEA el decay
                       porque usa Δt desde `last_access` (que `reinforce` pone a now).
  - `evict(limit)`   — mientras `nº recuerdos > limit`, borra el de MENOR peso que NO esté pinned. Con espacio
                       de sobra no borra nada. NUNCA borra pinned.
  - `consolidate()`  — orquesta promote → dedup → decay → evict y devuelve un informe.
"""
import logging
import math
import re
import time

from . import db as _db
from . import writer as _writer

_log = logging.getLogger("zaelar.memory.consolidator")

DECAY_LAMBDA_PER_DAY = 0.001     # vida media ≈ 693 días a este λ; el consolidador lo puede subir por tipo
DEFAULT_LIMIT = 50_000           # techo de recuerdos antes de empezar a olvidar por peso
SHORT_TO_MID_DAYS = 2.0
MID_TO_LONG_DAYS = 30.0

_WS = re.compile(r"\s+")


def _now() -> int:
    from .clock import now
    return now()


def _norm(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


# ── decay ──────────────────────────────────────────────────────────────────────────────────────────────
def _kv_get(key: str) -> str | None:
    db = _db.get_db()
    db.execute("CREATE TABLE IF NOT EXISTS sys_kv (key TEXT PRIMARY KEY, value TEXT)")
    row = db.query_one("SELECT value FROM sys_kv WHERE key=?", (key,))
    return row["value"] if row else None


def _kv_set(key: str, value: str) -> None:
    db = _db.get_db()
    db.execute("CREATE TABLE IF NOT EXISTS sys_kv (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("INSERT INTO sys_kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, value))


def decay(now: int | None = None, lam: float = DECAY_LAMBDA_PER_DAY) -> int:
    """Decay Ebbinghaus por VENTANA: `weight *= e^(−λ·Δt)` con Δt = días sin acceso DENTRO de la ventana desde el
    ÚLTIMO ciclo de decay (marcador `sys_kv.decay_last_run`). Fix auditoría 2026-07-19: la versión anterior
    recomponía e^(−λ·días_desde_last_access) EN CADA ciclo (horario) sin tocar last_access → sobre-decay ~24×/día
    (una píldora idle 30 días perdía ~51% de peso POR DÍA en vez de la vida media de 693 días). Ahora cada tramo de
    inactividad se descuenta UNA sola vez: Δt = now − max(last_access, último_ciclo). Una sola sentencia SQL (exp()
    nativo) → el lock dura ms, no O(N) statements (el sueño ya no congela las lecturas calientes)."""
    db = _db.get_db()
    now = now or _now()
    last_run = _kv_get("decay_last_run")
    if last_run is None:
        # primer ciclo con marcador: inicializa SIN decaer (conservador — evita un último golpe retroactivo
        # sobre el stock, que ya viene sobre-decaído por el bug)
        _kv_set("decay_last_run", str(now))
        return 0
    last_run_i = int(float(last_run))
    if now <= last_run_i:
        return 0
    with db.cursor() as cur:
        cur.execute(
            "UPDATE memories SET weight = weight * exp(-? * ((? - max(last_access, ?)) / 86400.0)) "
            "WHERE last_access IS NOT NULL AND ? - max(last_access, ?) > 0",
            (lam, now, last_run_i, now, last_run_i),
        )
        n = cur.rowcount
    _kv_set("decay_last_run", str(now))
    return n


# ── eviction por peso ────────────────────────────────────────────────────────────────────────────────────
def count() -> int:
    return _db.get_db().query_one("SELECT COUNT(*) c FROM memories")["c"]


# Un hecho es SALIENTE (parte del "perfil" que un humano no olvida bajo presión) si es importante, o es un dato
# canónico singular (tiene `slot`: nombre/ubicación/objetivo…), o es identidad/preferencia. La eviction lo respeta
# hasta el final: primero se van la charla y la trivia. SOTA 2026 ("el problema de consolidación"): evictar hechos
# salientes ERODE la confianza — un buen consolidador tira lo de bajo valor, no el nombre del perro.
_SALIENT_IMPORTANCE = 0.5


def evict(limit: int = DEFAULT_LIMIT) -> int:
    """Mientras se supere `limit`, borra el recuerdo de MENOR valor que NO esté pinned. Orden de sacrificio:
    primero lo NO saliente (trivia/charla), y solo si no queda otra, lo saliente. NUNCA borra pinned. Así una poda
    agresiva conserva el PERFIL (nombre/dieta/mascota…) y descarta el ruido — no al revés (SOTA: consolidation
    problem)."""
    db = _db.get_db()
    removed = 0
    while count() > limit:
        # `salient` = 1 si (importante | tiene slot | identidad/preferencia). Ordena por saliente ASC → los NO
        # salientes (0) se van primero; a igualdad, menor peso y más antiguo. Solo se toca lo saliente si ya no
        # queda trivia que tirar.
        row = db.query_one(
            "SELECT id FROM memories WHERE pinned=0 ORDER BY "
            "(CASE WHEN importance >= ? OR slot IS NOT NULL OR kind IN ('profile','pref') THEN 1 ELSE 0 END) ASC, "
            "weight ASC, last_access ASC LIMIT 1",
            (_SALIENT_IMPORTANCE,),
        )
        if row is None:  # solo quedan pinned → no se puede bajar más; parar (nunca borrar pinned)
            break
        _writer.delete_memory(row["id"])
        removed += 1
    return removed


# ── dedup ──────────────────────────────────────────────────────────────────────────────────────────────
def dedup() -> int:
    """Fusiona recuerdos de texto idéntico (normalizado). Conserva el de mayor peso; transfiere aristas. Devuelve nº borrados."""
    db = _db.get_db()
    rows = db.query("SELECT id, text, weight, access_count, pinned FROM memories WHERE valid=1")
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(_norm(r["text"]), []).append(r)
    removed = 0
    for _key, members in groups.items():
        if len(members) < 2:
            continue
        # conserva el de mayor (pinned, weight, access_count); borra el resto.
        members.sort(key=lambda m: (m["pinned"], m["weight"], m["access_count"]), reverse=True)
        keep = members[0]
        for dup in members[1:]:
            # reengancha las aristas del duplicado al superviviente
            with db.cursor() as cur:
                cur.execute("UPDATE OR IGNORE edges SET from_id=? WHERE from_id=?", (keep["id"], dup["id"]))
                cur.execute("UPDATE OR IGNORE edges SET to_id=? WHERE to_id=?", (keep["id"], dup["id"]))
            _writer.delete_memory(dup["id"])
            removed += 1
        # el superviviente hereda un empujón de acceso (se usó "más veces")
        _writer.reinforce([keep["id"]], step=0.0)
    return removed


# ── promoción por edad (compresión estructural; la semántica va en V2-006) ────────────────────────────────
def promote(now: int | None = None, summarize_fn=None) -> dict:
    """Corto viejo → 'mid'; mid viejo → 'long'. `summarize_fn(list[text])->text` opcional (clustering, V2-006)."""
    db = _db.get_db()
    now = now or _now()
    short_cut = now - int(SHORT_TO_MID_DAYS * 86400)
    mid_cut = now - int(MID_TO_LONG_DAYS * 86400)
    with db.cursor() as cur:
        # El BUFFER CONVERSACIONAL (`kind='conv'`) NUNCA se promociona a durable: es el turno crudo efímero (TTL 2d),
        # no un recuerdo — el CORAZÓN ya destiló lo memorable en píldoras aparte. Además no lleva vector (writer:
        # optimización 2026-07-12), así que promocionarlo dejaría un durable sin embedding (irrecuperable por vector).
        cur.execute("UPDATE memories SET level='mid', updated=? WHERE level='short' AND kind!='conv' AND created < ?",
                    (now, short_cut))
        to_mid = cur.rowcount
        cur.execute("UPDATE memories SET level='long', updated=? WHERE level='mid' AND created < ?",
                    (now, mid_cut))
        to_long = cur.rowcount
    # gancho de compresión semántica (V2-006): no-op por defecto.
    if summarize_fn is not None:
        summarize_fn  # documenta el punto de extensión sin ejecutar nada por ahora
    return {"short_to_mid": to_mid, "mid_to_long": to_long}


# ── orquestación ─────────────────────────────────────────────────────────────────────────────────────────
def heal_slots() -> dict:
    """Saneo de SLOTS (auditoría 2026-07-14). Dos pasadas deterministas, idempotentes:

    (1) NORMALIZA slots legacy al canónico (`writer.canon_slot`): filas escritas ANTES de la normalización del
        writer (alias 'location'/'ubicación', mayúsculas en namespaced `cluster:X:Y`) quedaban como linajes
        huérfanos que ninguna escritura nueva volvería a superseder.
    (2) COLAPSA multi-vigentes: si un slot tiene 2+ filas `valid=1` (alias recién unificados, unforget, legacy),
        conserva la más reciente y marca el resto `valid=0, superseded_by` — "el más reciente MANDA", también
        hacia atrás. Es la pareja del supersede auto-curativo del writer, para el stock ya existente."""
    db = _db.get_db()
    now = _now()
    normalized = 0
    for r in db.query("SELECT DISTINCT slot FROM memories WHERE slot IS NOT NULL"):
        s = r["slot"]
        c = _writer.canon_slot(s)
        if c and c != s:
            db.execute("UPDATE memories SET slot=? WHERE slot=?", (c, s))
            normalized += 1
    collapsed = 0
    dup_slots = db.query(
        "SELECT slot FROM memories WHERE valid=1 AND slot IS NOT NULL GROUP BY slot HAVING COUNT(*) > 1")
    for r in dup_slots:
        rows = db.query("SELECT id FROM memories WHERE slot=? AND valid=1 ORDER BY updated DESC, id DESC",
                        (r["slot"],))
        keep = int(rows[0]["id"])
        stale = [int(x["id"]) for x in rows[1:]]
        if stale:
            ph = ",".join("?" * len(stale))
            db.execute(f"UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? "
                       f"WHERE id IN ({ph})", (keep, now, now, *stale))
            collapsed += len(stale)
    return {"normalized": normalized, "collapsed": collapsed}


PRUNE_INVALID_AFTER_DAYS = float(2.0)   # días tras los que una cáscara valid=0 sale de los ÍNDICES (no de la BD)


def prune_invalid(now: int | None = None, after_days: float = PRUNE_INVALID_AFTER_DAYS) -> int:
    """Saca de los ÍNDICES (vec + FTS) las cáscaras `valid=0` viejas — la fila de `memories` SE CONSERVA (regla de
    oro: nunca se borra el histórico). Auditoría 2026-07-19 (P2-6): cada supersede dejaba su vector y su fila FTS
    vivos PARA SIEMPRE → los k=40 candidatos del retriever se llenaban de cáscaras (weather:soria = 56 filas, 55
    muertas) y el brute-force pagaba filas basura. Idempotente: marca `meta.pruned=1` para no re-podar."""
    db = _db.get_db()
    now = now or _now()
    cutoff = now - int(after_days * 86400)
    rows = db.query(
        "SELECT id, text, meta FROM memories WHERE valid=0 AND pinned=0 AND updated < ? "
        "AND (meta IS NULL OR meta NOT LIKE '%\"pruned\": 1%')",
        (cutoff,),
    )
    import json as _json
    pruned = 0
    for r in rows:
        try:
            # The paraphrase index is the THIRD index, and this function never knew about it (2026-08-18). This
            # is the same defect P2-6 fixed for vec+FTS in 2026-07-19, one table later: a superseded shell's
            # paraphrase vectors stay alive forever, keep winning KNN slots, and map back to a `valid=0` row the
            # reader will discard — pool budget spent on the dead, which is exactly what this function exists to
            # stop. Note this path DE-INDEXES (the `memories` row is preserved on purpose: history is never
            # deleted); `writer.delete_memory` is the one that really deletes, and it calls the same helper.
            _writer.drop_paraphrases(r["id"])
            with db.cursor() as cur:
                cur.execute("DELETE FROM vec_memories WHERE memory_id=?", (r["id"],))
                try:
                    # FTS5 external-content: el borrado del índice exige el comando 'delete' CON el texto original.
                    cur.execute("INSERT INTO fts_memories(fts_memories, rowid, text) VALUES ('delete', ?, ?)",
                                (r["id"], r["text"]))
                except Exception:
                    pass  # fila sin entrada FTS (p. ej. ya podada a medias) — seguir
                meta = _json.loads(r["meta"] or "{}")
                meta["pruned"] = 1
                cur.execute("UPDATE memories SET meta=? WHERE id=?",
                            (_json.dumps(meta, ensure_ascii=False), r["id"]))
            pruned += 1
        except Exception:
            continue
    return pruned


def expire_ttl(now: int | None = None) -> int:
    """Invalidate expired non-pinned memories according to ``created + ttl_days``.

    TTL was part of the schema and writer contract but was previously never
    enforced. Expiration is soft: the historical row remains auditable and its
    search indexes are pruned by the normal invalid-row phase.
    """
    db = _db.get_db()
    now = now or _now()
    with db.cursor() as cur:
        cur.execute(
            "UPDATE memories SET valid=0, updated=?, invalidated_at=? "
            "WHERE valid=1 AND pinned=0 AND ttl_days IS NOT NULL "
            "AND created + CAST(ttl_days * 86400 AS INTEGER) <= ?",
            (now, now, now),
        )
        return cur.rowcount


def consolidate(limit: int = DEFAULT_LIMIT, lam: float = DECAY_LAMBDA_PER_DAY, summarize_fn=None,
                now: int | None = None, prune_workers_fn=None) -> dict:
    """Un ciclo de "sueño" LIGERO: heal_slots → promote → dedup → decay → prune → evict. Devuelve el informe.
    No es hot path. (El sueño PROFUNDO —dedup semántico + síntesis/insights, la fase REM— vive en
    `memory/rem.py` y lo dispara el loop con su propia cadencia.)"""
    now = now or _now()
    healed = heal_slots()
    promoted = promote(now=now, summarize_fn=summarize_fn)
    deduped = dedup()
    decayed = decay(now=now, lam=lam)
    expired = expire_ttl(now=now)
    pruned = prune_invalid(now=now)
    evicted = evict(limit=limit)
    # V2-079: el mismo barrido del sueño limpia el LEDGER de Brain Workers — borra ejecuciones terminadas viejas
    # (>7d por defecto), como el decay/evict de la memoria; las ligadas a un cron activo (recurrentes) no caducan.
    #
    # INYECTADO (auditoría de arquitectura 2026-08-23), no importado. El comentario que había aquí decía «la
    # memoria no importa `nucleo/*`» y a la línea siguiente importaba `nucleo.workers.ledger` — perezoso y
    # fail-open, pero un import inverso igual: el paquete dejaba de ser autónomo por una tarea de higiene que ni
    # siquiera es suya. Es el patrón que `rem.py` ya vive con sus hooks de LLM, y el llamante que lo inyecta
    # (`nucleo/loop.py`) es el mismo que inyecta aquéllos.
    #
    # **Sin hook, `workers_pruned` es None y NO 0**: cero dice «miré y no había nada que limpiar», None dice
    # «nadie me dio con qué mirar». Son hechos distintos y confundirlos es cómo una función se pierde en
    # silencio — un llamante que olvide inyectar vería un informe perfectamente normal mientras el ledger crece
    # sin límite. Fail-open se mantiene: un hook que reviente no tumba el ciclo de consolidación.
    workers_pruned = None
    if prune_workers_fn is not None:
        try:
            workers_pruned = prune_workers_fn(now=now)
        except Exception as e:  # noqa: BLE001
            _log.debug("consolidate: el hook de limpieza del ledger falló (%s)", e)
    return {
        "healed_slots": healed,
        "promoted": promoted,
        "deduped": deduped,
        "decayed": decayed,
        "expired": expired,
        "pruned": pruned,
        "evicted": evicted,
        "workers_pruned": workers_pruned,
        "count": count(),
    }
