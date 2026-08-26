"""memory/_prompt.py — lo que la memoria PINTA para un modelo, separado de lo que GUARDA.

Sacado VERBATIM de `memory/api.py` en la auditoría de arquitectura del 2026-08-23 (hallazgo H3). La fachada
había llegado a 1.075 líneas mezclando ciclo de vida, escritura, olvido, kv, reglas de usuario y episodios con
**160 líneas de composición de PROMPT** — presentación viviendo dentro de la capa de datos. La fachada sigue
siendo LA puerta (el contrato de `memory/contract.py` lo exige y el trinquete lo vigila); lo que cambia es que
por dentro es delgada.

Aquí vive la lectura DIRECTA que el turno paga: microsegundos, sin LLM y sin retriever — el invariante de oro
de V2-011 («escribir puede ser lento; leer debe ser máxima velocidad»). Nada de este módulo llama a un modelo.

**Las CUATRO superficies que pintan píldoras** a un cerebro (bloque pasivo, dosier del worker, recall del
FlashBrain y `/api/memory/recall`) convergen en `api.query()`, que aplica la regla de la forma-de-la-clave UNA
vez; `background_slot_off_topic` se queda en `api.py` con ella, no aquí, porque es una regla de RECUPERACIÓN y
no de presentación.
"""
from __future__ import annotations

import re

from . import db as _db
from . import state as _state


_STATE_RENDERED = {"assistant_name", "operator_name", "language", "treatment", "location", "recent", "topics",
                   "open_widgets", "activity", "sessions", "mission", "rails", "rules"}

_RAIL_STATUS = {"searching": "buscando", "playing": "sonando", "paused": "en pausa",
                "sin_resolver": "SIN RESOLVER"}


