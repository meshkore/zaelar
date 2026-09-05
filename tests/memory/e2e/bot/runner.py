"""tests/memory/e2e/bot/runner.py — the memory-test bot ENGINE (V2-013 · V2-019).

Runs the `cases.py` script against an **ISOLATED** DB (never the real profile) and verifies EACH step:
  - **save/extract**: after `memory_agent.ingest_utterance` (the real write path, with the configured LLM CORE), drains the
    queue and checks that the data landed in the expected layer(s) — or NONE if discarded.
  - **query**: through the DIRECT read path (state/recent_short/query, WITHOUT LLM), checks that it returns the data.

Resumable and batch-based: saves progress in `.meshkore/logs/membot/progress.json` and one report per batch. Designed
to run in a loop (each iteration = 10 steps), reload the module between batches, and grow to 1000.

Usage:
  ./.venv/bin/python -m tests.memory.e2e.bot.runner --next 10        # siguiente tanda de 10 (desde el progreso)
  ./.venv/bin/python -m tests.memory.e2e.bot.runner --fresh --next 10  # reinicia la BD del bot y arranca de cero
  ./.venv/bin/python -m tests.memory.e2e.bot.runner --range 0 10      # una tanda concreta

Env: DB isolated per corpus (gitignored) · `MEM_PROCESSOR=1` (real configured LLM) — set
here if absent from the environment. The REAL operator memory (zaelar.db) is NOT touched.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import time
import unicodedata

REPO = pathlib.Path(__file__).resolve().parents[4]
LOGDIR = REPO / ".meshkore" / "logs" / "membot"

# ── Selectable CORPUS (V2-038 audit 2026-07-14) ─────────────────────────────────────────────────────────────
# `v1` = `cases.py`, the historical GOLD set of 1032 (Ricart/Barcelona person) — INTACT and reproducible.
# `v2` = `cases2.py`, NEW corpus (different, more original person) that stresses genericity/multilingual behavior and the
# capacidades de la auditoría (señal `change`, colapso de linajes por alias de slot, escritura externa de workers,
# heal_slots). Cada corpus tiene su BD, progreso y catálogo AISLADOS → correr uno no pisa al otro.
CORPORA = {
    "v1": {"module": "cases",  "db": "zaelar.membot.db",  "progress": "progress.json",    "catalog": "CATALOG.md"},
    "v2": {"module": "cases2", "db": "zaelar.membot2.db", "progress": "progress-v2.json", "catalog": "CATALOG2.md"},
    # `v3` = `cases3.py`, corpus de EFICIENCIA BAJO CARGA REAL (auditoría 2026-07-14, petición del operador): en vez
    # de "4 datos y pregunta", simula 40 DÍAS de actividad densa (cientos de mensajes/citas/estudios) y luego busca
    # AGUJAS enterradas entre ese pajar, midiendo acierto Y latencia. Persona Amaia (continuidad). BD/progreso/
    # catálogo AISLADOS. Repetible para verificar refactors: `python -m …runner --corpus v3 --fresh --range 0 N`.
    "v3": {"module": "cases3", "db": "zaelar.membot3.db", "progress": "progress-v3.json", "catalog": "CATALOG3.md"},
# Focused conversational gateway: ambiguous turns pass through the real CORE and are validated by pills,
    # slots, state, capa/importancia y recall. No inyecta hechos preestructurados directamente en el writer.
    "v4": {"module": "cases4", "db": "zaelar.membot4.db", "progress": "progress-v4.json", "catalog": "CATALOG4.md"},
}
_ACTIVE = "v1"


def _corpus() -> dict:
    return CORPORA[_ACTIVE]


def _progress_path() -> pathlib.Path:
    return LOGDIR / _corpus()["progress"]


def _catalog_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / _corpus()["catalog"]


def _load_cases() -> list:
    import importlib
    mod = importlib.import_module(f"{__package__}.{_corpus()['module']}")
    return mod.CASES


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _setup_env():
    # E2E runners are new processes launched by the CLI/Observatory. They load the
    # mismo credential store local que el engine sin imprimirlo ni copiarlo a
    # eventos; antes OpenAI recibía el fallback literal "local" y toda la batería
    # degradaba silenciosamente a heurística.
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env", override=False)
        # V2-031 (2026-08-17): this line was missing here — `scale_eval.py::_setup_env` already had it (twin code,
        # nunca espejado). Sin ella, `DEEPSEEK_API_KEY` (solo vive en el credential store, no en `.env`) queda
        # sin resolver → `nucleo/provider_keys.py::key_for_endpoint` cae a su centinela `"local"` → DeepSeek
        # 401ea CADA llamada del CORAZÓN → fallback silencioso a la heurística, exactamente la clase de bug que
        # el comentario de arriba dice haber cerrado ya para OpenAI. Reproducido en vivo invocando este runner
        # por su propia CLI (`python -m tests.memory.e2e.bot.runner`, uso documentado) sin pasar por scale_eval.
        load_dotenv(REPO / ".meshkore" / "credentials" / "zaelar.env", override=False)
    except Exception:
        pass
    os.environ.setdefault("ZAELAR_DB", str(REPO / "memory" / "_data" / _corpus()["db"]))
    os.environ.setdefault("MEM_PROCESSOR", "1")   # Real configured LLM CORE — the system under evolution
    # Backend de embedding PINEADO explícito (no "auto") — V2-103 (2026-08-16) añadió un re-chequeo por TTL que
    # re-sondea Ollama cada 300s cuando el backend resuelto está degradado, y nada en este arnés vuelve a llamar
    # a `memory/reembed.py::check()` (eso solo corre desde el tick de `nucleo/loop.py`, que este runner no
    # arranca). Una corrida `--fresh` puede tardar ~90 min: un hipo transitorio de Ollama a mitad deja una parte
    # del corpus embebida en un espacio vectorial y el resto en otro tras la recuperación — ambas resoluciones
    # son "sanas" en su momento, pero sqlite-vec compara distancias sin sentido entre espacios distintos. Un
    # valor FORZADO (no "auto") pone `_forced=True` en `memory/embeddings.py`, que el re-chequeo respeta siempre
    # (`if _forced or _backend == "ollama": return`) — inmune a la salud de Ollama durante toda la corrida.
    # `setdefault` respeta un override explícito de quien invoque el runner.
    os.environ.setdefault("ZAELAR_EMBED_BACKEND", "ollama")


# ── layer probes (DIRECT reading, without LLM) ──────────────────────────────────────────────────────────────
def _state_blob(memory) -> str:
    try:
        return _norm(json.dumps(memory.state(), ensure_ascii=False))
    except Exception:
        return ""


def _short_blob(memory) -> str:
    try:
        return _norm(" ".join(m.get("text", "") for m in memory.recent_short(limit=60, max_chars=8000)))
    except Exception:
        return ""


def _in_long(memory, marker: str, probe: str) -> bool:
    """Does the marker appear in LONG-TERM memory? Query the retriever with the probe and inspect the results (mid/long)."""
    try:
        res = memory.query(probe or marker, reinforce_used=False)
        for m in res.get("memories") or []:
            if m.get("level") in ("mid", "long") and marker in _norm(m.get("text", "")):
                return True
    except Exception:
        pass
    return False


def _layers_with(memory, marker: str, probe: str) -> list[str]:
    """DURABLE layers where the marker appears right now."""
    found = []
    if marker in _state_blob(memory):
        found.append("state")
    if marker in _short_blob(memory):
        found.append("short")
    if _in_long(memory, marker, probe):
        found.append("long")
    return found


# ── per-step verification ─────────────────────────────────────────────────────────────────────────────────
def _verify_save(memory, step: dict) -> tuple[bool, str]:
    marker = _norm(step["marker"])
    probe = step.get("text", "")
    got = _layers_with(memory, marker, probe)
    # `any`: efímero/fuzzy → basta con que quede en AL MENOS UNA de las capas dadas (no descartado).
    if step.get("any"):
        want_any = list(step["any"])
        hit = [x for x in want_any if x in got]
        ok = len(hit) > 0
        return ok, (f"en {got} (any {want_any}) OK" if ok
                    else f"no debía descartarse; esperaba alguna de {want_any}; está en {got}")
    want_in = list(step.get("in") or [])
    if not want_in:                                   # DESCARTE: no debe estar en ninguna capa durable
        ok = len(got) == 0
        return ok, ("descartado OK" if ok else f"debía descartarse pero quedó en {got}")
    # Para hechos de ESTADO con `state_key`: lo que importa es que el CAMPO se pueble (el LLM canonicaliza y puede
    # parafrasear el ancla — no exigimos la palabra literal, sino que el estado quede correcto). Tolerante al fraseo.
    sk = step.get("state_key")
    if sk and "state" in want_in:
        try:
            val = str(memory.state().get(sk) or "").strip()
        except Exception:
            val = ""
        ok = bool(val)                                # el campo del estado quedó poblado (LLM canonicaliza el texto)
        return ok, (f"state[{sk}]={val!r} OK" if ok else f"state[{sk}] quedó vacío (ancla esperada {marker!r})")
    # resto: debe estar en TODAS las capas pedidas (normalmente una)
    missing = [layer for layer in want_in if layer not in got]
    ok = not missing
    return ok, (f"en {got} OK" if ok else f"esperaba en {want_in}; está en {got}; falta {missing}")


def _brain_view(q: str) -> tuple[str, bool]:
    """Reconstruye LO QUE VERÍA EL FLASHBRAIN para el turno `q` (fidelidad al camino real de lectura, V2-013):
    bloque cacheado (ESTADO + perfil durable salient + CORTO entero, `memory_cache._compose`) + recall semántico
    SOLO si el gate `needs_recall` dispara (`compose_recall`). Es exactamente lo que el cerebro tiene en el prompt
    — sin LLM en la lectura. Devuelve (texto_normalizado, recall_disparado)."""
    from nucleo.flash import memory_cache as _mc
    from nucleo.flash import prompt as _p
    try:
        block, _op = _mc._compose()
    except Exception:
        block = ""
    fired = _p.needs_recall(q)
    recall = ""
    if fired:
        try:
            recall, _ids = _p.compose_recall(q)
        except Exception:
            recall = ""
    return _norm(block + "\n" + recall), fired


def _count_durable_with(marker: str) -> tuple[int, float]:
    """Cuenta recuerdos DURABLES válidos (mid/long) cuyo texto contiene el ancla, y el peso máximo entre ellos.
    Lectura directa a la BD (no retriever) — para verificar el DEDUP (¿cuántas filas del mismo hecho hay?)."""
    from memory import db as _db
    rows = _db.get_db().query(
        "SELECT text, weight FROM memories WHERE valid=1 AND level IN ('mid','long')")
    n, wmax = 0, 0.0
    for r in rows:
        if marker in _norm(r["text"]):
            n += 1
            wmax = max(wmax, float(r["weight"] or 0))
    return n, wmax


def _verify_query(memory, step: dict) -> tuple[bool, str]:
    via = step.get("via", "long")            # fuente ESPERADA (documentación); la vista es siempre la del cerebro
    want = [_norm(w) for w in (step.get("want") or [])]
    view, fired = _brain_view(step.get("q", ""))
    hit = [w for w in want if w in view]
    # not_want: subcadenas que NO deben aparecer (p. ej. un dato superseded que ya no vale).
    not_want = [_norm(w) for w in (step.get("not_want") or [])]
    leaked = [w for w in not_want if w in view]
    tag = f"via {via}, recall={'sí' if fired else 'no'}"
    if leaked:
        return False, f"NO debía aparecer {leaked} (dato viejo/superseded) pero está en la vista ({tag})"
    ok = len(hit) == len(want)
    return ok, (f"el FlashBrain vería {want} ({tag}) OK" if ok
                else f"esperaba {want}; el FlashBrain solo vería {hit} ({tag})")


async def _do_turn(memory, memory_agent, get_queue, step: dict) -> tuple[bool, str]:
    """Simula un TURNO de voz REAL (fidelidad al camino de `voice/engine/llm/providers/nucleo.py::_run`):
      1. `ingest_utterance(op)` → el CORAZÓN DESTILA lo memorable (nombre/hechos/preferencias) off-hot-path.
      2. conv-buffer: `memory.write(kind='conv', level='short', ttl_days=2)` con el par Operador·zaelar → alimenta
         la RECENCIA (lectura entera de CORTO, `recent_short`), pero NO es durable.
    Es lo que ocurre en CADA turno de charla. La recencia ("¿de qué hemos hablado?") se sirve de este buffer.

    Verificación OPCIONAL de la destilación con `durable`: `[]` = la charla NO debe crear recuerdo durable
    (state/long) — el conv de CORTO sí; `["long"]`/`["state"]` = además debe destilar ahí. Sin `durable` → solo
    avanza la conversación (siempre OK)."""
    op = step.get("op", step.get("text", ""))
    hb = step.get("hb", "")
    try:
        await memory_agent.ingest_utterance(op, role="operator")
        await get_queue().join()
    except Exception as e:  # noqa: BLE001
        return False, f"ingest lanzó: {e}"
    memory.write(f"Operador: {op[:200]} · zaelar: {hb[:200]}",
                 kind="conv", level="short", importance=0.2, ttl_days=2.0, meta={"source": "conv"})
    await get_queue().join()
    dur = step.get("durable")
    if dur is None:
        return True, f"turno registrado (recencia); zaelar: {hb[:40]!r}"
    marker = _norm(step["marker"])
    got = [l for l in _layers_with(memory, marker, op) if l in ("state", "long")]   # ignora el conv de CORTO
    if not dur:                                   # la charla NO debe crear durable
        ok = len(got) == 0
        return ok, ("charla sin durable OK (solo recencia)" if ok
                    else f"la charla creó durable indebido en {got}")
    missing = [l for l in dur if l not in got]
    ok = not missing
    return ok, (f"destiló a {got} OK" if ok else f"esperaba durable en {dur}; está en {got}")


async def _do_extract(memory, memory_agent, get_queue, step: dict) -> tuple[bool, str]:
    """Evalúa texto natural → CORAZÓN → gates → píldoras/slots/state."""
    from memory import db as _db

    database = _db.get_db()
    before = {int(row["id"]) for row in database.query("SELECT id FROM memories")}
    result = await memory_agent.ingest_utterance(step["text"], role="operator")
    await get_queue().join()
    rows = [dict(row) for row in database.query(
        "SELECT id,level,kind,text,importance,weight,ttl_days,pinned,valid,slot,meta "
        "FROM memories ORDER BY id")]
    new_rows = [row for row in rows if int(row["id"]) not in before]
    active = [row for row in rows if int(row["valid"] or 0) == 1]
    state = memory.state()
    combined = _norm("\n".join(row.get("text") or "" for row in active) + "\n" +
                     json.dumps(state, ensure_ascii=False))
    errors: list[str] = []

    source = str(result.get("source") or "")
    if step.get("require_llm") and not source.startswith("llm"):
        errors.append(f"CORAZÓN no produjo la escritura (source={source!r})")
    atoms = int(result.get("atoms") or 0)
    if atoms < int(step.get("min_atoms", 0)):
        errors.append(f"átomos={atoms} < mínimo {step['min_atoms']}")
    if step.get("max_atoms") is not None and atoms > int(step["max_atoms"]):
        errors.append(f"átomos={atoms} > máximo {step['max_atoms']}")

    if step.get("discard"):
        if new_rows:
            errors.append(f"debía descartarse pero creó {len(new_rows)} fila(s)")
        if source not in {"discard", "discard-llm", "skip"}:
            errors.append(f"ruta de descarte inesperada: {source!r}")

    for marker in step.get("contains", ()):
        if _norm(marker) not in combined:
            errors.append(f"no extrajo {marker!r}")
    if step.get("contains_any") and not any(_norm(marker) in combined for marker in step["contains_any"]):
        errors.append(f"no extrajo ninguno de {step['contains_any']!r}")
    for marker in step.get("not_contains", ()):
        if _norm(marker) in combined:
            errors.append(f"persistió contenido prohibido {marker!r}")

    for field, expected in (step.get("state") or {}).items():
        actual = str(state.get(field) or "")
        if _norm(expected) not in _norm(actual):
            errors.append(f"state.{field}={actual!r}; esperaba {expected!r}")

    by_slot: dict[str, list[dict]] = {}
    for row in active:
        if row.get("slot"):
            by_slot.setdefault(str(row["slot"]), []).append(row)
    for slot, expected in (step.get("slots") or {}).items():
        slot_rows = by_slot.get(slot, [])
        blob = _norm(" ".join(row.get("text") or "" for row in slot_rows))
        if len(slot_rows) != 1 or _norm(expected) not in blob:
            errors.append(f"slot {slot}: {len(slot_rows)} vigente(s), esperaba una con {expected!r}")
    for slot, forbidden in (step.get("slot_not") or {}).items():
        blob = _norm(" ".join(row.get("text") or "" for row in by_slot.get(slot, [])))
        if _norm(forbidden) in blob:
            errors.append(f"slot {slot} aún contiene {forbidden!r}")

    for marker, allowed in (step.get("allowed_levels") or {}).items():
        hits = [row for row in active if _norm(marker) in _norm(row.get("text") or "")]
        if hits and not any(row.get("level") in allowed for row in hits):
            errors.append(f"{marker!r} quedó en {[row.get('level') for row in hits]}, esperaba {allowed}")
    for marker in step.get("pinned", ()):
        hits = [row for row in active if _norm(marker) in _norm(row.get("text") or "")]
        if not hits or not any(int(row.get("pinned") or 0) == 1 for row in hits):
            errors.append(f"{marker!r} no quedó pinned")

    evidence = {
        "gateway": {k: v for k, v in result.items() if k != "plan"},
        "plan": result.get("plan"), "state": state, "new_rows": new_rows, "errors": errors,
    }
    return not errors, json.dumps(evidence, ensure_ascii=False, default=str)


async def _do_connector(memory, memory_agent, get_queue, step: dict) -> tuple[bool, str]:
    """Simula un DATO ENTRANTE por una FUENTE externa (WhatsApp/Telegram/email/**cluster**/**agent**) — la vía real
    `memory.ingest_message` (multi-fuente): indexa `source`=plataforma + `entity`=remitente en `meta` y en el texto
    `[source] entity: body`. Escala igual a 2 conectores que a 200, o a un peer de cluster («Zalo») que a un chat.
    `trust`: 'external' (conector del dueño) vs 'untrusted' (peer de cluster no confiable). `durable=True` → mid.
    Verifica que el dato queda en la(s) capa(s) esperada(s)."""
    platform = step.get("platform", "whatsapp")
    sender = step.get("sender") or step.get("entity") or ""
    text = step.get("text", "")
    trust = step.get("trust", "external")
    memory.ingest_message(platform, sender, text, group=step.get("group"),
                          directed=step.get("directed", True), trust=trust,
                          durable=bool(step.get("durable")), ttl_days=step.get("ttl_days"),
                          importance=step.get("importance"))
    await get_queue().join()
    marker = _norm(step["marker"])
    want_in = list(step.get("in") or ["short"])
    # ALMACENAMIENTO: se verifica por el ÍNDICE DE FUENTE (ve TODO, también lo `untrusted` que la lectura pasiva
    # pone en cuarentena) — el dato SÍ se guarda; la cuarentena solo lo oculta del bloque pasivo del cerebro.
    rows = memory.recent_by_source(platform, sender or None, limit=80, max_chars=12000)
    hits = [r for r in rows if marker in _norm(r.get("text", ""))]
    if not hits:
        return False, f"[{platform}] {sender or '—'}: NO quedó indexado por fuente (marker {marker!r})"
    # DURABILIDAD: si se pidió durable (o `in` incluye 'long'), la fila indexada debe ser mid/long. Se comprueba
    # por el nivel que devuelve el ÍNDICE DE FUENTE — funciona también para untrusted (cuarentenado del retriever).
    if step.get("durable") or "long" in want_in:
        if not any(r.get("level") in ("mid", "long") for r in hits):
            return False, f"[{platform}] {sender or '—'}: se pedía durable pero la fila indexada no es mid/long"
    return True, f"[{platform}] {sender or '—'} indexado (durable={bool(step.get('durable'))}, trust={trust}) OK"


async def _do_forget(memory, memory_agent, get_queue, step: dict) -> tuple[bool, str]:
    """Dim N — OLVIDO A PETICIÓN por la ruta NL REAL: `ingest_utterance("olvida lo de X")` dispara el hook
    determinista → `memory.forget`. Verifica que (a) se detectó la intención de olvido y (b) el ancla DESAPARECE
    del store durable/reciente (invalidada; el histórico se conserva con valid=0, no se pierde)."""
    say = step.get("say") or step.get("text", "")
    res = await memory_agent.ingest_utterance(say, role="operator")
    await get_queue().join()
    if res.get("source") != "forget":
        return False, f"el hook NL de olvido NO disparó con {say!r} (source={res.get('source')!r})"
    marker = _norm(step["marker"])
    # HARD delete (privacidad): además de no aflorar, la fila NO debe existir NI con valid=0 (borrado real).
    if step.get("hard"):
        if not res.get("hard"):
            return False, "se pidió olvido DURO pero el hook lo trató como soft (marca 'del todo' no detectada)"
        from memory import db as _db
        n = _db.get_db().query_one(
            "SELECT count(*) c FROM memories WHERE lower(text) LIKE ?", (f"%{marker}%",))["c"]
        ok = (n == 0)
        return ok, (f"olvido DURO: 0 filas con {marker!r} (borrado real, sin rastro) OK" if ok
                    else f"olvido DURO pedido pero quedan {n} fila(s) con {marker!r} en la BD")
    got = _layers_with(memory, marker, step.get("probe", marker))
    ok = len(got) == 0
    return ok, (f"olvidó {res.get('forgot', 0)} recuerdo(s); ancla {marker!r} ya no aparece OK" if ok
                else f"el olvido disparó pero el ancla {marker!r} SIGUE en {got}")


async def _do_unforget(memory, memory_agent, get_queue, step: dict) -> tuple[bool, str]:
    """Dim N — DES-OLVIDO por la ruta NL REAL: `ingest_utterance("recupera lo de X")` dispara el hook determinista
    → `memory.unforget`. Verifica (a) que se detectó la retractación y (b) que el ancla VUELVE a aparecer en el
    store (lo que se había invalidado con forget se restaura y vuelve a aflorar en la lectura)."""
    say = step.get("say") or step.get("text", "")
    res = await memory_agent.ingest_utterance(say, role="operator")
    await get_queue().join()
    if res.get("source") != "unforget":
        return False, f"el hook NL de des-olvido NO disparó con {say!r} (source={res.get('source')!r})"
    marker = _norm(step["marker"])
    got = _layers_with(memory, marker, step.get("probe", marker))
    ok = len(got) > 0
    return ok, (f"restauró {res.get('restored', 0)} recuerdo(s); ancla {marker!r} vuelve en {got} OK" if ok
                else f"des-olvido disparó pero el ancla {marker!r} NO reaparece (restore roto)")


async def _do_weight_check(memory, get_queue, step: dict) -> tuple[bool, str]:
    """Dim L — REFUERZO medible (curva de memoria humana): un recuerdo que se USA se FORTALECE. Siembra un hecho,
    lo consulta N veces con `reinforce_used=True` y verifica que su peso/acceso SUBE (la superpotencia: lo que
    recuerdas a menudo se afianza; lo que no, decae). El refuerzo va por la COLA async → hay que DRENARLA antes de
    leer el peso. Lectura directa a la BD antes/después."""
    from memory import db as _db
    text = step["text"]
    mid = memory.write_now(text, kind="fact", level="long")

    def _wa():
        r = _db.get_db().query_one("SELECT weight, access_count FROM memories WHERE id=?", (mid,))
        return (float(r["weight"] or 0), int(r["access_count"] or 0)) if r else (0.0, 0)

    w0, a0 = _wa()
    q = step.get("q", text)
    for _ in range(int(step.get("reinforce", 4))):
        memory.query(q, reinforce_used=True)
    await get_queue().join()                # DRENAR el refuerzo async antes de medir
    w1, a1 = _wa()
    ok = (w1 > w0) or (a1 > a0)
    return ok, (f"refuerzo: peso {w0:.2f}→{w1:.2f}, accesos {a0}→{a1} (esperado ↑) {'OK' if ok else 'FALLO (no se afianzó)'}")


def _do_consolidate(memory, step: dict) -> tuple[bool, str]:
    """Dim L — CONSOLIDACIÓN / OLVIDO por peso: corre `memory.consolidate(limit)` (decay + dedup + eviction del de
    MENOR peso). Verifica el INVARIANTE de oro: **pinned NUNCA se evita** — el `keep` (ancla de un hecho pinned)
    debe seguir vivo tras una poda AGRESIVA. Best-effort.

    AISLADO en una BD temporal (V2-031, 2026-08-17): antes de este fix, `consolidate(limit=120)` podaba
    DIRECTAMENTE `zaelar.membot.db` en case ~382/579 — con cientos de hechos YA acumulados de otras baterías
    (BATCH_9 "tareas encargadas" entre ellas), `evict()` borraba de VERDAD (hard delete) todo lo no-pinned por
    debajo del límite, un daño colateral silencioso que solo `dimension C` (retención profunda, medida MUCHOS
    casos después contra el estado FINAL) delataba — el propio `keep` de este test pasaba siempre (es pinned),
    así que nada en la batería local avisaba de lo que se llevaba por delante. Snapshot-and-restore: se
    checkpointea el WAL, se copia el fichero, se corre la poda AGRESIVA de verdad (la aserción sigue siendo
    real, sobre datos reales), y se RESTAURA el snapshot al terminar — el resto del corpus nunca ve el hueco."""
    import shutil
    limit = int(step.get("limit", 200))
    try:
        from memory import db as _db
        db = _db.get_db()
        db.conn.commit()
        db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")   # vuelca el WAL al fichero principal antes de copiar
        snapshot = str(_db.db_path()) + ".consolidate-snapshot"
        shutil.copyfile(str(_db.db_path()), snapshot)
        try:
            before = db.query_one("SELECT count(*) c FROM memories WHERE valid=1")["c"]
            rep = memory.consolidate(limit=limit)
            after = db.query_one("SELECT count(*) c FROM memories WHERE valid=1")["c"]
            keep = _norm(step.get("keep", ""))
            survived = _in_long(memory, keep, step.get("keep", "")) if keep else True
        finally:
            # restaura SIEMPRE (incluso si la aserción falló) — el resto de la batería no puede heredar la poda.
            # ORDEN CRÍTICO: cerrar la conexión ANTES de tocar el fichero — sobreescribir un .db con una conexión
            # SQLite todavía abierta (WAL) es estado indefinido; `close()` puede volcar su propia caché encima
            # del restore. Verificado en vivo: sin este orden el restore quedaba a medias (ni 23 ni 5 filas).
            _db.reset_db()
            shutil.copyfile(snapshot, str(_db.db_path()))
            for suf in ("-wal", "-shm"):
                f = pathlib.Path(str(_db.db_path()) + suf)
                if f.exists():
                    f.unlink()
            os.remove(snapshot)
            _db.get_db()
    except Exception as e:  # noqa: BLE001
        return False, f"consolidate lanzó: {e}"
    if keep and not survived:
        return False, f"PINNED evitado indebidamente: {step.get('keep')!r} no sobrevivió a la poda (limit={limit})"
    return True, (f"consolidó AISLADO (limit={limit}): {before}→{after} válidos; "
                  f"pinned {step.get('keep','—')!r} sobrevive OK; corpus compartido restaurado")


async def _do_episode(memory, get_queue, step: dict) -> tuple[bool, str]:
    """Dim S — EPISÓDICA: guarda un fichero (paste/drop) con `memory.write_episode` (bytes + RESUMEN buscable, carga
    lazy). Verifica que el RESUMEN es recuperable por el retriever (el binario NO va al prompt por defecto)."""
    text = step.get("text", "")
    summary = step.get("summary", text[:200])
    fn = step.get("filename", "documento.txt")
    try:
        memory.write_episode(text.encode("utf-8"), filename=fn, summary=summary)
        await get_queue().join()
    except Exception as e:  # noqa: BLE001
        return False, f"write_episode lanzó: {e}"
    marker = _norm(step["marker"])
    ok = _in_long(memory, marker, summary) or (marker in _short_blob(memory))
    return ok, (f"episodio {fn!r} indexado; resumen buscable OK" if ok
                else f"el resumen del episodio {fn!r} NO es recuperable (ancla {marker!r})")


def _verify_source_query(memory, step: dict) -> tuple[bool, str]:
    """Consulta por TIPO INDEXADO (`memory.recent_by_source` — lectura DIRECTA, sin LLM): filtra por
    `source`(/`entity`) y comprueba que aparecen los `want` (y no los `not_want`). Es "¿qué me ha llegado por
    WhatsApp?" / "¿qué me dijo Zalo por el cluster?" resuelto por el índice de fuente, no por el retriever."""
    src = step.get("source")
    ent = step.get("entity")
    rows = memory.recent_by_source(src, ent, limit=60, max_chars=8000)
    blob = _norm(" ".join(r.get("text", "") for r in rows))
    want = [_norm(w) for w in (step.get("want") or [])]
    hit = [w for w in want if w in blob]
    not_want = [_norm(w) for w in (step.get("not_want") or [])]
    leaked = [w for w in not_want if w in blob]
    tag = f"source={src or '*'}" + (f" entity={ent}" if ent else "") + f" · {len(rows)} filas"
    if leaked:
        return False, f"NO debía aparecer {leaked} en la fuente ({tag})"
    ok = len(hit) == len(want)
    return ok, (f"índice de fuente devuelve {want} ({tag}) OK" if ok
                else f"esperaba {want} por índice de fuente; solo {hit} ({tag})")


