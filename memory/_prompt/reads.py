"""The DIRECT reads the turn pays for: microseconds, no LLM and no retriever — V2-011's golden invariant («writing
may be slow; reading must be maximum speed»). Nothing here calls a model."""
from __future__ import annotations

from .. import db as _db


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
    # INBOUND MESSAGES OUT (V2-802 T-03): this block is «what WE were talking about», and the inbox is not that.
    # With a connector live, email and group chatter outnumber the turns and pushed the conversation out of the
    # few lines this block keeps (yesterday's errand gone, marketing email in its place).
    # They remain readable by their own door (`recent_by_source`) and their own recall lane (`retriever.LANE_*`).
    rows = db.query(
        "SELECT id, text, created FROM memories WHERE level='short' AND valid=1 AND kind != 'msg' "
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
    píldoras). Solo válidos y durables; dedup por texto normalizado (varias alergias distintas SÍ coexisten).

    UNA FRASE DEL OPERADOR DEJA DOS PÍLDORAS CRÍTICAS, y el corte se aplicaba a PÍLDORAS (V2-491, 2026-08-29):
    la destilada por el CORAZÓN (`meta.path='llm'`) y la literal que guarda la red de seguridad de salud
    (`path='health-net'`, `ingest.py`). El dedup era por cadena EXACTA, así que no colapsan — son textos
    distintos — y cada hecho ocupa DOS plazas de las 6. Medido sembrando cuatro hechos críticos distintos por su
    camino real (celiaquía, frutos secos, diabetes, marcapasos): **el marcapasos DESAPARECE**, expulsado de la
    línea más prominente del prompt por las copias de los otros tres. Es exactamente el fallo que esta línea
    existe para evitar, cometido por su propio cap.

    **El enlace es EXACTO, no un parecido**, y eso es lo que lo hace seguro: la píldora destilada guarda en
    `meta.raw` la frase del operador (`ingest.py`, recortada a 120), y el texto de la píldora de la red ES esa
    frase. Así que se retira la copia cuando otra píldora crítica declara haber nacido de ella.

    ⚠️ **Deduplicar por PARECIDO se probó y se descartó con números**, porque aquí un falso positivo BORRA una
    restricción: sobre pares reales, el que SÍ debe fundirse (destilada vs literal de la celiaquía) puntúa
    jaccard 0,30 / cobertura 0,50, y los que JAMÁS deben fundirse —«alérgico a los frutos secos» vs «alérgico al
    marisco», penicilina vs ibuprofeno— puntúan 0,25-0,33 / 0,50. **Ningún umbral los separa**, así que no hay
    umbral bueno: solo el enlace por procedencia."""
    try:
        rows = _db.get_db().query(
            "SELECT text, json_extract(meta,'$.raw') AS raw FROM memories "
            "WHERE valid=1 AND level IN ('mid','long') "
            "AND json_extract(meta,'$.critical')='health' ORDER BY (importance*weight) DESC, updated DESC LIMIT ?",
            # El margen se queda en *2, el de siempre: subirlo parecía necesario «para las copias que se van a
            # retirar» y NINGÚN caso lo respalda — las destiladas pesan 0,95 y las copias 0,7, así que las que
            # sobreviven al ranking son justo las que se conservan. Un margen sin caso que lo exija es una
            # constante que nadie podrá volver a justificar.
            (int(limit) * 2,))
    except Exception:
        return []
    _plano = lambda t: " ".join((t or "").lower().split())
    # Frases del operador que ALGUNA píldora crítica declara como origen suyo.
    origenes = {_plano(r["raw"]) for r in rows if (r["raw"] or "").strip()}
    out, seen = [], set()
    for r in rows:
        t = (r["text"] or "").strip()
        k = _plano(t)
        if not t or k in seen:
            continue
        # El `raw` viaja recortado a 120, así que la copia se reconoce por PREFIJO: una frase más larga que el
        # recorte seguiría siendo la misma frase.
        if any(o and (k == o or k.startswith(o)) for o in origenes) and not (r["raw"] or "").strip():
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= limit:
            break
    return out




def tastes(limit: int = 6) -> list[str]:
    """GUSTOS Y PREFERENCIAS del operador — línea PROPIA del estado, fuera del ranking que siempre pierden.

    Norma del operador (2026-08-29): *«los gustos forman parte del estado activo — no son datos históricos ni
    cosas que hayan sucedido en el pasado, sino que tienen que estar ahí»*.

    MEDIDO sobre su memoria viva antes de escribir nada: el bloque pasivo que ve el modelo en CADA turno tenía
    DOS líneas —una regla de trabajo y un `[RESET]` del sistema— y **ni un solo gusto**, con 12 píldoras `pref`
    guardadas (Ferrari ×7, guitarra y música ×2). No se perdían al escribirse: se escriben bien y pierden el
    RANKING. `salient_long` ordena por importancia·peso y esas píldoras pesan 0,3-0,494 contra un corte de
    0,446 dominado por píldoras de 0,99. Así que el arreglo no es tocar el orden — es la misma forma que
    `critical_facts` (V2-491): lo que tiene que estar SIEMPRE no compite por una plaza.

    ⚠️ **UN SLOT ERA LA VÍA OBVIA Y ESTÁ MEDIDA COMO MUERTA.** `operator.tastes` con reflejo en el estado, calcando
    `operator.family`, era el diseño natural. Dos hechos lo tumban: (1) el prompt del CORAZÓN enseña
    EXPLÍCITAMENTE que un gusto es ADITIVO y va con `slot=null` («aficiones/gustos… → slot=null SIEMPRE»,
    porque un slot invalida lo anterior y a alguien le pueden gustar los Ferrari Y la guitarra); y (2)
    `operator.family` lleva desde el 2026-08-17 en el catálogo y se ha escrito **CERO veces** en la memoria del
    operador — la regla aditiva del destilador gana a la entrada del catálogo, así que un slot nuevo nacería
    igual de inerte. La clase ya está en el dato (`kind='pref'`, la que el propio destilador asigna a una
    preferencia/deseo) y se estaba tirando: se RENDERIZA la distinción que existe, sin slot nuevo, sin campo
    nuevo y sin lista de palabras.

    Se llama GUSTOS Y PREFERENCIAS, no «gustos», porque eso es lo que la clase contiene de verdad: junto a
    Ferrari y guitarra vive «prefiere que las tareas las haga un worker», que es una preferencia legítima sobre
    cómo trabajas. Etiquetar la línea por la clase que el dato trae es honesto; llamarla «gustos» convertiría esa
    fila en una afición.

    Los ecos casi idénticos (siete formas de «le interesan los Ferrari») NO se colapsan aquí: fundirlos es
    trabajo de `semantic_dedup`, que CONSERVA la mejor e invalida el resto. Hoy no puede hacerlo con estas filas
    —sus vectores están dañados y la reparación está bloqueada (V2-482/V2-497)—, así que hasta que sanen esta
    línea puede repetirse. Se dice aquí en vez de inventar un dedup por parecido en la capa de pintar, que es
    justo lo que V2-491 descartó con números."""
    try:
        rows = _db.get_db().query(
            "SELECT text FROM memories WHERE valid=1 AND level IN ('mid','long') AND kind='pref' "
            # mismas exclusiones que el pasivo: fondo namespaced (`:`), peers no confiables y los CRÍTICOS,
            # que tienen su propia línea y no se duplican.
            "AND (slot IS NULL OR slot NOT LIKE '%:%') "
            "AND (json_extract(meta,'$.critical') IS NULL) "
            "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted') "
            "ORDER BY (importance * weight) DESC, updated DESC LIMIT ?", (int(limit) * 3,))
    except Exception:
        return []
    out, seen = [], set()
    for r in rows:
        t = (r["text"] or "").strip().replace("\n", " ")
        k = " ".join(t.lower().split())
        if not t or k in seen:
            continue
        seen.add(k)
        out.append(t[:140])
        if len(out) >= limit:
            break
    return out


def salient_long(limit: int = 8, max_chars: int = 800) -> list[dict]:
    """LO QUE ZAELAR "SABE DE TI" — las memorias durables MÁS salientes (mayor importancia·peso), lectura DIRECTA
    (µs, sin embeddings ni retriever) — SOTA "in-context availability": un humano sabe que le gusta el pádel sin
    tener que *recordarlo*. Se enchufa cacheada en el bloque del FlashBrain (memory_cache), junto al estado y al
    corto, para que lo esencial durable esté SIEMPRE disponible sin disparar el recall semántico (V2-013). Solo
    `valid=1`, nivel durable (mid/long). Devuelve [{id, text, importance, weight, kind, verdict}]. Tolera BD vacía."""
    db = _db.get_db()
    # EXCLUYE los slots de FONDO namespaced (`weather:soria`, `<widget>:<clave>`, `cluster:…`) — auditoría de
    # memoria 2026-07-14: el bloque pasivo es "lo que zaelar sabe del OPERADOR" y se pinta con "dalo por sabido SIN
    # buscar"; un `weather:soria` volcado por el widget de fondo se colaba ahí y SECUESTRABA "¿qué tiempo hace hoy?"
    # (el cerebro leía Soria en vez de aterrizar en state.location y buscar). Los slots del operador usan `.`
    # (operator.location, goal.current…); los de fondo/widget/cluster usan `:` → quedan SUBORDINADOS a state.location
    # (fuera del pasivo). Siguen siendo recuperables por el retriever ante una pregunta EXPLÍCITA por esa ciudad.
    rows = db.query(
        "SELECT id, text, importance, weight, kind, json_extract(meta,'$.verdict') AS verdict FROM memories "
        # `pref` sale de aquí porque tiene su propia línea desde V2-498 (`tastes()`): dejarlo lo pintaría DOS
        # veces en el mismo prompt. Y libera plaza — medido en la memoria del operador, una de las dos únicas
        # que llegaban al bloque era una preferencia.
        # `msg` (V2-802 T-03): an inbound message is what someone else wrote, not what zaelar knows of HIM —
        # and rows promoted before promotion stopped taking them are still mid/long on existing installs.
        "WHERE valid=1 AND level IN ('mid','long') AND kind NOT IN ('profile','pref','msg') "
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
                    "weight": r["weight"], "kind": r["kind"], "verdict": r["verdict"] or ""})
        used += len(txt)
        if len(out) >= limit:
            break
    return out
