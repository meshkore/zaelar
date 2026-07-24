"""tests/e2e/memory/bot/cases3.py — TERCER corpus del test bot de memoria: EFICIENCIA BAJO CARGA REAL.

Petición del operador (2026-07-14): «no me valen pruebecitas con cuatro datos en la memoria; si los metemos todos
el LLM siempre acierta». La corrección de un dato ya la cubren v1 (GOLD) y v2 (genericidad + auditoría). Este corpus
prueba lo que ninguno de los dos: **¿el sistema encuentra el dato correcto, rápido, cuando la memoria está LLENA de
la vida real de una persona?** Simula **40 DÍAS de actividad densa** (cientos de mensajes, citas que se mueven y se
cancelan, estudios, compras, rutinas) y DESPUÉS busca AGUJAS enterradas en ese pajar — midiendo acierto Y latencia.

Tres ejes que v1/v2 no atacan:
  1. **DENSIDAD realista** — el pajar no es "nota de relleno 47": son mensajes reales de un roster (pareja, familia,
     editorial, grupo de escalada, ikastola, banco, veterinaria) con DISTRACTORES deliberados (5 restaurantes que
     recomendó la pareja, 3 citas de dentista, decenas de mensajes de escalada) → la recuperación tiene que
     DISCRIMINAR, no solo encontrar.
  2. **EFICIENCIA** — el runner resume la latencia de LECTURA (p50/p95/máx, el camino real del cerebro sin LLM). Los
     casos `scale` barren PERFILES DE INTENSIDAD (ligero 150 · moderado 600 · intensivo 2500 · extremo 5000) con
     umbral de latencia → "¿es rápido?" pasa a ser un número, y sabemos dónde se degrada.
  3. **INVARIANTES bajo carga** — supersede/cuarentena/olvido/consolidación/escritura de worker ejercidos con la BD
     LLENA, no vacía (que es cuando de verdad importan).

Persona: **Amaia Etxeberria** (la misma que v2 — continuidad; ahora con 40 días de vida encima). Corre aislado:
`python -m tests.e2e.memory.bot.runner --corpus v3 --fresh --range 0 N` (BD zaelar.membot3.db / progress-v3.json /
CATALOG3.md). REPETIBLE y determinista (sin azar ni reloj) → sirve para re-verificar refactors de arquitectura.

Formato de cada caso = idéntico a cases.py/cases2.py. La AGREGACIÓN (abajo) mete PRIMERO todo el pajar (día 0 →
stream de 40 días) y DESPUÉS las queries diferidas → cada aguja se pregunta con cientos de recuerdos intermedios.
"""
from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# HELPERS de construcción (compactos → densidad sin verbosidad; deterministas).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════

def _msg(platform, sender, text, marker, durable=True, trust="external", note="pajar"):
    """Mensaje ENTRANTE (WhatsApp/Telegram) → `connector`. `durable=True` → va a memoria durable (mid) por la
    triaje de mensajería: es el pajar BARATO (ingest_message escribe VERBATIM, sin LLM) y a la vez indexa por
    fuente. El marker es un substring distintivo del texto (verificación de indexado)."""
    return {"t": "connector", "platform": platform, "sender": sender, "text": text, "marker": marker,
            "trust": trust, "in": (["long"] if durable else ["short"]), "durable": durable,
            "dim": "G", "note": note}


def _say(text, marker, dest="long", state_key=None, dim=None, note="aguja (camino real del CORAZÓN)"):
    """Utterance del operador → `save` (pasa por el CORAZÓN LLM). Para AGUJAS de perfil ancla a un token DURO
    (nombre propio / número) que la destilación no parafrasea."""
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
    else:  # any de capas
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
# DÍA 0 — ALTA DE PERFIL. Lo básico que se preguntará ~300 pasos después (retención bajo densidad).
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
# EL PAJAR — 40 días de mensajes densos. Roster real, temas coherentes, DISTRACTORES deliberados dentro de cada
# tema. Todo durable (la triaje los vuelca a memoria) → el retriever tendrá que discriminar entre cientos.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════

# — IVÁN (pareja, WhatsApp, casi a diario): logística de casa + los 5 RESTAURANTES (solo 1 es el del aniversario) —
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

# — GRUPO DE ESCALADA "Mendi" (WhatsApp, Gorka y otros): fechas, material, rutas → distractores de material/lugar —
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

# — EDITORIAL Almadía (Telegram, Reyes): el libro de divulgación → fechas, portada, ventas, eventos —
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

# — FAMILIA: Xabier (Telegram, Berlín) + Begoña (WhatsApp, madre) —
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