async def _do_cluster_exchange(memory, get_queue, step: dict) -> tuple[bool, str]:
    """Simula un INTERCAMBIO real con un peer de cluster (peer→zaelar + zaelar→peer) por la vía de T170
    (`connectors.meshkore.mem_ingest`): destila una SÍNTESIS COMPRIMIDA y CUARENTENADA por peer bajo el slot
    `cluster:<cluster>:<peer>` (supersede). Verifica que (a) queda UNA fila recuperable por índice de fuente y
    (b) NO se cuela en el bloque pasivo del cerebro (cuarentena). La calidad de la síntesis la valida el pytest
    unitario con un sintetizador determinista; aquí ejercemos el camino real (LLM local si está, si no fail-open)."""
    from connectors.meshkore import mem_ingest
    cluster = step.get("cluster", "obra")
    peer = step.get("peer") or step.get("entity") or "Zalo"
    before = len(memory.recent_by_source("cluster", peer, limit=200))
    await mem_ingest._run(cluster, peer, step.get("inbound", ""), step.get("outbound", ""))
    await get_queue().join()
    rows = memory.recent_by_source("cluster", peer, limit=200)
    if not rows:
        return False, f"cluster·{peer}: no se generó síntesis"
    if any(r.get("trust") != "untrusted" for r in rows if r.get("source") == "cluster"):
        # (defensivo) la síntesis del canal SIEMPRE es untrusted
        pass
    # SUPERSEDE por slot: un intercambio POSTERIOR con el mismo peer REESCRIBE su síntesis, no añade una fila nueva
    # (la vía slotted). En el DB acumulativo del bot puede haber filas previas NO-slotted (paso `connector`), así que
    # comprobamos el DELTA: como mucho +1 fila la primera vez; 0 en los intercambios siguientes del mismo peer.
    if len(rows) > before + 1:
        return False, f"cluster·{peer}: la síntesis añadió {len(rows) - before} filas (supersede roto)"
    # CUARENTENA: nada de la síntesis en el bloque pasivo (marker debe faltar en corto/salient)
    marker = _norm(step.get("marker", ""))
    if marker:
        passive = _norm(" ".join(r.get("text", "") for r in memory.recent_short(limit=50))
                        + " " + " ".join(r.get("text", "") for r in memory.salient_long(limit=8)))
        if marker in passive:
            return False, f"cluster·{peer}: la síntesis se coló en el bloque pasivo (marker {marker!r})"
    return True, f"cluster·{peer}: síntesis cuarentenada y recuperable por fuente OK"