def compose_state(*, mission_fallback: str = "") -> tuple[str, str, dict]:
    """Compone el ESTADO COMPARTIDO que ven AMBOS cerebros (FlashBrain y SlowBrain): pequeño, ordenado, en el
    idioma del operador. Devuelve `(bloque, operator_name, stats)`.

    Es el contrato del rediseño del prompt (V2-027): el cerebro recibe **[ESTADO compuesto] + [petición]**, y el
    ESTADO se compone aquí una sola vez (los RECURSOS/tools divergen por cerebro → capa propia). Estructura:

      A. **QUIÉN ERES** — la misión/identidad (state.mission, sembrada al init desde `langs`; `mission_fallback`
         si aún no se sembró). Es la parte FIJA; nunca un prompt inglés hardcodeado en un `.py`.
      B. **QUIÉN TIENES DELANTE** — situacional VARIABLE: operador (nombre/trato/ubicación + campos durables del
         estado), widgets ABIERTOS ahora, tareas EN MARCHA, y el perfil durable saliente ("lo que sabes de él").
      C. **DE QUÉ ÍBAIS HABLANDO** — síntesis TENSA de la conversación reciente (corto plazo con cap agresivo:
         las últimas líneas, NO el volcado crudo entero; NUNCA la memoria de largo plazo).

    Lectura DIRECTA (µs, sin LLM ni retriever) → seguro cachearla off-hot-path (`nucleo/flash/memory_cache`). El
    turno de voz NUNCA la compone sin caché (invariante V2-011). Best-effort: `('', '', {...})` si la memoria no
    está disponible. `mission_fallback` lo pasa el llamador que conoce el idioma (nucleo/flash), para no invertir
    la dependencia memoria→voz."""
    stats = {"has_state": False, "state_fields": 0, "short_count": 0, "short_chars": 0,
             "salient_count": 0, "has_mission": False, "op": ""}
    try:
        st = _state.read()
    except Exception:
        return "", "", stats
    op = (st.get("operator_name") or "").strip()
    stats["op"] = op

    # ── A · QUIÉN ERES (misión) ──────────────────────────────────────────────────────────────────────────
    mission = (st.get("mission") or "").strip() or (mission_fallback or "").strip()
    stats["has_mission"] = bool(mission)

    # ── B · QUIÉN TIENES DELANTE (situacional) ───────────────────────────────────────────────────────────
    sit: list[str] = []
    if op:
        sit.append(f"El operador se llama {op}.")
    if st.get("treatment"):
        sit.append(f"Trato preferido: {st['treatment']}.")
    # USER RULES (V2-046 A1): reglas de comportamiento que el operador impuso hablando; persisten entre sesiones
    # y viajan SIEMPRE (cacheadas, µs). Capa APRENDIDA sobre las brain rules. Vacío = ni una línea (prompt idéntico).
    rules = [str(r).strip() for r in (st.get("rules") or []) if str(r).strip()]
    if rules:
        sit.append("REGLAS DEL OPERADOR (te las dio él; síguelas SIEMPRE): "
                   + " · ".join(r[:90] for r in rules[:8]))
    if st.get("location"):
        sit.append(f"Ubicación: {st['location']}.")
    # HECHOS CRÍTICOS de seguridad (alergias/condiciones médicas): línea PROPIA y PROMINENTE que se surface SIEMPRE,
    # independiente del ranking/cap del perfil saliente — olvidar una alergia bajo densidad es un fallo de seguridad
    # (auditoría 2026-07-14). El guard del writer los marca `meta.critical='health'`.
    try:
        crit = critical_facts(limit=6)
    except Exception:
        crit = []
    if crit:
        sit.append("⚠️ CRÍTICO (tenlo SIEMPRE presente): " + " · ".join(crit))
    # Campos CUSTOM escalares del estado (objetivo/proyecto/coche/empresa/cumpleaños…): la "pila" durable del
    # operador va SIEMPRE — el cerebro debe verla sin tener que recordarla.
    for k, v in st.items():
        if k in _STATE_RENDERED:
            continue
        if isinstance(v, (str, int, float)) and str(v).strip():
            sit.append(f"{k.capitalize().replace('_', ' ')}: {v}.")
    open_w = [str(w).strip() for w in (st.get("open_widgets") or []) if str(w).strip()]
    if open_w:
        sit.append("Widgets ABIERTOS ahora en su pantalla: " + ", ".join(open_w[:12]) + ".")
    # PROCESOS/SESIONES VIVAS del SlowBrain (V2-036, P4): id + objetivo + fase, para que el orquestador (FlashBrain)
    # ASOCIE cada pregunta/orden del operador a la sesión correcta ("¿cómo va la moto?", "y el estudio del universo?",
    # "para la tarea del mercado…"). Rico (sesiones) si lo hay; si no, cae a las etiquetas de `activity`.
    sessions = [s for s in (st.get("sessions") or []) if isinstance(s, dict) and (s.get("goal") or s.get("phase"))]
    if sessions:
        lines = []
        waiting_any = False
        for s in sessions[:6]:
            sid = str(s.get("id") or "?")
            goal = (str(s.get("goal") or "")).strip().replace("\n", " ")[:90]
            phase = (str(s.get("phase") or "")).strip()[:40]
            line = f"  · [{sid}] «{goal}»" + (f" — fase: {phase}" if phase else "")
            if (s.get("waiting_on") or "") == "user":
                waiting_any = True
                ask = (str(s.get("ask") or "")).strip()[:120]
                line += f" — ESPERA tu respuesta a: «{ask}»" if ask else " — ESPERA una respuesta tuya"
            lines.append(line)
        # SOLO DATOS (auditoría 2026-07-14): la memoria compone el ESTADO COMPARTIDO; la DIRECTIVA de cómo
        # dirigir workers (refinar=inyectar, parar=matar, responder un ask) es prosa del FlashBrain y vive en su
        # capa de recursos (`nucleo/flash/prompt._flash_layer`) — V2-027: cada cerebro añade SU capa.
        head = "PROCESOS DE FONDO en marcha ahora:\n"
        if waiting_any:
            head = "⚠️ Un proceso de fondo ESPERA una respuesta del operador (abajo). " + head
        sit.append(head + "\n".join(lines))
    else:
        activity = [str(a).strip() for a in (st.get("activity") or []) if str(a).strip()]
        if activity:
            sit.append("Tareas en marcha ahora: " + "; ".join(a[:80] for a in activity[:6]) + ".")
    # RAILS con run VIVO (V2-042): comportamientos conducidos que cruzan turnos — qué se está buscando, qué suena,
    # y las búsquedas SIN RESOLVER (aisladas, con intentos) que el operador puede retomar aportando datos. Los
    # proyecta `nucleo/rails.py`; aquí SOLO datos (la guía por rail la inyecta el FlashBrain solo cuando aplica).
    rails = [a for a in (st.get("rails") or []) if isinstance(a, dict) and (a.get("label") or "").strip()]
    if rails:
        lines = []
        for a in rails[:5]:
            status = _RAIL_STATUS.get(str(a.get("status") or ""), str(a.get("status") or ""))
            line = f"  · [{str(a.get('kind') or '?')}] {status}: «{str(a['label']).strip()[:90]}»"
            det = (str(a.get("detail") or "")).strip()
            if det:
                line += f" — {det[:80]}"
            att = int(a.get("attempts") or 0)
            if att > 1:
                line += f" ({att} intentos)"
            lines.append(line)
        sit.append("Rails en curso (conducciones tuyas):\n" + "\n".join(lines))
    stats["state_fields"] = len(sit)
    stats["has_state"] = bool(sit)

    # Perfil durable SALIENTE ("lo que sabes de él", SOTA in-context availability): cap TERSO (V2-027).
    #
    # AN ERRAND IS NOT A FACT ABOUT THE PERSON (V2-317, 2026-08-26). Both used to go in the same list, under the
    # same instruction — «dalo por sabido sin buscar» — so «Vive en Madrid» and «Tarea pendiente para el
    # asistente: buscarle un coche de segunda mano» read as the same class of thing. Measured on the harness:
    # in `cheapest-monitor` the agent opened by talking about CARS, carrying over the previous case's errand.
    # And this is not a lab artefact — on the operator's own live memory **3 of the 5 slots were errands**
    # (a flight to London, a plumber that ran out of quota, a worker test), crowding out the actual person.
    #
    # The class is ALREADY in the data and was being thrown away: `mem_processor` is explicit that a task the
    # operator delegates is `kind="result"` («jamás a goal.current ni al state.objetivo»), and `salient_long`
    # returns `kind` — `compose_state` just never looked at it. So no word list and no new field: the
    # distinction that exists gets rendered instead of flattened. Errands stay VISIBLE and stay readable as
    # pending — suppressing them would trade this failure for the opposite one, an agent that forgets what it
    # was asked — but they are no longer presented as things to take for granted about the person.
    salient: list[str] = []
    errands: list[str] = []
    try:
        for m in salient_long(limit=5, max_chars=440):
            t = (m.get("text") or "").strip().replace("\n", " ")
            if not t:
                continue
            (errands if m.get("kind") == "result" else salient).append(f"· {t[:140]}")
    except Exception:
        pass
    stats["salient_count"] = len(salient)
    stats["errand_count"] = len(errands)

    # ── C · DE QUÉ ÍBAIS HABLANDO (síntesis TENSA del corto plazo) ────────────────────────────────────────
    # V2-027: sustituye el volcado CRUDO de 30 líneas / 1800 chars por las ÚLTIMAS pocas líneas (cap agresivo).
    # Sigue siendo lectura DIRECTA (µs, sin LLM) — la "síntesis" es el recorte, no un resumen por modelo (que, si
    # se quisiera, iría OFF del turno como el resto de la escritura). Da el hilo reciente sin inflar el prompt.
    convo: list[str] = []
    short_chars = 0
    try:
        for m in recent_short(limit=5, max_chars=550):
            t = (m.get("text") or "").strip().replace("\n", " ")
            if t:
                convo.append(f"· {t[:180]}")
                short_chars += len(t)
    except Exception:
        pass
    stats["short_count"] = len(convo)
    stats["short_chars"] = short_chars

    if not (mission or sit or salient or errands or convo):
        return "", op, stats

    parts: list[str] = []
    if mission:
        parts.append("── QUIÉN ERES ──\n" + mission)
    if sit or salient or errands:
        b = "── QUIÉN TIENES DELANTE (trátalo como sabido de siempre; salúdalo por su nombre sin volver a preguntar) ──"
        if sit:
            b += "\n" + "\n".join(sit)
        if salient:
            b += "\n[Lo que sabes de él, dalo por sabido sin buscar]\n" + "\n".join(salient)
        if errands:
            # Says what they ARE, and nothing about what to do with them. The line is deliberately not an order
            # in either direction: «ignore these» would be the opposite failure (an agent that forgets what it
            # was asked), and «handle these» is what produced the measured defect. Judgement stays with the
            # brain — same doctrine as `workers/findings.py`.
            b += ("\n[Encargos que te hizo en algún momento — NO son hechos sobre él, y pueden estar ya "
                  "hechos o caducados. No empieces a trabajar en uno salvo que él lo saque en este turno]\n"
                  + "\n".join(errands))
        parts.append(b)
    if convo:
        parts.append("── DE QUÉ ÍBAIS HABLANDO (lo más reciente primero; el último MANDA si hay contradicción) ──\n"
                     + "\n".join(convo))
    block = "\n\n".join(parts)
    return block, op, stats




