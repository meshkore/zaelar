"""tests/memory/e2e/bot/cases3.py — THIRD corpus for the memory bot test: EFFICIENCY UNDER REAL LOAD.

Operator request (2026-07-14): «little tests with four pieces of data in memory are no use to me; if we put them all in,
the LLM always gets it right». Correct handling of a datum is already covered by v1 (GOLD) and v2 (genericity + audit).
This corpus tests what neither does: **does the system find the right datum, quickly, when memory is FULL of a person's
real life?** It simulates **40 DAYS of dense activity** (hundreds of messages, appointments that move and are cancelled,
studies, purchases, routines) and THEN searches for NEEDLES buried in that haystack — measuring accuracy AND latency.

Three axes that v1/v2 do not address:
  1. **REALISTIC DENSITY** — the haystack is not "filler note 47": it is real roster messages (partner, family,
     publisher, climbing group, ikastola, bank, veterinarian) with deliberate DISTRACTORS (5 restaurants the partner
     recommended, 3 dentist appointments, dozens of climbing messages) → retrieval has to DISCRIMINATE, not merely find.
  2. **EFFICIENCY** — the runner summarizes READ latency (p50/p95/max, the brain's real path without an LLM). The
     `scale` cases sweep INTENSITY PROFILES (light 150 · moderate 600 · intensive 2500 · extreme 5000) with a latency
     threshold → "is it fast?" becomes a number, and we know where it degrades.
  3. **INVARIANTS under load** — supersede/quarantine/forgetting/consolidation/worker writing exercised with the FULL
     database, not an empty one (which is when they truly matter).

Person: **Amaia Etxeberria** (the same as v2 — continuity; now with 40 days of life added). Run in isolation:
`python -m tests.memory.e2e.bot.runner --corpus v3 --fresh --range 0 N` (BD zaelar.membot3.db / progress-v3.json /
CATALOG3.md). REPEATABLE and deterministic (no randomness or clock) → useful for re-verifying architecture refactors.

Format of each case = identical to cases.py/cases2.py. The AGGREGATION (below) puts the entire haystack in FIRST (day 0 →
40-day stream) and THEN the deferred queries → each needle is queried with hundreds of intervening memories.
"""
from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# CONSTRUCTION HELPERS (compact → density without verbosity; deterministic).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════

def _msg(platform, sender, text, marker, durable=True, trust="external", note="pajar"):
    """INCOMING message (WhatsApp/Telegram) → `connector`. `durable=True` → goes to durable memory (mid) through
    message triage: it is the CHEAP haystack (`ingest_message` writes VERBATIM, without an LLM) and is also indexed by
    source. The marker is a distinctive substring of the text (indexing verification)."""
    return {"t": "connector", "platform": platform, "sender": sender, "text": text, "marker": marker,
            "trust": trust, "in": (["long"] if durable else ["short"]), "durable": durable,
            "dim": "G", "note": note}


def _say(text, marker, dest="long", state_key=None, dim=None, note="aguja (camino real del CORAZÓN)"):
    """Operator utterance → `save` (passes through the LLM CORE). For profile NEEDLES, anchor to a HARD token
    (proper name / number) that distillation does not paraphrase."""
    st = {"t": "save", "text": text, "marker": marker, "note": note}
    if dest == "state":
        st["in"] = ["state"]
        if state_key:
            st["state_key"] = state_key
        st["dim"] = dim or "A"
    elif dest == "discard":
        st["in"] = []
        st["dim"] = dim or "E"
    elif dest in ("short", "long"):
        st["in"] = [dest]
        st["dim"] = dim or ("C" if dest == "long" else "B")
    else:  # any of the layers
        st["any"] = list(dest)
        st["dim"] = dim or "C"
    return st


def _turn(op, hb, dim="B", note="recencia (charla mundana del día)"):
    return {"t": "turn", "op": op, "hb": hb, "dim": dim, "note": note}


def _q(q, want, not_want=None, via="long", dim="C", note=""):
    st = {"t": "query", "q": q, "via": via, "want": (want if isinstance(want, list) else [want]),
          "dim": dim, "note": note}
    if not_want:
        st["not_want"] = not_want if isinstance(not_want, list) else [not_want]
    return st


# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# DAY 0 — PROFILE SETUP. The basics that will be asked about ~300 steps later (retention under density).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
DIA0 = [
    _say("Hola, me llamo Amaia.", "amaia", "state", "operator_name", "A", "nombre → estado"),
    _say("Vivo en Logroño, aunque soy de Donostia.", "logrono", "state", "location", "A", "ubicación → estado"),
    _say("Prefiero que me hables claro y sin tecnicismos.", "claro", "state", "treatment", "A", "trato → estado"),
    _say("Mi pareja se llama Iván y es fisioterapeuta.", "ivan", "long", note="pareja → durable"),
    _say("Tengo una hija de siete años, Kattalin.", "kattalin", "long", note="hija → durable"),
    _say("Tenemos un gato que se llama Otto.", "otto", "long", note="gato (no perro) → durable"),
    _say("Soy alérgica a la penicilina desde pequeña.", "penicilina", "long", note="alergia crítica → durable"),
    _say("Mi hermano Xabier vive en Berlín.", "xabier", "long", note="hermano → durable"),
    _say("Doy clases de física y química en un instituto.", "fisica", "long", note="oficio → durable"),
    _say("Conduzco un Dacia Duster gris.", "duster", "long", note="coche → durable"),
    _q("¿Cómo me llamo?", "amaia", via="state", dim="A", note="identidad tras 40 días"),
    _q("¿A qué soy alérgica?", "penicilina", dim="C", note="seguridad: alergia tras 40 días de ruido"),
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# THE HAYSTACK — 40 days of dense messages. Real roster, coherent topics, deliberate DISTRACTORS within each
# topic. All durable (triage puts them into memory) → the retriever will have to discriminate among hundreds.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════

# — IVÁN (partner, WhatsApp, almost daily): household logistics + the 5 RESTAURANTS (only 1 is the anniversary one) —
_IVAN = [
    ("¿Compro pan de camino a casa o ya has ido tú?", "pan de camino"),
    ("Recojo yo a Kattalin del cole hoy, tú acaba las correcciones.", "recojo yo a kattalin"),
    ("El técnico de la caldera viene el jueves por la mañana.", "tecnico de la caldera"),
    ("Ceno fuera con los del gimnasio, no me esperes.", "ceno fuera con los del gimnasio"),
    ("Han cambiado el turno, salgo tarde de la clínica.", "salgo tarde de la clinica"),
    ("Probé el sitio nuevo de pintxos, el Bergara, está bien para un vermú.", "bergara"),
    ("Fuimos con los de trabajo al Kabo, la sidra estaba floja.", "kabo"),
    ("Me han recomendado el Ikaitz para comer de menú entre semana.", "ikaitz"),
    ("El Rekondo es carísimo, mejor lo dejamos para una ocasión muy especial.", "rekondo"),
    ("He reservado en el Portalón para nuestro aniversario, a las nueve.", "portalon"),
    ("Te quiero, ánimo con el libro.", "animo con el libro"),
    ("¿Ponemos lavadora esta noche o mañana?", "ponemos lavadora"),
    ("Kattalin quiere macarrones otra vez, se lo hago yo.", "macarrones otra vez"),
    ("Voy a llevar el Duster a que le cambien las ruedas de invierno.", "ruedas de invierno"),
]

# — CLIMBING GROUP "Mendi" (WhatsApp, Gorka and others): dates, equipment, routes → equipment/place distractors —
_MENDI = [
    ("Gorka: este sábado vamos a Etxauri si el tiempo aguanta.", "etxauri"),
    ("Gorka: yo llevo las cuerdas, tú trae los mosquetones y el arnés nuevo.", "mosquetones"),
    ("Leire: yo pongo los pies de gato de repuesto por si acaso.", "pies de gato"),
    ("Gorka: el finde que viene mejor Riglos, hay mucha gente en Etxauri.", "riglos"),
    ("Iñaki: llevo el hornillo y el café para la mañana.", "hornillo"),
    ("Gorka: acordaos de traer agua, arriba no hay fuente.", "arriba no hay fuente"),
    ("Leire: ¿alguien tiene un ocho de repuesto? Perdí el mío.", "ocho de repuesto"),
    ("Gorka: la vía de la izquierda es un 6a, la de la derecha un 5c.", "6a"),
    ("Maider: el refugio de Ordesa lo reservé para el puente.", "refugio de ordesa"),
    ("Gorka: quedamos a las siete en el parking de siempre.", "parking de siempre"),
    ("Leire: yo esta semana no puedo, tengo guardia en el hospital.", "guardia en el hospital"),
    ("Gorka: llevad casco, la última vez cayeron piedras.", "cayeron piedras"),
]

# — Almadía PUBLISHER (Telegram, Reyes): the popular-science book → dates, cover, sales, events —
_EDITORIAL = [
    ("Reyes: la fecha de entrega del manuscrito es el 15 de noviembre, no lo olvides.", "15 de noviembre"),
    ("Reyes: el diseño de portada ya está aprobado, te lo enseño mañana.", "portada ya esta aprobado"),
    ("Reyes: nos gustaría un título más corto, el actual es larguísimo.", "titulo mas corto"),
    ("Reyes: las ventas del primer libro van muy bien, 2000 ejemplares.", "2000 ejemplares"),
    ("Reyes: te han invitado a la feria del libro de Durango en diciembre.", "feria del libro de durango"),
    ("Reyes: el corrector ha marcado un par de dudas en el capítulo cuatro.", "capitulo cuatro"),
    ("Reyes: firmamos el contrato del segundo libro la semana que viene.", "contrato del segundo libro"),
    ("Reyes: la entrevista de la radio es el día 20 a las diez.", "entrevista de la radio"),
    ("Reyes: adjunto las galeradas para que las revises.", "galeradas"),
    ("Reyes: el anticipo ya está transferido, avísame cuando llegue.", "anticipo ya esta transferido"),
]

# — FAMILY: Xabier (Telegram, Berlin) + Begoña (WhatsApp, mother) —
_FAMILIA = [
    ("Xabier: me mudo a un piso nuevo en Kreuzberg el mes que viene.", "kreuzberg"),
    ("Xabier: mi vuelo a Bilbao llega el 22 por la tarde, ¿me recoges?", "vuelo a bilbao"),
    ("Xabier: aquí en Berlín ya está nevando, un frío horrible.", "berlin ya esta nevando"),
    ("Xabier: he empezado un curso de alemán avanzado por las noches.", "curso de aleman"),
    ("Xabier: ¿sigue en pie lo de esquiar en Semana Santa?", "esquiar en semana santa"),
    ("Begoña: he encontrado fotos tuyas de bebé, te las escaneo.", "fotos tuyas de bebe"),
    ("Begoña: no te olvides de la revisión del corazón que tienes pendiente.", "revision del corazon"),
    ("Begoña: hice marmitako, te guardo un táper para el finde.", "marmitako"),
    ("Begoña: la vecina del quinto se ha roto la cadera, pobre.", "roto la cadera"),
    ("Begoña: ¿a qué hora venís el domingo a comer?", "domingo a comer"),
]

# — IKASTOLA / Kattalin's school (WhatsApp: "ikastola", Maddi another mother) —
_IKASTOLA = [
    ("ikastola: reunión de padres el martes a las cinco en el aula de Kattalin.", "reunion de padres"),
    ("ikastola: excursión al caserío-museo el jueves, traer almuerzo.", "caserio-museo"),
    ("ikastola: hay piojos en clase, revisad a los peques.", "piojos en clase"),
    ("ikastola: la función de Navidad será el día 19 por la tarde.", "funcion de navidad"),
    ("Maddi: ¿llevas tú a las niñas a natación el miércoles?", "natacion el miercoles"),
    ("Maddi: Kattalin se ha dejado el chubasquero en mi coche.", "chubasquero"),
    ("ikastola: entrega de notas y tutorías la próxima semana.", "entrega de notas"),
    ("Maddi: el cumple de mi hija es el sábado en el txoko.", "txoko"),
]

# — NOTIFICATIONS / services (bank, pharmacy, courier, veterinarian Ane) —
_SERVICIOS = [
    ("banco: cargo de 59,90 € de tu seguro del coche.", "59,90"),
    ("banco: tu nómina ha sido ingresada.", "nomina ha sido ingresada"),
    ("farmacia: tu medicación para la migraña está lista para recoger.", "medicacion para la migrana"),
    ("mensajería: tu paquete se entregará mañana entre las 10 y las 14.", "paquete se entregara manana"),
    ("Ane (veterinaria): Otto necesita la vacuna anual, pide cita cuando puedas.", "vacuna anual"),
    ("banco: se ha detectado un acceso desde un dispositivo nuevo.", "acceso desde un dispositivo nuevo"),
    ("mensajería: no pudimos entregar tu paquete, reprograma la entrega.", "reprograma la entrega"),
    ("Ane (veterinaria): los análisis de Otto han salido perfectos.", "analisis de otto"),
    ("farmacia: ya tenemos tu protector solar del que preguntaste.", "protector solar"),
    ("banco: recordatorio del recibo de la luz, 74,20 €.", "74,20"),
]

_HAYSTACK = (
    [_msg("whatsapp", "Iván", t, m) for t, m in _IVAN] +
    [_msg("whatsapp", "grupo Mendi", t, m) for t, m in _MENDI] +
    [_msg("telegram", "editorial Almadía", t, m) for t, m in _EDITORIAL] +
    [_msg("telegram" if t.startswith("Xabier") else "whatsapp",
          "Xabier" if t.startswith("Xabier") else "Begoña", t, m) for t, m in _FAMILIA] +
    [_msg("whatsapp", "Maddi" if t.startswith("Maddi") else "ikastola", t, m) for t, m in _IKASTOLA] +
    [_msg("telegram" if t.startswith(("banco", "mensajería")) else "whatsapp",
          t.split(":")[0].split(" (")[0], t, m) for t, m in _SERVICIOS]
)

# — MUNDANE CHAT (recency turns, not durable → pure working-set churn) —
_CHATTER = [
    _turn("Menudo día, tres reuniones seguidas y sin comer.", "Vaya maratón, descansa un poco."),
    _turn("Estoy corrigiendo los exámenes de la segunda evaluación.", "Ánimo, ya queda menos."),
    _turn("Hoy hace un frío que pela en el instituto, la calefacción no tira.", "Abrígate bien."),
    _turn("Otto ha vuelto a tirar la planta del salón.", "Este Otto no para."),
    _turn("Kattalin ha aprendido a montar en bici sin ruedines.", "¡Qué mayor se hace!"),
    _turn("He dormido fatal, otra vez la migraña.", "Cuídate, bebe agua."),
    _turn("Estoy escribiendo el capítulo sobre el sistema solar.", "Suena apasionante."),
    _turn("Iván ha hecho una tortilla de patata buenísima.", "Qué envidia."),
    _turn("Llueve tanto que hemos suspendido la escalada.", "Otra vez será."),
    _turn("Hemos jugado al ajedrez y Kattalin casi me gana.", "Cuidado, que aprende rápido."),
    _turn("Me he apuntado a un taller de cerámica los lunes.", "Qué buen plan."),
    _turn("El coche hace un ruido raro al frenar.", "Míralo pronto, no lo dejes."),
]

# — Profile NEEDLES buried in the stream (save → CORE; anchored to a HARD token) —
_NEEDLES_SAVE = [
    _say("El código del candado de mi bici es 7391.", "7391", "long", note="aguja: código numérico"),
    _say("El pediatra de Kattalin es el doctor Salaverri.", "salaverri", "long", note="aguja: nombre propio"),
    _say("La contraseña del wifi de casa es MENDIZORROTZA22.", "mendizorrotza22", "long", note="aguja: password"),
    _say("Aparqué en el parking de Chile, planta -2, plaza 118.", "plaza 118", "long", note="aguja: ubicación puntual"),
    _say("Estuve investigando la fermentación láctica para una charla.", "fermentacion", "long", note="aguja: estudio"),
    _say("Le prometí a Kattalin que iríamos al acuario de San Sebastián en su cumpleaños.", "acuario", "long",
         note="aguja: promesa"),
    _say("El presupuesto de las obras de la cocina es de 8400 euros.", "8400", "long", note="aguja: cifra"),
    _say("Toco el txistu en el grupo de la ikastola.", "txistu", "long", note="aguja: dato inesperado"),
    _say("Guardo los ahorros en una cuenta de Laboral Kutxa.", "laboral kutxa", "long", note="aguja: banco"),
    _say("Mi talla de pies de gato es la 38.", "38", "long", note="aguja: talla escalada"),
]

# — Repeated ROUTINES (same habit several times → reinforces the pattern) —
_RUTINAS = [
    _say("Los martes y jueves entreno escalada a las siete de la tarde.", "martes y jueves", "long", "O"),
    _say("Suelo salir a correr al parque del Ebro los domingos por la mañana.", "parque del ebro", "long", "O"),
    _say("Todos los lunes tengo taller de cerámica después de clase.", "taller de ceramica", "long", "O"),
]

_STREAM = _HAYSTACK + _CHATTER + _NEEDLES_SAVE + _RUTINAS

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# CHANGING EVENTS — appointments that move/cancel and a profile that mutates (supersede under density). They are
# inserted into the stream and queried at the end. The OLD VALUE must not leak (not_want).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_CHANGES = [
    # appointment moved: Thursday 5 → Friday 6
    _say("La reunión con la editorial es el jueves a las cinco.", "jueves", "long", "C", note="base a mover"),
    _say("Al final la reunión con la editorial se mueve al viernes a las seis.", "viernes", "long", "X",
         note="reprogramación (supersede implícito)"),
    # appointment cancelled
    _say("Tengo cita en el taller para el coche el día doce.", "dia doce", "long", "C", note="base a cancelar"),
    _say("He cancelado la cita del taller del coche, ya no hace falta.", "cancelado la cita del taller", "long", "X",
         note="cancelación"),
    # city move (superseded state)
    _say("Me acabo de mudar a Vitoria por el trabajo de Iván.", "vitoria", "state", "location", "AD",
         note="mudanza declarada → estado actualizado + supersede (sin nombrar la ciudad origen)"),
    # career pivot (implicit invalidation)
    _say("He dejado las clases en el instituto, ahora me dedico a la divulgación científica a tiempo completo.",
         "divulgacion cientifica", "long", "X", note="pivote de oficio"),
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# MULTI-HOP — two links separated in time that a single question must COMPOSE.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_MULTIHOP = [
    _say("El cumpleaños de mi hermano Xabier es el 3 de mayo.", "3 de mayo", "long", "U", note="eslabón 1"),
    # (link 2 "Kreuzberg" is already in the family _HAYSTACK)
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# RETRIEVAL UNDER DENSITY — the 16 distinct use cases. Each query is resolved through the brain's REAL PATH
# (brain_view = state + salient + short + recall) against the ALREADY FULL database.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_RETRIEVAL = [
    # 1 · Exact durable FACT (profile needle amid noise)
    _q("¿Cuál es el código del candado de mi bici?", "7391", dim="C", note="1·hecho exacto: código"),
    _q("¿Cómo se llama el pediatra de Kattalin?", "salaverri", dim="C", note="1·hecho exacto: nombre"),
    _q("¿Cuál es la contraseña del wifi de casa?", "mendizorrotza22", dim="C", note="1·hecho exacto: password"),
    _q("¿En qué banco tengo los ahorros?", "laboral kutxa", dim="C", note="1·hecho exacto: banco"),
    _q("¿Dónde aparqué el coche?", "plaza 118", dim="C", note="1·hecho exacto: ubicación puntual"),

    # 2 · MESSAGE by CONTENT (recover what someone said, among dozens of messages)
    _q("¿Qué me pidió Gorka que llevara a la escalada?", "mosquetones", dim="G", note="2·mensaje por contenido"),
    _q("¿Cuándo tengo que entregar el manuscrito?", "15 de noviembre", dim="G", note="2·mensaje por contenido"),
    _q("¿Qué necesita Otto según la veterinaria?", "vacuna", dim="G", note="2·mensaje por contenido"),
    _q("¿Cuándo es la reunión de padres de la ikastola?", "martes", dim="G", note="2·mensaje por contenido"),

    # 3 · MESSAGE by SOURCE (index, not retriever): "what have I received from X?"
    {"t": "source_query", "source": "telegram", "entity": "Xabier", "want": ["kreuzberg"], "dim": "G",
     "note": "3·por fuente: lo de Xabier"},
    {"t": "source_query", "source": "telegram", "entity": "editorial Almadía", "want": ["2000 ejemplares"],
     "dim": "G", "note": "3·por fuente: lo de la editorial"},
    {"t": "source_query", "source": "whatsapp", "entity": "grupo Mendi", "want": ["etxauri"], "dim": "G",
     "note": "3·por fuente: el grupo de escalada"},

    # 4 · DISCRIMINATION among NEAR-DUPS (5 of Iván's restaurants → only the anniversary one)
    _q("¿Dónde ha reservado Iván para nuestro aniversario?", "portalon",
       not_want=["bergara", "kabo", "ikaitz", "rekondo"], dim="C", note="4·discriminación: 5 restaurantes"),

    # 5 · MOVED APPOINTMENT (as-of: the new value wins, the old one does NOT filter)
    _q("¿Qué día es finalmente la reunión con la editorial?", "viernes", not_want=["jueves"], dim="X",
       note="5·movida: viernes manda sobre jueves"),

    # 6 · CANCELLED APPOINTMENT (reflects the cancellation)
    _q("¿Sigue en pie la cita del taller del coche?", "cancelado", dim="X", note="6·cancelada"),

    # 7 · SUPERSEDED PROFILE under density (move)
    _q("¿En qué ciudad vivo ahora?", "vitoria", not_want=["logrono"], via="state", dim="AD",
       note="7·estado superseded: Vitoria, no Logroño"),

    # 8 · MULTI-HOP (compose sibling + where + when)
    _q("¿Dónde vive y cuándo cumple años mi hermano?", ["kreuzberg", "3 de mayo"], dim="U", note="8·multi-hop"),

    # 9 · VOCAB-GAP by MEANING (question with no lexical overlap with the fact)
    {"t": "recall_probe", "save": ["Toco el txistu en el grupo de la ikastola."],
     "q": "¿Qué instrumento musical sé tocar?", "want": ["txistu"], "dim": "T", "note": "9·vocab-gap"},
    {"t": "recall_probe", "save": ["Estuve investigando la fermentación láctica para una charla."],
     "q": "¿Sobre qué tema preparé una ponencia?", "want": ["fermentacion"], "dim": "T", "note": "9·vocab-gap"},

    # 10 · STUDY / RESEARCH
    _q("¿Qué estuve investigando para una charla?", "fermentacion", dim="C", note="10·estudio"),

    # 11 · ANTI-HALLUCINATION (a never-given datum must not produce a fabricated answer). NB: the retriever surfacing
    #      the cat Otto is NOT a memory failure — it is the BRAIN that must not call it a "dog"; the read path does not ensure this.
    _q("¿Cuál es mi color favorito?", [], dim="AA", note="11·anti-alucinación: dato nunca dado, sin fabricar"),
    _q("¿Cómo se llama mi empresa de coches de carreras?", [], dim="AA",
       note="11·anti-alucinación: entidad inexistente, sin inventar"),

    # 12 · PROMISE
    _q("¿Qué le prometí a Kattalin para su cumpleaños?", "acuario", dim="C", note="12·promesa"),

    # 13 · ROUTINE under density
    _q("¿Qué días entreno escalada?", ["martes", "jueves"], dim="O", note="13·rutina"),
    _q("¿Dónde salgo a correr los domingos?", "ebro", dim="O", note="13·rutina"),

    # 14 · FIGURE amid noise (many bank amounts in between)
    _q("¿Cuánto cuestan las obras de la cocina?", "8400", dim="C", note="14·cifra entre importes"),

    # 15 · CAREER PIVOT (implicit invalidation). No not_want: the pivot sentence itself names the old occupation
    #      ("I left teaching at the school, now…") → requiring its absence would be unfair (it appears in the fact).
    _q("¿A qué me dedico ahora?", "divulgacion", dim="X", note="15·pivote de oficio: aflora el nuevo"),

    # 16 · CRITICAL safety DATA, ALWAYS retrievable (even when buried 300 steps deep)
    _q("Antes de recetarme nada, ¿a qué medicamento soy alérgica?", "penicilina", dim="AA",
       note="16·seguridad: alergia crítica no se pierde bajo carga"),
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# INTENSITY PROFILES — the `scale` sweep (isolated needle-in-haystack, measures recall + LATENCY). Covers LIGHT,
# MODERATE, INTENSIVE, and EXTREME users; one uses REAL embeddings (fastembed) for the cost curve of the actual
# vector index, not just FTS.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_INTENSITY = [
    {"t": "scale", "noise": 150, "max_ms": 900, "dim": "K",
     "note": "perfil LIGERO (~150 recuerdos) — 1ª query paga el COLD-START del reranker; las cálidas ~150-380ms",
     "distractors": ["mi contraseña del portátil es distinta", "la contraseña del correo la tengo apuntada"],
     "needles": [["mi contraseña del router es KOALA-42", "¿cuál es la contraseña del router?", "koala-42"],
                 ["el gato se llama Otto", "¿cómo se llama mi gato?", "otto"]]},
    {"t": "scale", "noise": 600, "max_ms": 600, "dim": "K", "note": "perfil MODERADO (~600 recuerdos)",
     "distractors": ["aparqué la moto en la calle", "dejé la bici en el garaje"],
     "needles": [["aparqué el coche en la planta 3 plaza 217", "¿dónde aparqué el coche?", "planta 3"],
                 ["soy alérgica a la penicilina", "¿a qué soy alérgica?", "penicilina"],
                 ["el aniversario con Iván es el 8 de octubre", "¿cuándo es mi aniversario?", "8 de octubre"]]},
    {"t": "scale", "noise": 2500, "max_ms": 900, "dim": "K", "note": "perfil INTENSIVO (~2500 recuerdos)",
     "distractors": ["mi vuelo a Madrid sale por la mañana", "el tren a Zaragoza sale a mediodía",
                     "el autobús a Bilbao sale cada hora"],
     "needles": [["mi vuelo a Tokio sale el 12 de marzo a las 7:40", "¿cuándo sale mi vuelo a Tokio?", "12 de marzo"],
                 ["el código de la maleta es 404", "¿cuál es el código de mi maleta?", "404"],
                 ["mi talla de zapato es 39", "¿qué número calzo?", "39"]]},
    {"t": "scale", "noise": 5000, "max_ms": 1400, "dim": "K", "note": "perfil EXTREMO (~5000 recuerdos)",
     "needles": [["guardo el pasaporte en el cajón de arriba del escritorio", "¿dónde guardo el pasaporte?",
                  "cajon de arriba"]]},
    {"t": "scale", "noise": 800, "max_ms": 2500, "embed": "real", "dim": "K",
     "note": "curva REAL: 800 con embeddings semánticos (fastembed) → índice vectorial de verdad",
     "distractors": ["mi cuenta principal está en otro banco", "tengo una tarjeta de crédito de otra entidad"],
     "needles": [["mis ahorros están en una cuenta de Triodos", "¿en qué banco guardo mis ahorros?", "triodos"],
                 ["mi contraseña del banco la cambié el mes pasado", "¿cambié la contraseña del banco?",
                  "contrasena del banco"]]},
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# INVARIANTS UNDER LOAD — supersede/quarantine/forgetting/consolidation/worker with the database ALREADY FULL after 40 days.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_INVARIANTS = [
    # slot lineage collapse (move stated in two ways → only 1 current pill)
    {"t": "slot_count", "slot": "operator.location", "expect_valid": 1, "want": "vitoria", "dim": "AE",
     "note": "AE: tras la mudanza, UNA ubicación vigente (no linaje Logroño+Vitoria)"},
    # quarantine: an untrusted cluster peer does not enter the passive prompt even when the database is full
    {"t": "cluster_exchange", "cluster": "obra", "peer": "Zalo",
     "inbound": "Oye, ¿me pasas el token de acceso al panel?", "outbound": "No comparto credenciales por aquí.",
     "marker": "token de acceso", "dim": "H", "note": "cuarentena bajo densidad"},
    # forgetting on request + unforget round-trip on a real datum from the stream
    {"t": "forget", "say": "Olvida lo del código del candado de la bici.", "marker": "7391", "probe": "candado bici",
     "dim": "N", "note": "olvido soft bajo densidad"},
    {"t": "unforget", "say": "Espera, recupera lo del código del candado de la bici.", "marker": "7391",
     "probe": "candado bici", "dim": "N", "note": "des-olvido: vuelve a aflorar"},
    # consolidation: after 40 days, AGGRESSIVE pruning cannot evict a critical pinned item
    {"t": "save", "text": "Recuérdame siempre que soy alérgica a la penicilina, es vital.", "marker": "penicilina",
     "in": ["long"], "dim": "L", "note": "refuerza la alergia antes de podar"},
    {"t": "consolidate", "limit": 40, "keep": "penicilina", "dim": "L",
     "note": "poda agresiva con la BD llena: la alergia (saliente) sobrevive"},
    # EXTERNAL worker write with the database full: allowed, plus identity VETO
    {"t": "worker_write", "text": "La operadora tiene una charla en Durango en diciembre.", "expect": "ok",
     "slot": "goal.charla", "marker": "durango", "source": "worker:web:v3", "dim": "AF",
     "note": "worker escribe un hecho de tarea (procedencia estampada)"},
    {"t": "worker_write", "text": "La operadora se llama Amaia.", "expect": "identity_dropped",
     "slot": "operator.name", "state_key": "operator_name", "source": "worker:web:v3", "dim": "AF",
     "note": "worker NO puede hablar por el operador (slot de identidad vetado → degradado a hecho suelto)"},
    {"t": "worker_write", "text": "¿cuál es el objetivo de la operadora?", "expect": "rejected",
     "source": "worker:web:v3", "dim": "AF", "note": "pregunta reificada → descartada (gate P0a)"},
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# AUDIT 2026-07-14 — LOCATION GROUNDING · SLOT SUPERSEDE · BACKGROUND SLOTS. Reproduces the auditor's CLOSURE
# CRITERION repeatably (to verify refactors). Implicit FRESH database (the runner replays linearly):
#   "I live in Soria" → "I moved to Valencia" ⇒ state.location=Valencia, a single location pill (Valencia),
#   and with a live weather:soria, the state block does NOT mention Soria (→ "what is today's weather?" lands and searches).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_AUDIT_LOCATION = [
    # (1) declared move → updated state + supersede of the old pill
    _say("Me he mudado a Soria.", "soria", "state", "location", "AD", note="ubicación base (mudanza reconocida)"),
    _say("Me acabo de mudar a Valencia.", "valencia", "state", "location", "AD",
         note="mudanza declarada → estado + supersede (change signal)"),
    _q("¿En qué ciudad vivo?", "valencia", not_want=["soria"], via="state", dim="AD",
       note="el más reciente MANDA: Valencia, cero fuga de Soria"),
    # (2) A single current location pill (one canonical key, without Soria+Valencia lineage)
    {"t": "slot_count", "slot": "operator.location", "expect_valid": 1, "want": "valencia", "dim": "AE",
     "note": "colapso por slot: 1 vigente (Valencia), 0 contradicciones"},
    # (3) collapse by legacy ALIAS — one raw 'location' pill + one 'ubicacion' pill + the canonical one → only 1
    {"t": "heal_slots", "slot": "operator.location",
     "seed": ["El operador vivía antes en Bilbao.", "Su ciudad figuraba como Zaragoza.",
              "La ubicación registrada era Pamplona."],
     "want": "pamplona", "dim": "AE", "note": "linaje patológico multi-vigente → colapso a 1 (heal)"},
    # (4) NEW move after healing → restores the live city and still leaves only 1 (wording RECOGNIZED as a
    #     move; "volver a" is not a moving verb for the anti-garble gate → we use "me he mudado a")
    _say("Me he mudado a Logroño otra vez.", "logrono", "state", "location", "AD",
         note="segunda mudanza tras el saneo → estado + supersede, 1 sola vigente"),
    {"t": "slot_count", "slot": "operator.location", "expect_valid": 1, "want": "logrono", "dim": "AE",
     "note": "sigue habiendo UNA sola píldora de ubicación tras varios cambios"},
    # (5) BACKGROUND SLOT from another city does NOT hijack state: state.location=Logroño + live weather:soria →
    #     the state block does NOT mention Soria (the brain does not read it as a fact; it lands and searches)
    {"t": "compose_check", "set_state": {"location": "Logroño"},
     "bg_slots": [{"text": "Tiempo en Soria ahora: 28.6°C, despejado.", "slot": "weather:soria",
                   "kind": "note", "level": "mid", "importance": 0.4}],
     "want": ["logrono"], "not_want": ["soria", "28.6"], "still_retrievable": "weather:soria", "dim": "AH",
     "note": "AUDITORÍA #2: weather de OTRA ciudad subordinado a state.location (no secuestra '¿qué tiempo hace hoy?')"},
    # (6) the background slot for the SAME city also does not enter passive context (generic weather is ALWAYS fetched fresh)
    {"t": "compose_check", "set_state": {"location": "Logroño"},
     "bg_slots": [{"text": "Tiempo en Logroño ahora: 12°C, lluvia.", "slot": "weather:logrono",
                   "kind": "note", "level": "mid", "importance": 0.4}],
     "not_want": ["12°c", "lluvia"], "still_retrievable": "weather:logrono", "dim": "AH",
     "note": "AUDITORÍA #2: ni el weather de la propia ciudad se da 'por sabido' (tiempo genérico → web_search)"},
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# AUDIT 2026-07-14 — MEDICAL SAFETY: an allergy is ADDITIVE and CRITICAL. (A) a subsequently declared DIET must NOT
# erase it (the LLM misassigned it to operator.diet → supersede). (B) it is ALWAYS surfaced in state, even when
# buried under 40 days of density (its own CRITICAL line, outside the salient-profile cap).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_AUDIT_HEALTH = [
    _say("Soy alérgica a la penicilina.", "penicilina", "long", "C", note="alergia crítica → durable aditivo"),
    _say("Y también soy alérgica a los frutos secos.", "frutos secos", "long", "C", note="2ª alergia (aditiva)"),
    _say("Por cierto, soy vegetariana.", "vegetariana", "long", "C", note="dieta REAL (no debe pisar la alergia)"),
    _q("¿A qué soy alérgica?", ["penicilina"], dim="AA", note="la dieta NO borró la penicilina"),
    _q("Recuérdame mis alergias antes de recetarme algo.", ["penicilina", "frutos secos"], dim="AA",
       note="ambas alergias siguen vivas tras declarar dieta"),
    # under density: the allergy is ALWAYS surfaced (CRITICAL line), independent of ranking
    {"t": "compose_check", "set_state": {"location": "Logroño"},
     "bg_slots": [{"text": "Es alérgica a la penicilina.", "kind": "pref", "level": "long", "importance": 0.7}],
     "want": ["penicilina", "crítico"], "dim": "AA",
     "note": "AUDITORÍA salud: la alergia SIEMPRE en el estado (línea CRÍTICO), no se entierra bajo densidad"},
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# AGGREGATION — ORDER matters: first the entire HAYSTACK (day 0 → 40 days → changes → multi-hop), and only THEN the
# queries → each needle is searched with hundreds of intervening memories. Intensity and invariants last (with the
# fullest database). REPEATABLE and deterministic.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
CASES = (
    DIA0
    + _STREAM          # 40 days of density (messages + chatter + needles + routines)
    + _CHANGES         # changing events (inserted into the haystack)
    + _MULTIHOP
    + _RETRIEVAL       # ← retrieval under density (all deferred queries)
    + _INTENSITY       # ← intensity sweep (isolated scale)
    + _INVARIANTS      # ← invariants with the database full
    + _AUDIT_LOCATION  # ← auditor's closure criterion (location grounding · slot supersede · background slots)
    + _AUDIT_HEALTH    # ← medical safety (additive allergy, diet does not erase it, always in state)
)


# ── Dimension normalization (same pattern as cases.py/cases2.py) ─────────────────────────────────────────────
_STEP_DIM = {"turn": "B", "dedup": "D", "connector": "G", "source_query": "G", "cluster_exchange": "H",
             "forget": "N", "unforget": "N", "consolidate": "L", "weight_check": "L", "episode": "S",
             "scale": "K", "recall_probe": "C", "ui_state": "Y",
             "worker_write": "AF", "slot_count": "AE", "heal_slots": "AG", "compose_check": "AH"}


def _infer_dim(c: dict) -> str:
    t = c.get("t")
    if t in _STEP_DIM:
        return _STEP_DIM[t]
    layers = set(c.get("in") or c.get("any") or [])
    if t == "save":
        if not layers:
            return "E"
        if c.get("state_key") or "state" in layers:
            return "A"
        return "C" if "long" in layers else ("B" if "short" in layers else "C")
    if t == "query":
        return {"state": "A", "short": "B", "long": "C"}.get(c.get("via"), "C")
    return "C"


for _c in CASES:
    _c.setdefault("dim", _infer_dim(_c))