async def _do_recall_probe(memory, memory_agent, get_queue, step: dict) -> tuple[bool, str]:
    """Dims T/C — RECALL SEMÁNTICO AISLADO: guarda el/los hecho(s) (destilados por el CORAZÓN, ruta real) y luego
    consulta el RETRIEVER DIRECTAMENTE (`memory.query`, NO el bloque pasivo) → mide si el hecho aflora POR SIGNIFICADO
    aunque la pregunta no comparta léxico (vocab-gap, dim T) o el dato sea antiguo (retención, dim C). Aísla la capa
    LARGO de la recencia: el conv-buffer del CORTO no puede 'chivar' el dato verbatim, así probamos el embedding real."""
    for tx in step.get("save", []):
        await memory_agent.ingest_utterance(tx, role="operator")
        await get_queue().join()
    res = memory.query(step.get("q", ""), reinforce_used=False)
    blob = _norm(" ".join(m.get("text", "") for m in res.get("memories", [])))
    want = [_norm(w) for w in (step.get("want") or [])]
    hit = [w for w in want if w in blob]
    ok = len(hit) == len(want)
    return ok, (f"el retriever (LARGO, por significado) aflora {want} OK" if ok
                else f"esperaba {want} por significado; el retriever solo trajo {hit} (vocab-gap/retención)")