def recent_short(limit: int = 30, max_chars: int = 1800) -> list[dict]:
    """CORTO PLAZO reciente, LECTURA DIRECTA (µs, sin embeddings ni retriever) — el "working set" que se enchufa
    ENTERO al prompt (V2-013 T146): la memoria de corto plazo es pequeña y cabe, así que en vez de buscar
    (lento, y hoy poco fiable) el modelo la ve completa. Más reciente primero, acotado por nº y por chars para
    no inflar el prompt/latencia. Devuelve [{id, text, created}]. Tolera BD vacía."""
    db = _db.get_db()
    # Orden DETERMINISTA: `updated` tiene resolución de segundo → varias escrituras en el mismo segundo empatan y
    # el desempate arbitrario haría que un turno MÁS reciente cayera fuera de la ventana (rompe "el más reciente
    # MANDA" de la recencia). Desempatamos por `id` (monótono, orden de inserción) → la recencia es estable.
    # CUARENTENA por CONFIANZA (multi-fuente 2026-07-10): lo `trust='untrusted'` (peers de cluster, agentes
    # ajenos) NUNCA entra en el bloque PASIVO que ve el FlashBrain cada turno — evita que un peer no confiable
    # inyecte instrucciones en el prompt del operador. Sigue siendo recuperable por consulta EXPLÍCITA
    # (`recent_by_source`) o recall dirigido. Lo del propio dueño (operator/external) sí entra.
    rows = db.query(
        "SELECT id, text, created FROM memories WHERE level='short' AND valid=1 "
        "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted') "
        "ORDER BY updated DESC, id DESC LIMIT ?", (int(limit),)
    )
    out, used = [], 0
    for r in rows:
        txt = (r["text"] or "").strip()
        if not txt:
            continue
        if used + len(txt) > max_chars and out:
            break
        out.append({"id": r["id"], "text": txt, "created": r["created"]})
        used += len(txt)
    return out