# — IKASTOLA / colegio de Kattalin (WhatsApp: "ikastola", Maddi otra madre) —
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

# — NOTIFICACIONES / servicios (banco, farmacia, mensajería, veterinaria Ane) —
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

# — CHARLA MUNDANA (turnos de recencia, sin durable → puro churn del working set) —
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

# — AGUJAS de perfil enterradas en el stream (save → CORAZÓN; ancla a token DURO) —
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

# — RUTINAS repetidas (mismo hábito varias veces → refuerza el patrón) —
_RUTINAS = [
    _say("Los martes y jueves entreno escalada a las siete de la tarde.", "martes y jueves", "long", "O"),
    _say("Suelo salir a correr al parque del Ebro los domingos por la mañana.", "parque del ebro", "long", "O"),
    _say("Todos los lunes tengo taller de cerámica después de clase.", "taller de ceramica", "long", "O"),
]

_STREAM = _HAYSTACK + _CHATTER + _NEEDLES_SAVE + _RUTINAS

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# EVENTOS QUE CAMBIAN — citas que se mueven/cancelan y perfil que muta (supersede bajo densidad). Se insertan en el
# stream; se preguntan al final. El VALOR VIEJO no debe filtrarse (not_want).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_CHANGES = [
    # cita movida: jueves 5 → viernes 6
    _say("La reunión con la editorial es el jueves a las cinco.", "jueves", "long", "C", note="base a mover"),
    _say("Al final la reunión con la editorial se mueve al viernes a las seis.", "viernes", "long", "X",
         note="reprogramación (supersede implícito)"),
    # cita cancelada
    _say("Tengo cita en el taller para el coche el día doce.", "dia doce", "long", "C", note="base a cancelar"),
    _say("He cancelado la cita del taller del coche, ya no hace falta.", "cancelado la cita del taller", "long", "X",
         note="cancelación"),
    # mudanza de ciudad (estado superseded)
    _say("Me acabo de mudar a Vitoria por el trabajo de Iván.", "vitoria", "state", "location", "AD",
         note="mudanza declarada → estado actualizado + supersede (sin nombrar la ciudad origen)"),
    # pivote de oficio (invalidación implícita)
    _say("He dejado las clases en el instituto, ahora me dedico a la divulgación científica a tiempo completo.",
         "divulgacion cientifica", "long", "X", note="pivote de oficio"),
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# MULTI-HOP — dos eslabones separados en el tiempo que una sola pregunta debe COMPONER.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_MULTIHOP = [
    _say("El cumpleaños de mi hermano Xabier es el 3 de mayo.", "3 de mayo", "long", "U", note="eslabón 1"),
    # (eslabón 2 "Kreuzberg" ya está en el _HAYSTACK de familia)
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# RECUPERACIÓN BAJO DENSIDAD — los 16 casos de uso distintos. Cada query se resuelve por el CAMINO REAL del cerebro
# (brain_view = estado + salient + corto + recall) contra la BD YA LLENA.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_RETRIEVAL = [
    # 1 · HECHO EXACTO durable (aguja de perfil entre el ruido)
    _q("¿Cuál es el código del candado de mi bici?", "7391", dim="C", note="1·hecho exacto: código"),
    _q("¿Cómo se llama el pediatra de Kattalin?", "salaverri", dim="C", note="1·hecho exacto: nombre"),
    _q("¿Cuál es la contraseña del wifi de casa?", "mendizorrotza22", dim="C", note="1·hecho exacto: password"),
    _q("¿En qué banco tengo los ahorros?", "laboral kutxa", dim="C", note="1·hecho exacto: banco"),
    _q("¿Dónde aparqué el coche?", "plaza 118", dim="C", note="1·hecho exacto: ubicación puntual"),

    # 2 · MENSAJE por CONTENIDO (recuperar lo que dijo alguien, entre decenas de mensajes)
    _q("¿Qué me pidió Gorka que llevara a la escalada?", "mosquetones", dim="G", note="2·mensaje por contenido"),
    _q("¿Cuándo tengo que entregar el manuscrito?", "15 de noviembre", dim="G", note="2·mensaje por contenido"),
    _q("¿Qué necesita Otto según la veterinaria?", "vacuna", dim="G", note="2·mensaje por contenido"),
    _q("¿Cuándo es la reunión de padres de la ikastola?", "martes", dim="G", note="2·mensaje por contenido"),

    # 3 · MENSAJE por FUENTE (índice, no retriever): "¿qué me ha llegado de X?"
    {"t": "source_query", "source": "telegram", "entity": "Xabier", "want": ["kreuzberg"], "dim": "G",
     "note": "3·por fuente: lo de Xabier"},
    {"t": "source_query", "source": "telegram", "entity": "editorial Almadía", "want": ["2000 ejemplares"],
     "dim": "G", "note": "3·por fuente: lo de la editorial"},
    {"t": "source_query", "source": "whatsapp", "entity": "grupo Mendi", "want": ["etxauri"], "dim": "G",
     "note": "3·por fuente: el grupo de escalada"},

    # 4 · DISCRIMINACIÓN entre NEAR-DUPS (5 restaurantes de Iván → solo el del aniversario)
    _q("¿Dónde ha reservado Iván para nuestro aniversario?", "portalon",
       not_want=["bergara", "kabo", "ikaitz", "rekondo"], dim="C", note="4·discriminación: 5 restaurantes"),

    # 5 · CITA MOVIDA (as-of: el nuevo valor manda, el viejo NO filtra)
    _q("¿Qué día es finalmente la reunión con la editorial?", "viernes", not_want=["jueves"], dim="X",
       note="5·movida: viernes manda sobre jueves"),

    # 6 · CITA CANCELADA (refleja la cancelación)
    _q("¿Sigue en pie la cita del taller del coche?", "cancelado", dim="X", note="6·cancelada"),

    # 7 · PERFIL SUPERSEDED bajo densidad (mudanza)
    _q("¿En qué ciudad vivo ahora?", "vitoria", not_want=["logrono"], via="state", dim="AD",
       note="7·estado superseded: Vitoria, no Logroño"),

    # 8 · MULTI-HOP (componer hermano + dónde + cuándo)
    _q("¿Dónde vive y cuándo cumple años mi hermano?", ["kreuzberg", "3 de mayo"], dim="U", note="8·multi-hop"),

    # 9 · VOCAB-GAP por SIGNIFICADO (pregunta sin solape léxico con el hecho)
    {"t": "recall_probe", "save": ["Toco el txistu en el grupo de la ikastola."],
     "q": "¿Qué instrumento musical sé tocar?", "want": ["txistu"], "dim": "T", "note": "9·vocab-gap"},
    {"t": "recall_probe", "save": ["Estuve investigando la fermentación láctica para una charla."],
     "q": "¿Sobre qué tema preparé una ponencia?", "want": ["fermentacion"], "dim": "T", "note": "9·vocab-gap"},

    # 10 · ESTUDIO / INVESTIGACIÓN
    _q("¿Qué estuve investigando para una charla?", "fermentacion", dim="C", note="10·estudio"),

    # 11 · ANTI-ALUCINACIÓN (dato nunca dado no debe fabricar una respuesta). NB: que el retriever aflore el gato
    #      Otto NO es un fallo de memoria — es el CEREBRO quien no debe llamarlo "perro"; el read-path no lo asegura.
    _q("¿Cuál es mi color favorito?", [], dim="AA", note="11·anti-alucinación: dato nunca dado, sin fabricar"),
    _q("¿Cómo se llama mi empresa de coches de carreras?", [], dim="AA",
       note="11·anti-alucinación: entidad inexistente, sin inventar"),

    # 12 · PROMESA
    _q("¿Qué le prometí a Kattalin para su cumpleaños?", "acuario", dim="C", note="12·promesa"),

    # 13 · RUTINA bajo densidad
    _q("¿Qué días entreno escalada?", ["martes", "jueves"], dim="O", note="13·rutina"),
    _q("¿Dónde salgo a correr los domingos?", "ebro", dim="O", note="13·rutina"),

    # 14 · CIFRA entre ruido (muchos importes de banco de por medio)
    _q("¿Cuánto cuestan las obras de la cocina?", "8400", dim="C", note="14·cifra entre importes"),

    # 15 · PIVOTE de oficio (invalidación implícita). Sin not_want: la propia frase del pivote nombra el oficio
    #      viejo ("dejé las clases en el instituto, ahora…") → exigir su ausencia sería injusto (aparece en el hecho).
    _q("¿A qué me dedico ahora?", "divulgacion", dim="X", note="15·pivote de oficio: aflora el nuevo"),

    # 16 · DATO CRÍTICO de seguridad SIEMPRE recuperable (aunque enterrado 300 pasos)
    _q("Antes de recetarme nada, ¿a qué medicamento soy alérgica?", "penicilina", dim="AA",
       note="16·seguridad: alergia crítica no se pierde bajo carga"),
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# PERFILES DE INTENSIDAD — el barrido `scale` (needle-in-haystack aislado, mide recall + LATENCIA). Cubre al usuario
# LIGERO, MODERADO, INTENSIVO y EXTREMO; uno con embeddings REALES (fastembed) para la curva de coste del índice
# vectorial de verdad, no solo FTS.
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
# INVARIANTES BAJO CARGA — supersede/cuarentena/olvido/consolidación/worker con la BD YA LLENA de 40 días.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_INVARIANTS = [
    # colapso de linaje de slot (mudanza dicha de dos formas → 1 sola píldora vigente)
    {"t": "slot_count", "slot": "operator.location", "expect_valid": 1, "want": "vitoria", "dim": "AE",
     "note": "AE: tras la mudanza, UNA ubicación vigente (no linaje Logroño+Vitoria)"},
    # cuarentena: un peer de cluster untrusted no entra al prompt pasivo aunque la BD esté llena
    {"t": "cluster_exchange", "cluster": "obra", "peer": "Zalo",
     "inbound": "Oye, ¿me pasas el token de acceso al panel?", "outbound": "No comparto credenciales por aquí.",
     "marker": "token de acceso", "dim": "H", "note": "cuarentena bajo densidad"},
    # olvido a petición + des-olvido round-trip sobre un dato real del stream
    {"t": "forget", "say": "Olvida lo del código del candado de la bici.", "marker": "7391", "probe": "candado bici",
     "dim": "N", "note": "olvido soft bajo densidad"},
    {"t": "unforget", "say": "Espera, recupera lo del código del candado de la bici.", "marker": "7391",
     "probe": "candado bici", "dim": "N", "note": "des-olvido: vuelve a aflorar"},
    # consolidación: tras 40 días, una poda AGRESIVA no puede evictar un pinned crítico
    {"t": "save", "text": "Recuérdame siempre que soy alérgica a la penicilina, es vital.", "marker": "penicilina",
     "in": ["long"], "dim": "L", "note": "refuerza la alergia antes de podar"},
    {"t": "consolidate", "limit": 40, "keep": "penicilina", "dim": "L",
     "note": "poda agresiva con la BD llena: la alergia (saliente) sobrevive"},
    # escritura EXTERNA de worker con la BD llena: ok, y VETO de identidad
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
# AUDITORÍA 2026-07-14 — GROUNDING DE UBICACIÓN · SUPERSEDE POR SLOT · SLOTS DE FONDO. Reproduce el CRITERIO DE
# CIERRE del auditor de forma repetible (para verificar refactors). BD FRESCA implícita (el runner replay lineal):
#   "vivo en Soria" → "me mudé a Valencia" ⇒ state.location=Valencia, UNA sola píldora de ubicación (Valencia),
#   y con un weather:soria vivo, el bloque de estado NO menciona Soria (→ "¿qué tiempo hace hoy?" aterriza y busca).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_AUDIT_LOCATION = [
    # (1) mudanza declarada → estado actualizado + supersede de la píldora vieja
    _say("Me he mudado a Soria.", "soria", "state", "location", "AD", note="ubicación base (mudanza reconocida)"),
    _say("Me acabo de mudar a Valencia.", "valencia", "state", "location", "AD",
         note="mudanza declarada → estado + supersede (change signal)"),
    _q("¿En qué ciudad vivo?", "valencia", not_want=["soria"], via="state", dim="AD",
       note="el más reciente MANDA: Valencia, cero fuga de Soria"),
    # (2) UNA sola píldora vigente de ubicación (clave canónica única, sin linaje Soria+Valencia)
    {"t": "slot_count", "slot": "operator.location", "expect_valid": 1, "want": "valencia", "dim": "AE",
     "note": "colapso por slot: 1 vigente (Valencia), 0 contradicciones"},
    # (3) colapso por ALIAS legacy — una píldora cruda 'location' + una 'ubicacion' + la canónica → 1 sola
    {"t": "heal_slots", "slot": "operator.location",
     "seed": ["El operador vivía antes en Bilbao.", "Su ciudad figuraba como Zaragoza.",
              "La ubicación registrada era Pamplona."],
     "want": "pamplona", "dim": "AE", "note": "linaje patológico multi-vigente → colapso a 1 (heal)"},
    # (4) NUEVA mudanza tras el heal → restablece la ciudad viva y sigue habiendo 1 sola (fraseo RECONOCIDO como
    #     mudanza; "volver a" no es verbo de mudanza para el gate anti-garble → usamos "me he mudado a")
    _say("Me he mudado a Logroño otra vez.", "logrono", "state", "location", "AD",
         note="segunda mudanza tras el saneo → estado + supersede, 1 sola vigente"),
    {"t": "slot_count", "slot": "operator.location", "expect_valid": 1, "want": "logrono", "dim": "AE",
     "note": "sigue habiendo UNA sola píldora de ubicación tras varios cambios"},
    # (5) SLOT DE FONDO de otra ciudad NO secuestra el estado: state.location=Logroño + weather:soria vivo →
    #     el bloque de estado NO menciona Soria (el cerebro no lo lee como hecho, aterriza y busca)
    {"t": "compose_check", "set_state": {"location": "Logroño"},
     "bg_slots": [{"text": "Tiempo en Soria ahora: 28.6°C, despejado.", "slot": "weather:soria",
                   "kind": "note", "level": "mid", "importance": 0.4}],
     "want": ["logrono"], "not_want": ["soria", "28.6"], "still_retrievable": "weather:soria", "dim": "AH",
     "note": "AUDITORÍA #2: weather de OTRA ciudad subordinado a state.location (no secuestra '¿qué tiempo hace hoy?')"},
    # (6) el slot de fondo de LA MISMA ciudad tampoco entra al pasivo (el tiempo genérico SIEMPRE se busca fresco)
    {"t": "compose_check", "set_state": {"location": "Logroño"},
     "bg_slots": [{"text": "Tiempo en Logroño ahora: 12°C, lluvia.", "slot": "weather:logrono",
                   "kind": "note", "level": "mid", "importance": 0.4}],
     "not_want": ["12°c", "lluvia"], "still_retrievable": "weather:logrono", "dim": "AH",
     "note": "AUDITORÍA #2: ni el weather de la propia ciudad se da 'por sabido' (tiempo genérico → web_search)"},
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# AUDITORÍA 2026-07-14 — SEGURIDAD MÉDICA: una alergia es ADITIVA y CRÍTICA. (A) una DIETA declarada después NO
# puede borrarla (el LLM la mis-asignaba a operator.diet → supersede). (B) se surface SIEMPRE en el estado, aunque
# esté enterrada bajo 40 días de densidad (línea CRÍTICO propia, fuera del cap del perfil saliente).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
_AUDIT_HEALTH = [
    _say("Soy alérgica a la penicilina.", "penicilina", "long", "C", note="alergia crítica → durable aditivo"),
    _say("Y también soy alérgica a los frutos secos.", "frutos secos", "long", "C", note="2ª alergia (aditiva)"),
    _say("Por cierto, soy vegetariana.", "vegetariana", "long", "C", note="dieta REAL (no debe pisar la alergia)"),
    _q("¿A qué soy alérgica?", ["penicilina"], dim="AA", note="la dieta NO borró la penicilina"),
    _q("Recuérdame mis alergias antes de recetarme algo.", ["penicilina", "frutos secos"], dim="AA",
       note="ambas alergias siguen vivas tras declarar dieta"),
    # bajo densidad: la alergia se surface SIEMPRE (línea CRÍTICO), no depende del ranking
    {"t": "compose_check", "set_state": {"location": "Logroño"},
     "bg_slots": [{"text": "Es alérgica a la penicilina.", "kind": "pref", "level": "long", "importance": 0.7}],
     "want": ["penicilina", "crítico"], "dim": "AA",
     "note": "AUDITORÍA salud: la alergia SIEMPRE en el estado (línea CRÍTICO), no se entierra bajo densidad"},
]

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
# AGREGACIÓN — el ORDEN importa: primero el PAJAR entero (día 0 → 40 días → cambios → multi-hop), y solo DESPUÉS las
# queries → cada aguja se busca con cientos de recuerdos intermedios. Intensidad e invariantes al final (con la BD
# más llena). REPETIBLE y determinista.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
CASES = (
    DIA0
    + _STREAM          # 40 días de densidad (mensajes + charla + agujas + rutinas)
    + _CHANGES         # eventos que mutan (se insertan dentro del pajar)
    + _MULTIHOP
    + _RETRIEVAL       # ← recuperación bajo densidad (todas las queries diferidas)
    + _INTENSITY       # ← barrido de intensidad (scale aislado)
    + _INVARIANTS      # ← invariantes con la BD llena
    + _AUDIT_LOCATION  # ← criterio de cierre del auditor (grounding ubicación · supersede slot · slots de fondo)
    + _AUDIT_HEALTH    # ← seguridad médica (alergia aditiva, la dieta no la borra, siempre en el estado)
)


# ── Normalización de dimensión (idéntico patrón a cases.py/cases2.py) ───────────────────────────────────────
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