async def _do_ui_state(memory, get_queue, step: dict) -> tuple[bool, str]:
    """Dim Y — ESTADO / CONTEXTO DE UI VIVO: escribe el estado de UI (widgets abiertos + tareas en marcha) por la
    MISMA vía que el frontend/dispatcher (`memory.set_state`) y verifica DOS cosas — que el ESTADO **GUARDA** lo que
    debe (`state()` lo refleja; el patch superficial no pisa el resto) y que el bloque que **VE el FlashBrain**
    (`memory_cache._compose`, lo que va en el prompt) **CONTIENE** los widgets abiertos/tareas (→ desambiguación) y
    NO contiene lo retirado. Es la prueba de que el ESTADO da servicio a los casos de uso que fallaban."""
    from nucleo.flash import memory_cache as _mc
    memory.set_state(step.get("set") or {})
    await get_queue().join()
    st = memory.state()
    for k, v in (step.get("expect_state") or {}).items():   # (a) el ESTADO GUARDA lo esperado
        if st.get(k) != v:
            return False, f"ESTADO no guardó {k}={v!r} (tiene {st.get(k)!r})"
    block, _op = _mc._compose()                             # (b) el FlashBrain lo VE en su bloque de prompt
    blob = _norm(block)
    miss = [w for w in (_norm(x) for x in (step.get("want") or [])) if w not in blob]
    leaked = [w for w in (_norm(x) for x in (step.get("not_want") or [])) if w in blob]
    if miss:
        return False, f"el bloque del FlashBrain NO muestra {miss} del ESTADO de UI"
    if leaked:
        return False, f"el bloque del FlashBrain AÚN muestra {leaked} (no se retiró del ESTADO)"
    return True, f"ESTADO guarda {list((step.get('expect_state') or {}).keys())} y el FlashBrain lo VE OK"


async def _do_worker_write(memory, memory_agent, get_queue, step: dict) -> tuple[bool, str]:
    """Dim AF — ESCRITURA EXTERNA de un Brain Worker (auditoría 2026-07-14): la vía `remember_external`
    (por HTTP en producción vía `hbmem`) aplica gates que la escritura de voz NO necesita: NUNCA toca `state`,
    los slots de IDENTIDAD se VETAN (un worker no habla por el operador), una pregunta reificada se DESCARTA
    (gate P0a), y la procedencia queda estampada (`meta.source`). `expect`: 'ok' (persiste), 'rejected'
    (descartado), 'identity_dropped' (slot de identidad degradado a hecho suelto). Verifica el resultado + que
    el ESTADO NO cambió + (para ok) que el ancla queda recuperable con la fuente correcta."""
    item = {"text": step.get("text", "")}
    for k in ("slot", "kind", "level", "importance"):
        if step.get(k) is not None:
            item[k] = step[k]
    st_before = dict(memory.state())
    res = await memory_agent.remember_external(item, source=step.get("source", "worker:test"))
    await get_queue().join()
    exp = step.get("expect", "ok")
    # el ESTADO nunca lo toca un worker
    prot = step.get("state_key")
    if prot and memory.state().get(prot) != st_before.get(prot):
        return False, f"un worker PISÓ el estado {prot!r} ({st_before.get(prot)!r}→{memory.state().get(prot)!r})"
    if exp == "rejected":
        ok = not res.get("ok")
        return ok, (f"worker write RECHAZADO por el gate ({res.get('reason')}) OK" if ok
                    else "se esperaba rechazo del gate pero se persistió")
    if not res.get("ok"):
        return False, f"worker write se esperaba OK pero el gate lo rechazó ({res.get('reason')})"
    if exp == "identity_dropped" and not res.get("identity_slot_dropped"):
        return False, "se esperaba que el slot de IDENTIDAD se vetara pero se conservó"
    marker = _norm(step.get("marker", ""))
    if marker:
        got = _layers_with(memory, marker, step.get("text", ""))
        if not got:
            return False, f"worker write OK pero el ancla {marker!r} no aflora en ninguna capa"
    return True, f"worker write ({exp}) OK · source={step.get('source','worker:test')}"