def recent_window(limit: int = 6, max_chars: int = 1600) -> list[dict]:
    """VENTANA CONVERSACIONAL verbatim (los últimos turnos LITERALES operador↔zaelar), LECTURA DIRECTA (µs, sin
    LLM ni retriever). Reconstruye los pares del BUFFER de corto `kind='conv'` (que escribe el provider cada turno)
    en mensajes listos para SEMBRAR `brain._window` tras un reinicio/reconexión — así el FlashBrain no pierde "de
    qué hablábamos" cuando su ventana en memoria arranca vacía (circuito de corto plazo, 2026-07-14). Devuelve
    `[{role, content}]` MÁS ANTIGUO primero (orden natural de chat). Prefiere los campos estructurados `meta.u`/
    `meta.a`; si un registro viejo no los tiene, parsea el texto "Operador: … · zaelar: …". Tolera BD vacía."""
    import json as _json
    db = _db.get_db()
    rows = db.query(
        "SELECT text, meta, created FROM memories WHERE level='short' AND valid=1 "
        "AND json_extract(meta,'$.source')='conv' "
        "ORDER BY updated DESC, id DESC LIMIT ?", (int(limit),)
    )
    pairs: list[tuple[str, str, float]] = []
    used = 0
    for r in rows:                                    # vienen NUEVO→VIEJO; recortamos por chars y luego invertimos
        u = a = ""
        try:
            meta = _json.loads(r["meta"]) if r["meta"] else {}
            u = (meta.get("u") or "").strip()
            a = (meta.get("a") or "").strip()
        except Exception:
            meta = {}
        if not u and not a:                            # registro viejo sin meta estructurado → parsea el texto
            txt = (r["text"] or "")
            if "· zaelar:" in txt:
                left, _, right = txt.partition("· zaelar:")
                u = left.replace("Operador:", "", 1).strip()
                a = right.strip()
            else:
                u = txt.strip()
        seg = len(u) + len(a)
        if used + seg > max_chars and pairs:
            break
        pairs.append((u, a, float(r["created"] or 0)))
        used += seg
    out: list[dict] = []
    for u, a, ts in reversed(pairs):                   # VIEJO→NUEVO
        # `ts` = epoch seconds this pair was written (V2-105 follow-up, 2026-08-17): lets a caller that needs
        # RECENCY — not just "is there any conversation" — filter out an entry from hours/days ago. The 2-day
        # TTL on this buffer is deliberate continuity for the FlashBrain's own "what were we talking about"
        # (voice/engine/pipeline/agent.py's reconnect-vs-new-session read), so `recent_window` keeps returning
        # everything within TTL by default; filtering by `ts` is opt-in per caller, not a change here.
        if u:
            out.append({"role": "user", "content": u, "ts": ts})
        if a:
            out.append({"role": "assistant", "content": a, "ts": ts})
    return out