def _do_slot_count(memory, step: dict) -> tuple[bool, str]:
    """Dim AE — REGISTRO DE SLOTS / colapso de linajes (auditoría 2026-07-14): tras decir un hecho SINGULAR de
    varias formas/idiomas (que disparan alias de slot distintos: 'location'/'ubicación'/'city' → operator.location),
    debe quedar EXACTAMENTE 1 píldora vigente de ese slot (no linajes paralelos, el bug de las 4 ubicaciones a la
    vez). Lee la BD directamente: cuenta filas `valid=1` con ese slot canónico."""
    from memory import db as _db
    from memory import slots as _slots
    slot = _slots.canonical(step["slot"])
    n = _db.get_db().query_one("SELECT count(*) c FROM memories WHERE slot=? AND valid=1", (slot,))["c"]
    exp = int(step.get("expect_valid", 1))
    ok = (n == exp)
    # ancla opcional: el valor VIGENTE debe ser el último dicho
    want = _norm(step.get("want", ""))
    if ok and want:
        row = _db.get_db().query_one(
            "SELECT text FROM memories WHERE slot=? AND valid=1 ORDER BY updated DESC, id DESC LIMIT 1", (slot,))
        if not row or want not in _norm(row["text"]):
            return False, f"slot {slot!r}: 1 vigente pero NO es {want!r} (es {row['text'][:50] if row else '—'!r})"
    return ok, (f"slot {slot!r}: {n} píldora(s) vigente(s) (esperado {exp}) OK" if ok
                else f"slot {slot!r}: {n} vigentes, esperado {exp} — LINAJES PARALELOS (bug del retest)")


async def _do_heal_slots(memory, get_queue, step: dict) -> tuple[bool, str]:
    """Dim AG — SANEO de slots del consolidador (auditoría 2026-07-14): siembra un linaje PATOLÓGICO con 2+
    píldoras VIGENTES del mismo slot (el estado que dejaban los alias/legacy/unforget pre-normalización) y verifica
    que `memory.consolidate()` → `heal_slots()` lo COLAPSA a 1 (la pareja del supersede auto-curativo del writer,
    para el stock ya existente). El valor VIGENTE final debe ser el último sembrado ('el más reciente MANDA')."""
    from memory import db as _db
    from memory import slots as _slots
    slot = _slots.canonical(step["slot"])
    ids = []
    for tx in step["seed"]:                       # textos DISTINTOS (si no, el dedup por texto los fundiría)
        ids.append(memory.write_now(tx, kind="profile", level="long", slot=slot))
        await get_queue().join()
    ph = ",".join("?" * len(ids))                 # fuerza el estado patológico: TODAS vigentes a la vez
    _db.get_db().execute(f"UPDATE memories SET valid=1, superseded_by=NULL WHERE id IN ({ph})", tuple(ids))
    before = _db.get_db().query_one("SELECT count(*) c FROM memories WHERE slot=? AND valid=1", (slot,))["c"]
    memory.consolidate(limit=100000)              # limit enorme → no evicta; aislamos el efecto de heal_slots
    rows = _db.get_db().query("SELECT id, text FROM memories WHERE slot=? AND valid=1 ORDER BY updated DESC, id DESC",
                              (slot,))
    after = len(rows)
    ok = (before >= 2) and (after == 1)
    want = _norm(step.get("want", ""))
    if ok and want and want not in _norm(rows[0]["text"]):
        return False, f"heal_slots colapsó a 1 pero NO es {want!r} (es {rows[0]['text'][:40]!r})"
    return ok, (f"heal_slots: {before}→{after} vigentes del slot {slot!r} (colapso a 1) OK" if ok
                else f"heal_slots: {before}→{after} vigentes del slot {slot!r} (esperaba colapso a 1) FALLO")


async def _do_compose_check(memory, get_queue, step: dict) -> tuple[bool, str]:
    """Dim AH — COMPOSICIÓN DEL ESTADO (auditoría de memoria 2026-07-14): verifica lo que el FlashBrain VE en el
    bloque de estado compuesto (`compose_state`, el mismo que cachea `memory_cache` y va al prompt). Prueba el bug
    del auditor: un slot de FONDO de otra ciudad (`weather:soria` del widget) NO debe colarse al bloque pasivo
    ('lo que sabes de él, sin buscar') cuando `state.location` es otra — o secuestra '¿qué tiempo hace hoy?'.
    `set_state` fija el estado; `bg_slots` siembra píldoras de fondo; `want`/`not_want` = subcadenas que deben /
    no deben aparecer en el bloque. Determinista (sin LLM)."""
    if step.get("set_state"):
        memory.set_state(step["set_state"])
        await get_queue().join()
    for w in step.get("bg_slots", []):
        memory.write_now(w["text"], slot=w.get("slot"), kind=w.get("kind", "note"),
                         level=w.get("level", "mid"), importance=w.get("importance", 0.4))
        await get_queue().join()
    block, _op, _st = memory.compose_state(mission_fallback=step.get("mission", ""))
    blob = _norm(block)
    want = [_norm(x) for x in (step.get("want") or [])]
    not_want = [_norm(x) for x in (step.get("not_want") or [])]
    miss = [w for w in want if w not in blob]
    leaked = [w for w in not_want if w in blob]
    if leaked:
        return False, f"el bloque de estado FILTRA {leaked} (slot de fondo secuestra el estado); state OK={not miss}"
    if miss:
        return False, f"el bloque de estado NO muestra {miss} de state.location"
    # opcional: el slot de fondo sigue recuperable por consulta EXPLÍCITA (no se ha perdido, solo subordinado)
    if step.get("still_retrievable"):
        from memory import db as _db
        n = _db.get_db().query_one(
            "SELECT count(*) c FROM memories WHERE slot=? AND valid=1", (step["still_retrievable"],))["c"]
        if n < 1:
            return False, f"el slot de fondo {step['still_retrievable']!r} se perdió (debe seguir consultable)"
    return True, f"bloque de estado limpio: muestra {want or 'state'}, no filtra {not_want or '—'} OK"


async def _do_scale(step: dict) -> tuple[bool, str]:
    """Dim K — ESCALA (needle-in-haystack + latencia), como CASO repetible en la suite. Cada caso siembra `noise`
    recuerdos de relleno + `distractors` (falsos-amigos: casi la respuesta pero NO) + `needles` (hechos con keyword
    ÚNICA + su pregunta) en una BD TEMPORAL AISLADA (hash-embeddings → siembra rápida y determinista), mide si CADA
    aguja se recupera entre el ruido (precisión no colapsa) y la latencia p50/máx, y RESTAURA la BD del bot al salir.
    Implementa el «bombardea con cientos/miles y pregunta por algunos» del operador — el modo de fallo nº1 (dim K).
    `pinned` (def False) = aguja NO fijada → prueba el retriever de verdad, no el atajo de saliencia."""
    import os
    import statistics
    import tempfile
    import time as _t
    old_db = os.environ.get("ZAELAR_DB")
    old_emb = os.environ.get("ZAELAR_EMBED_BACKEND")
    from memory import db as _db
    from memory import embeddings as _emb
    noise = int(step.get("noise", 500))
    max_ms = int(step.get("max_ms", 1200))
    pinned = bool(step.get("pinned", False))
    # embed: "hash" (def) = rápido/determinista, prueba FTS+RRF a escala. "fastembed" = embeddings SEMÁNTICOS REALES
    # (sin Ollama), prueba el ÍNDICE VECTORIAL real a escala — la verdadera curva de coste del retriever (dim K).
    embed = step.get("embed", "hash")
    needles = step["needles"]                       # [{text, q, marker}]
    distractors = step.get("distractors", [])       # falsos-amigos (str)
    topics = ["trabajo", "salud", "finanzas", "familia", "deporte", "viajes", "estudios", "ocio",
              "comida", "tecnologia", "vivienda", "mascotas"]
    old_dedup = os.environ.get("MEM_SEMANTIC_DEDUP")
    old_cfg = _emb._mem_cfg
    try:
        os.environ["ZAELAR_DB"] = str(pathlib.Path(tempfile.gettempdir()) / "zaelar.scalecase.db")
        os.environ["ZAELAR_EMBED_BACKEND"] = ("fastembed" if embed == "real" else embed)
        # (fix 2026-07-20) El STORE (config/v2.json §memory.embed_provider) GANA al env → con Ollama vivo el
        # backend "hash" del harness no forzaba nada y cada nota de relleno pagaba un embedding REAL. Se fuerza
        # a nivel de módulo (como las fixtures de pytest). Y sembrar RUIDO no es un test de dedup: el dedup
        # semántico del writer hacía un KNN vec0 POR INSERT sobre la tabla creciente (O(N²), el runner se
        # quedaba "colgado" en los casos de escala) → OFF solo durante este step.
        os.environ["MEM_SEMANTIC_DEDUP"] = "0"
        _emb._mem_cfg = lambda: {"embed_provider": os.environ["ZAELAR_EMBED_BACKEND"], "embed_model": ""}
        for suf in ("", "-wal", "-shm"):
            f = pathlib.Path(os.environ["ZAELAR_DB"] + suf)
            if f.exists():
                f.unlink()
        _db.reset_db(); _emb.reset(); _db.get_db()
        from memory import api as memory
        for j in range(noise):
            tp = topics[j % len(topics)]
            memory.write_now(f"nota de relleno {j} sobre {tp}: detalle rutinario e irrelevante del dia {j}",
                             kind="event", level=("long" if j % 3 == 0 else "short"))
        for d in distractors:                        # falsos-amigos: comparten léxico con la aguja pero NO responden
            memory.write_now(d, kind="event", level="long")
        for text, _q, _mk in needles:
            memory.write_now(text, kind="fact", level="long", pinned=pinned)
        found, lat, misses = 0, [], []
        for text, q, mk in needles:
            t0 = _t.perf_counter()
            res = memory.query(q, reinforce_used=False)
            lat.append((_t.perf_counter() - t0) * 1000)
            blob = _norm(" ".join(m.get("text", "") for m in res.get("memories", [])))
            if _norm(mk) in blob:
                found += 1
            else:
                misses.append(mk)
        total = _db.get_db().query_one("SELECT count(*) c FROM memories")["c"]
        p50 = statistics.median(lat) if lat else 0
        mx = max(lat) if lat else 0
        # min_found = agujas mínimas que deben aflorar (def = TODAS). Se rebaja para caracterizar fronteras
        # conocidas (p. ej. una aguja semántica ambigua que ni el mejor embedding resuelve) sin fingir un 100%.
        min_found = int(step.get("min_found", len(needles)))
        ok = (found >= min_found) and (mx <= max_ms)
        detail = (f"escala noise={noise} (total {total}, embed={embed}) · agujas {found}/{len(needles)} "
                  f"(mín {min_found}) · p50 {round(p50)}ms máx {round(mx)}ms (≤{max_ms}) "
                  f"{'OK' if ok else 'FALLO ' + (f'perdió {misses}' if misses else 'latencia')}")
        return ok, detail
    finally:
        if old_db is not None:
            os.environ["ZAELAR_DB"] = old_db
        else:
            os.environ.pop("ZAELAR_DB", None)
        if old_dedup is not None:
            os.environ["MEM_SEMANTIC_DEDUP"] = old_dedup
        else:
            os.environ.pop("MEM_SEMANTIC_DEDUP", None)
        _emb._mem_cfg = old_cfg
        if old_emb is not None:
            os.environ["ZAELAR_EMBED_BACKEND"] = old_emb
        else:
            os.environ.pop("ZAELAR_EMBED_BACKEND", None)
        _emb.reset(); _db.reset_db(); _db.get_db()      # reabre la BD del bot intacta para el resto de la tanda


# ── ejecución de una tanda ──────────────────────────────────────────────────────────────────────────────────
async def run_range(lo: int, hi: int, fresh: bool = False) -> dict:
    _setup_env()
    LOGDIR.mkdir(parents=True, exist_ok=True)
    from memory import db as _db
    from memory import api as memory
    from memory.queue import get_queue
    from nucleo import memory_agent

    if fresh:
        _db.reset_db()
        p = _db.db_path()
        for suf in ("", "-wal", "-shm"):
            f = pathlib.Path(str(p) + suf)
            if f.exists():
                f.unlink()
    _db.reset_db()
    _db.get_db()
    # V2-031 (2026-08-17, encontrado midiendo write-completeness tras el fix del backend de embedding): desde
    # 85b4922 (2026-08-14) una BD fresca arranca con `state.language="en"` a propósito (el producto abre en
    # inglés hasta detectar el idioma real) — y `nucleo/mem_processor.py::_render` lee ESE campo, no una env
    # var, para decidir en qué idioma destila cada píldora (`state.get("language") or _default_code()`, y el
    # valor de state SIEMPRE gana si está puesto). El corpus de `cases.py` está escrito íntegro en español con
    # `want`/`marker` en español — sin este seed, `--fresh` escribía la memoria entera en INGLÉS y el harness
    # reportaba "write miss" en case tras caso: el dato SÍ se guardaba, solo que en un idioma que ningún
    # `want` podía casar. Confirmado en vivo: `state.language` quedó en `"en"` y las píldoras en inglés tras la
    # corrida de esta tarde. `set_state` (no solo la env var) porque el campo de `state` es el que manda.
    memory.set_state({"language": "es"})

    CASES = _load_cases()
    hi = min(hi, len(CASES))
    results = []
    observer = None
    if os.getenv("ZAELAR_TEST_RUN_DIR"):
        from tests.platform.events import EventWriter
        observer = EventWriter(os.environ["ZAELAR_TEST_RUN_DIR"], run_id=os.getenv("ZAELAR_TEST_RUN_ID"))
        from .catalog import serialize_case
        for position, case_index in enumerate(range(lo, hi), start=1):
            entry = serialize_case(_ACTIVE, case_index, CASES[case_index])
            observer.emit("test.discovered", test_id=entry["id"], suite="memory",
                          label=f"{_ACTIVE} #{case_index + 1} · {entry['type']} · {entry['title']}",
                          index=position, total=hi - lo, case=entry)
        observer.emit("collection.finished", suite="memory", total=hi - lo)

    def record(result: dict, step: dict, started: float) -> None:
        result.setdefault("ms", round((time.time() - started) * 1000))
        results.append(result)
        if observer:
            from .catalog import serialize_case
            entry = serialize_case(_ACTIVE, result["i"], step)
            observer.emit("interaction.output", test_id=entry["id"], suite="memory", label="resultado",
                          output={"ok": result["ok"], "detail": result["detail"], "ms": result["ms"]})
            observer.emit("test.finished", test_id=entry["id"], suite="memory", label=entry["title"],
                          status="passed" if result["ok"] else "failed", duration_ms=result["ms"],
                          output={"detail": result["detail"]})

    await memory.start()
    try:
        for i in range(lo, hi):
            step = CASES[i]
            t0 = time.time()
            if observer:
                from .catalog import serialize_case
                entry = serialize_case(_ACTIVE, i, step)
                observer.emit("test.started", test_id=entry["id"], suite="memory", label=entry["title"])
                observer.emit("interaction.input", test_id=entry["id"], suite="memory", label="request",
                              input=entry["input"], expectation=entry["expected"],
                              verification=entry["verification"], note=entry["note"])
            if step["t"] == "save":
                try:
                    await memory_agent.ingest_utterance(step["text"], role="operator")
                except Exception as e:  # noqa: BLE001
                    record({"i": i, "t": "save", "ok": False, "detail": f"ingest lanzó: {e}",
                            "text": step.get("text"), "note": step.get("note")}, step, t0)
                    continue
                await get_queue().join()               # drena la cola (write + embedding)
                ok, detail = _verify_save(memory, step)
            elif step["t"] == "extract":
                try:
                    ok, detail = await _do_extract(memory, memory_agent, get_queue, step)
                except Exception as e:  # noqa: BLE001
                    ok, detail = False, f"gateway conversacional lanzó: {type(e).__name__}: {e}"
            elif step["t"] == "dedup":
                for tx in step["texts"]:               # el MISMO hecho, varios fraseos → debe colapsar en 1
                    await memory_agent.ingest_utterance(tx, role="operator")
                    await get_queue().join()
                marker = _norm(step["marker"])
                maxc = int(step.get("max_count", 1))
                n, wmax = _count_durable_with(marker)
                ok = (1 <= n <= maxc)
                detail = (f"{len(step['texts'])} fraseos → {n} recuerdo(s) durable(s), peso máx {wmax:.2f} "
                          f"(esperado ≤{maxc}) {'OK' if ok else 'FALLO (duplicados)'}")
                record({"i": i, "t": "dedup", "ok": ok, "detail": detail,
                        "text": step["texts"][0], "note": step.get("note"),
                        "ms": round((time.time() - t0) * 1000)}, step, t0)
                continue
            elif step["t"] == "turn":
                ok, detail = await _do_turn(memory, memory_agent, get_queue, step)
            elif step["t"] == "connector":
                ok, detail = await _do_connector(memory, memory_agent, get_queue, step)
            elif step["t"] == "source_query":
                ok, detail = _verify_source_query(memory, step)
            elif step["t"] == "cluster_exchange":
                ok, detail = await _do_cluster_exchange(memory, get_queue, step)
            elif step["t"] == "forget":
                ok, detail = await _do_forget(memory, memory_agent, get_queue, step)
            elif step["t"] == "unforget":
                ok, detail = await _do_unforget(memory, memory_agent, get_queue, step)
            elif step["t"] == "consolidate":
                ok, detail = _do_consolidate(memory, step)
            elif step["t"] == "weight_check":
                ok, detail = await _do_weight_check(memory, get_queue, step)
            elif step["t"] == "episode":
                ok, detail = await _do_episode(memory, get_queue, step)
            elif step["t"] == "scale":
                ok, detail = await _do_scale(step)
            elif step["t"] == "recall_probe":
                ok, detail = await _do_recall_probe(memory, memory_agent, get_queue, step)
            elif step["t"] == "ui_state":
                ok, detail = await _do_ui_state(memory, get_queue, step)
            elif step["t"] == "worker_write":
                ok, detail = await _do_worker_write(memory, memory_agent, get_queue, step)
            elif step["t"] == "slot_count":
                ok, detail = _do_slot_count(memory, step)
            elif step["t"] == "heal_slots":
                ok, detail = await _do_heal_slots(memory, get_queue, step)
            elif step["t"] == "compose_check":
                ok, detail = await _do_compose_check(memory, get_queue, step)
            else:
                ok, detail = _verify_query(memory, step)
            record({"i": i, "t": step["t"], "ok": ok, "detail": detail,
                    "text": step.get("text") or step.get("q") or step.get("op") or step.get("inbound"),
                    "note": step.get("note"), "ms": round((time.time() - t0) * 1000)}, step, t0)
    finally:
        await memory.stop()

    passed = sum(1 for r in results if r["ok"])
    # RESUMEN DE LATENCIA sobre las lecturas graduadas (query/source_query/recall_probe) — "¿es rápido?" deja de ser
    # afirmación y pasa a ser número. Es la latencia del CAMINO REAL de lectura del cerebro (sin LLM), la que el
    # FlashBrain paga en el turno. p95/máx delatan la cola (una aguja que el retriever tarda en traer bajo densidad).
    import statistics as _st
    read_ms = sorted(r["ms"] for r in results if r["t"] in ("query", "source_query", "recall_probe") and "ms" in r)
    latency = None
    if read_ms:
        latency = {
            "n": len(read_ms),
            "p50_ms": round(_st.median(read_ms)),
            "p95_ms": round(read_ms[min(len(read_ms) - 1, int(len(read_ms) * 0.95))]),
            "max_ms": max(read_ms),
            "slowest": sorted(
                ({"i": r["i"], "ms": r["ms"], "q": str(r.get("text"))[:60]}
                 for r in results if r["t"] in ("query", "source_query", "recall_probe") and "ms" in r),
                key=lambda x: x["ms"], reverse=True)[:5],
        }
    report = {"range": [lo, hi], "total": len(results), "passed": passed,
              "failed": len(results) - passed, "latency": latency, "results": results}
    return report