def seconds_since_last_conv() -> float | None:
    """Segundos desde el ÚLTIMO turno conversacional (buffer corto `source='conv'`), o None si no hay ninguno.
    Sirve para que el kickoff (voice/engine/pipeline/agent.py) distinga una sesión NUEVA de una RECONEXIÓN a una
    conversación EN CURSO: si el operador habló hace un momento, reconectar NO debe re-saludar como si fuera el
    primer turno (bug 2026-07-25: cada reconexión soltaba «Hola, ¿qué necesitas?» en mitad de la charla). Lectura
    directa µs, tolera BD vacía."""
    try:
        db = _db.get_db()
        row = db.query(
            "SELECT MAX(created) AS c FROM memories WHERE level='short' AND valid=1 "
            "AND json_extract(meta,'$.source')='conv'"
        )
        c = (row[0]["c"] if row else None)
        if not c:
            return None
        return max(0.0, __import__("time").time() - float(c))
    except Exception:
        return None


def critical_facts(limit: int = 8) -> list[str]:
    """Hechos CRÍTICOS de seguridad (alergias, intolerancias, condiciones médicas) marcados `meta.critical='health'`
    por el guard del writer. Lectura DIRECTA. Van a una LÍNEA PROPIA del estado (compose_state) que se surface
    SIEMPRE — nunca dependen del ranking/cap de `salient_long`: olvidar una alergia bajo densidad es un fallo de
    seguridad (auditoría de memoria 2026-07-14, hallazgo del corpus v3: la penicilina se enterraba bajo ~130
    píldoras). Solo válidos y durables; dedup por texto normalizado (varias alergias distintas SÍ coexisten)."""
    try:
        rows = _db.get_db().query(
            "SELECT text FROM memories WHERE valid=1 AND level IN ('mid','long') "
            "AND json_extract(meta,'$.critical')='health' ORDER BY (importance*weight) DESC, updated DESC LIMIT ?",
            (int(limit) * 2,))
    except Exception:
        return []
    out, seen = [], set()
    for r in rows:
        t = (r["text"] or "").strip()
        k = " ".join(t.lower().split())
        if t and k not in seen:
            seen.add(k)
            out.append(t)
        if len(out) >= limit:
            break
    return out




def salient_long(limit: int = 8, max_chars: int = 800) -> list[dict]:
    """LO QUE ZAELAR "SABE DE TI" — las memorias durables MÁS salientes (mayor importancia·peso), lectura DIRECTA
    (µs, sin embeddings ni retriever) — SOTA "in-context availability": un humano sabe que le gusta el pádel sin
    tener que *recordarlo*. Se enchufa cacheada en el bloque del FlashBrain (memory_cache), junto al estado y al
    corto, para que lo esencial durable esté SIEMPRE disponible sin disparar el recall semántico (V2-013). Solo
    `valid=1`, nivel durable (mid/long). Devuelve [{id, text, importance, weight, kind}]. Tolera BD vacía."""
    db = _db.get_db()
    # EXCLUYE los slots de FONDO namespaced (`weather:soria`, `<widget>:<clave>`, `cluster:…`) — auditoría de
    # memoria 2026-07-14: el bloque pasivo es "lo que zaelar sabe del OPERADOR" y se pinta con "dalo por sabido SIN
    # buscar"; un `weather:soria` volcado por el widget de fondo se colaba ahí y SECUESTRABA "¿qué tiempo hace hoy?"
    # (el cerebro leía Soria en vez de aterrizar en state.location y buscar). Los slots del operador usan `.`
    # (operator.location, goal.current…); los de fondo/widget/cluster usan `:` → quedan SUBORDINADOS a state.location
    # (fuera del pasivo). Siguen siendo recuperables por el retriever ante una pregunta EXPLÍCITA por esa ciudad.
    rows = db.query(
        "SELECT id, text, importance, weight, kind FROM memories "
        "WHERE valid=1 AND level IN ('mid','long') AND kind != 'profile' "
        "AND (slot IS NULL OR slot NOT LIKE '%:%') "
        "AND (json_extract(meta,'$.critical') IS NULL) "        # los CRÍTICOS van en su línea propia (no aquí, sin dup)
        "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted') "
        "ORDER BY (importance * weight) DESC, updated DESC LIMIT ?", (int(limit) * 3,)
    )
    out, used = [], 0
    for r in rows:
        txt = (r["text"] or "").strip()
        if not txt:
            continue
        if used + len(txt) > max_chars and out:
            break
        out.append({"id": r["id"], "text": txt, "importance": r["importance"],
                    "weight": r["weight"], "kind": r["kind"]})
        used += len(txt)
        if len(out) >= limit:
            break
    return out