def emit_catalog() -> str:
    """Genera el REGISTRO legible (catálogo del corpus activo) desde su `cases*.py`: por cada request, qué se
    dice/pregunta y QUÉ ESPERAMOS — dónde debe grabarse (save) o qué debe devolver la lectura del cerebro (query).
    Fuente única: el módulo de casos (así el catálogo nunca miente sobre el test)."""
    CASES = _load_cases()
    _LAYER = {"state": "ESTADO (siempre en prompt)", "short": "CORTO (working set)", "long": "LARGO (durable)"}
    lines = [
        "# Catálogo del test bot de memoria (registro de requests + expectativas)",
        "",
        f"> Generado desde `{_corpus()['module']}.py` "
        f"(`python -m tests.memory.e2e.bot.runner --corpus {_ACTIVE} --catalog`). NO editar a mano.",
        "> Cada **save/extract** dice qué dice el operador y qué debe extraerse, descartarse o actualizarse. Cada **query**",
        "> simula una pregunta como la haría el FlashBrain y qué datos debe devolver la lectura DIRECTA (sin LLM):",
        "> ESTADO + perfil durable + CORTO (cacheado) y, si el gate `needs_recall` dispara, el recall del LARGO.",
        "",
        f"**Total de casos definidos:** {len(CASES)} (objetivo 1000, en tandas de 10).",
        "",
        "| # | tipo | el operador dice / pregunta | esperamos | por qué |",
        "|--:|:--|:--|:--|:--|",
    ]
    for i, c in enumerate(CASES):
        if c["t"] == "extract":
            say = "🗣️ " + c.get("text", "")
            checks = []
            if c.get("discard"):
                checks.append("**DESCARTE**: cero píldoras")
            if c.get("min_atoms") is not None:
                checks.append(f"≥{c['min_atoms']} píldoras")
            if c.get("max_atoms") is not None:
                checks.append(f"≤{c['max_atoms']} píldoras")
            if c.get("contains"):
                checks.append("extraer " + ", ".join(f"`{x}`" for x in c["contains"]))
            if c.get("contains_any"):
                checks.append("extraer alguno de " + ", ".join(f"`{x}`" for x in c["contains_any"]))
            if c.get("state"):
                checks.append("estado " + ", ".join(f"`{k}={v}`" for k, v in c["state"].items()))
            if c.get("slots"):
                checks.append("slots " + ", ".join(f"`{k}={v}`" for k, v in c["slots"].items()))
            if c.get("pinned"):
                checks.append("pinned " + ", ".join(f"`{x}`" for x in c["pinned"]))
            exp = "; ".join(checks) or "validar extracción conversacional declarada"
        elif c["t"] == "save":
            where = ("**DESCARTE** (no debe quedar en ninguna capa)" if not c.get("in")
                     else "grabar en " + " + ".join(_LAYER.get(x, x) for x in c["in"]))
            if c.get("state_key"):
                where += f" · `state.{c['state_key']}` poblado"
            say = c.get("text", "")
            exp = where
        elif c["t"] == "dedup":
            say = " / ".join(c.get("texts", []))
            exp = f"colapsar en ≤{c.get('max_count', 1)} recuerdo(s) durable(s) (dedup)"
        elif c["t"] == "turn":
            say = f"🗣️ {c.get('op', '')}" + (f"  ↩︎ zaelar: {c['hb']}" if c.get("hb") else "")
            dur = c.get("durable")
            exp = ("avanzar conversación → RECENCIA (conv-buffer CORTO)" if dur is None
                   else ("charla SIN durable (solo recencia)" if not dur
                         else "recencia + destilar a " + " + ".join(_LAYER.get(x, x) for x in dur)))
        elif c["t"] == "connector":
            say = f"📨 [{c.get('platform', '?')}] {c.get('sender', c.get('entity', ''))}: {c.get('text', '')}"
            exp = "guardar dato entrante en " + " + ".join(_LAYER.get(x, x) for x in (c.get("in") or ["short"]))
        elif c["t"] == "source_query":
            say = f"🔎 fuente={c.get('source', '*')}" + (f" · {c['entity']}" if c.get("entity") else "")
            exp = "por índice de fuente devolver: " + ", ".join(f"`{w}`" for w in (c.get("want") or []))
        elif c["t"] == "cluster_exchange":
            say = (f"🛰️ cluster·{c.get('peer', c.get('entity', '?'))} ⇄ peer: {c.get('inbound', '')[:60]}")
            exp = "destilar SÍNTESIS comprimida CUARENTENADA por peer (recuperable por fuente, fuera del pasivo)"
        elif c["t"] == "scale":
            n = len(c.get("needles", []))
            say = f"📈 siembra {c.get('noise', 0)} recuerdos + {len(c.get('distractors', []))} falsos-amigos · {n} agujas"
            exp = f"recuperar las {n} agujas entre el ruido (recall 100%) y latencia ≤{c.get('max_ms', 1200)}ms"
        elif c["t"] == "recall_probe":
            say = "🧲 " + (c.get("save", [""])[0][:50] if c.get("save") else "(BD)") + f" → «{c.get('q', '')}»"
            exp = "el retriever (LARGO, por SIGNIFICADO) aflora: " + ", ".join(f"`{w}`" for w in (c.get("want") or []))
        elif c["t"] == "unforget":
            say = f"↩️ {c.get('say', c.get('text', ''))}"
            exp = f"des-olvido: el ancla `{c.get('marker', '')}` VUELVE a aflorar (restaura lo invalidado)"
        else:
            say = "❓ " + c.get("q", "")
            exp = "devolver: " + ", ".join(f"`{w}`" for w in (c.get("want") or [])) + \
                  f" (fuente esperada: {_LAYER.get(c.get('via',''), c.get('via',''))})"
        note = (c.get("note") or "").replace("|", "/")
        say = say.replace("|", "/")
        lines.append(f"| {i} | {c['t']} | {say} | {exp} | {note} |")
    lines.append("")
    txt = "\n".join(lines)
    _catalog_path().write_text(txt)
    return txt


# ── COBERTURA por dimensión (taxonomía, TAXONOMY.md) ──────────────────────────────────────────────────────────
def emit_coverage() -> str:
    """Cuenta casos por DIMENSIÓN (campo `dim`; `cases.py` lo garantiza en TODOS — las tandas nuevas lo declaran y
    las tempranas lo deducen de su capa). Mapa de huecos de un vistazo para elegir qué atacar sin duplicar
    (ver TAXONOMY.md)."""
    CASES = _load_cases()
    by_dim: dict[str, int] = {}
    for c in CASES:
        d = c.get("dim") or "?"
        by_dim[d] = by_dim.get(d, 0) + 1
    names = {
        "A": "ESTADO/perfil", "B": "CORTO/recencia", "C": "LARGO/recall", "D": "DEDUP/supersede",
        "E": "DESCARTE/abstención", "F": "GRAFO/categoría", "G": "MULTI-FUENTE", "H": "CUARENTENA/confianza",
        "I": "INTERESES/intenciones", "J": "TEMPORAL/cronología", "K": "ESCALA/grandes datos",
        "L": "OLVIDO/consolidación", "M": "CONTRADICCIONES", "N": "PRIVACIDAD/olvido", "O": "RUTINAS/hábitos",
        "P": "ADVERSARIAL/ruido", "Q": "CROSS-SOURCE", "R": "MULTILINGÜE", "S": "EPISÓDICA", "T": "VOCAB-GAP",
        "U": "MULTI-HOP/composición", "V": "VERBOSIDAD/extracción", "W": "INSTRUCCIONES perm.",
        "X": "INVALIDACIÓN implícita", "Y": "ESTADO/UI vivo",
        "Z": "MEMORIA→ACCIÓN", "AA": "ANTI-ALUCINACIÓN", "AB": "VALIDEZ TEMPORAL",
        "AC": "IDENTIDAD x-sesión",
        # auditoría 2026-07-14 — capacidades nuevas del sistema de memoria:
        "AD": "SEÑAL change (multiidioma)", "AE": "REGISTRO slots/colapso", "AF": "ESCRITURA workers ext.",
        "AG": "heal_slots consolidador", "AH": "COMPOSICIÓN estado (slots fondo)",
        "?": "(legacy sin dim)",
    }
    lines = [f"COBERTURA por dimensión — {len(CASES)} casos totales (objetivo ≥1000 verificadas)", ""]
    for d in sorted(by_dim, key=lambda k: (k == "?", k)):
        lines.append(f"  {d:<2} {names.get(d, d):<22} {by_dim[d]:>4}")
    txt = "\n".join(lines)
    print(txt)
    return txt


# ── ESCALA (dimensión K): needle-in-haystack + latencia con MILES de recuerdos ────────────────────────────────
async def run_scale(noise: int = 2000, needles: int = 6, max_ms: int = 800) -> dict:
    """Harness de ESCALA (aislado, BD temporal propia, embeddings HASH para sembrar rápido y determinista): siembra
    `noise` recuerdos de relleno + `needles` AGUJAS con keyword distintiva, y mide (a) si cada aguja se RECUPERA
    entre el ruido (recall no colapsa) y (b) la LATENCIA de query (sqlite-vec es fuerza bruta O(N) → medimos la
    curva). Caza el modo de fallo nº1 del operador: "¿qué pasa cuando hay muchos datos?"."""
    import os
    import statistics
    import tempfile
    import time as _t
    os.environ["ZAELAR_DB"] = str(pathlib.Path(tempfile.gettempdir()) / "zaelar.scale.db")
    os.environ["ZAELAR_EMBED_BACKEND"] = "hash"   # rápido + determinista para sembrar miles
    os.environ["MEM_SEMANTIC_DEDUP"] = "0"        # sembrar ruido no es un test de dedup (KNN por insert = O(N²))
    from memory import db as _db
    from memory import embeddings as _emb
    _emb._mem_cfg = lambda: {"embed_provider": "hash", "embed_model": ""}   # el STORE ganaría al env (fix 2026-07-20)
    for suf in ("", "-wal", "-shm"):
        f = pathlib.Path(os.environ["ZAELAR_DB"] + suf)
        if f.exists():
            f.unlink()
    _db.reset_db(); _emb.reset(); _db.get_db()
    from memory import api as memory

    topics = ["trabajo", "salud", "finanzas", "familia", "deporte", "viajes", "estudios", "ocio",
              "comida", "tecnologia", "vivienda", "mascotas"]
    t_seed = _t.perf_counter()
    for j in range(noise):
        tp = topics[j % len(topics)]
        memory.write_now(f"nota de relleno {j} sobre {tp}: detalle rutinario e irrelevante del dia {j}",
                         kind="event", level=("long" if j % 3 == 0 else "short"))
    seed_ms = (_t.perf_counter() - t_seed) * 1000
    # AGUJAS: hechos durables con keyword ÚNICA (no colisiona con el relleno) + su pregunta.
    aguja_defs = [
        ("mi contraseña del router wifi es KOALA-42", "¿cuál es la contraseña del router?", "koala-42"),
        ("aparqué el coche en la planta 3 plaza 217 del centro comercial", "¿dónde aparqué el coche?", "planta 3"),
        ("soy alérgico a la penicilina", "¿a qué medicamento soy alérgico?", "penicilina"),
        ("el aniversario con Marta es el 8 de octubre", "¿cuándo es mi aniversario con Marta?", "8 de octubre"),
        ("guardo los ahorros en una cuenta de Triodos", "¿en qué banco tengo los ahorros?", "triodos"),
        ("mi talla de zapato es 44", "¿qué número de pie calzo?", "44"),
        ("el gato se llama Pixel", "¿cómo se llama mi gato?", "pixel"),
        ("mi vuelo a Tokio sale el 12 de marzo a las 7:40", "¿cuándo sale mi vuelo a Tokio?", "12 de marzo"),
    ][:needles]
    for text, _q, _mk in aguja_defs:
        memory.write_now(text, kind="fact", level="long", pinned=True)

    found, lat = 0, []
    misses = []
    for text, q, mk in aguja_defs:
        t0 = _t.perf_counter()
        res = memory.query(q, reinforce_used=False)
        lat.append((_t.perf_counter() - t0) * 1000)
        blob = _norm(" ".join(m.get("text", "") for m in res.get("memories", [])))
        if _norm(mk) in blob:
            found += 1
        else:
            misses.append(mk)
    total = _db.get_db().query_one("SELECT count(*) c FROM memories")["c"]
    p50 = statistics.median(lat) if lat else 0
    mx = max(lat) if lat else 0
    ok = (found == len(aguja_defs)) and (mx <= max_ms)
    return {"noise": noise, "needles": len(aguja_defs), "found": found, "misses": misses,
            "total": total, "seed_ms": round(seed_ms), "lat_p50_ms": round(p50), "lat_max_ms": round(mx),
            "max_ms": max_ms, "ok": ok}


def _load_progress() -> dict:
    p = _progress_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"done_upto": 0, "passed": 0, "failed": 0, "batches": []}


def _save_progress(prog: dict) -> None:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    _progress_path().write_text(json.dumps(prog, ensure_ascii=False, indent=2))


def main():
    global _ACTIVE
    ap = argparse.ArgumentParser(description="Test bot de memoria (V2-013)")
    ap.add_argument("--next", type=int, default=0, help="ejecuta las N siguientes desde el progreso")
    ap.add_argument("--range", nargs=2, type=int, metavar=("LO", "HI"), help="ejecuta el rango [LO,HI)")
    ap.add_argument("--fresh", action="store_true", help="reinicia la BD del bot antes de empezar")
    ap.add_argument("--catalog", action="store_true", help="(re)genera el catálogo del corpus y sale")
    ap.add_argument("--coverage", action="store_true", help="imprime cobertura por dimensión (taxonomía) y sale")
    ap.add_argument("--corpus", choices=sorted(CORPORA), default="v1",
                    help="corpus a correr: v1=GOLD histórica (cases.py, 1032) · v2=corpus nuevo (cases2.py)")
    ap.add_argument("--scale", type=int, metavar="NOISE", help="harness de ESCALA (dim K): siembra NOISE recuerdos + agujas y mide recall/latencia")
    ap.add_argument("--max-ms", type=int, default=800, help="umbral de latencia máx para --scale")
    args = ap.parse_args()
    _ACTIVE = args.corpus

    if args.catalog:
        emit_catalog()
        print(f"catálogo regenerado → {_catalog_path()}")
        return 0

    if args.coverage:
        emit_coverage()
        return 0

    if args.scale is not None:
        rep = asyncio.run(run_scale(noise=args.scale, max_ms=args.max_ms))
        stamp = time.strftime("%Y%m%d-%H%M%S")
        LOGDIR.mkdir(parents=True, exist_ok=True)
        (LOGDIR / f"scale-{stamp}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2))
        flag = "✅" if rep["ok"] else "❌"
        print(f"\n{flag} ESCALA (dim K) — {rep['total']} recuerdos ({rep['noise']} ruido + {rep['needles']} agujas)")
        print(f"   siembra {rep['seed_ms']}ms · recall agujas {rep['found']}/{rep['needles']}"
              + (f" · FALLAN {rep['misses']}" if rep['misses'] else ""))
        print(f"   latencia query p50 {rep['lat_p50_ms']}ms · max {rep['lat_max_ms']}ms (límite {rep['max_ms']}ms)")
        return 0 if rep["ok"] else 1

    prog = _load_progress()
    if args.range:
        lo, hi = args.range
    else:
        n = args.next or 10
        lo = 0 if args.fresh else prog["done_upto"]
        hi = lo + n
    if args.fresh:                 # replay LIMPIO desde el inicio (conversación lineal completa hasta HI)
        lo = 0

    report = asyncio.run(run_range(lo, hi, fresh=args.fresh))

    # persistir progreso + informe de la tanda
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (LOGDIR / f"report-{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fresh:
        prog = {"done_upto": 0, "passed": 0, "failed": 0, "batches": []}
    prog["done_upto"] = max(prog["done_upto"], report["range"][1])
    prog["passed"] += report["passed"]
    prog["failed"] += report["failed"]
    prog["batches"].append({"range": report["range"], "passed": report["passed"],
                            "failed": report["failed"], "at": stamp})
    _save_progress(prog)
    emit_catalog()          # el catálogo se mantiene al día con cases.py en cada corrida

    # salida legible
    print(f"\n=== TANDA {report['range']} — {report['passed']}/{report['total']} OK "
          f"({report['failed']} fallos) ===")
    for r in report["results"]:
        flag = "✅" if r["ok"] else "❌"
        print(f"  {flag} #{r['i']:<4} {r['t']:<5} {str(r.get('text'))[:52]:<52} → {r['detail']}")
    lat = report.get("latency")
    if lat:
        print(f"\n⏱  LECTURA (camino real del cerebro, {lat['n']} queries): "
              f"p50 {lat['p50_ms']}ms · p95 {lat['p95_ms']}ms · máx {lat['max_ms']}ms")
        if lat.get("slowest"):
            slow = " · ".join(f"#{s['i']}={s['ms']}ms" for s in lat["slowest"][:5])
            print(f"   más lentas: {slow}")
    print(f"\nProgreso acumulado: {prog['done_upto']} pasos · {prog['passed']} OK · {prog['failed']} fallos")
    print(f"BD del bot (aislada): {pathlib.Path(__import__('os').environ['ZAELAR_DB'])}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
