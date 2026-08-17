"""nucleo/flash/recall_heuristics.py — on-demand recall/recency triggers (split out of prompt.py, 2026-08-17
modularization pass). `needs_recall()`/`needs_recent()` decide whether a turn's semantic recall or the expanded
recent-conversation block should fire; `compose_recent_block()` composes the latter. All three are pure text
classifiers plus one self-contained memory read — no dependency on prompt.py's ESTADO-composition machinery
(state/tools/widgets), which is why the audit that led to this split found them a clean, separable concern.

Re-exported from prompt.py, which several callers still import by name (`from nucleo.flash.prompt import
build_flash_system, needs_recall`, etc. — voice/engine/llm/providers/nucleo.py, probe_api.py, and
tests/voice/e2e/agent/model_bench.py all do this), so no external call site changed."""
from __future__ import annotations

import re as _re
import unicodedata as _ud

# ── heurística de RECALL BAJO DEMANDA (T116) ────────────────────────────────────────────────────────────
# El recall semántico (`compose_recall` → embeddings) solo se dispara cuando el turno pide RECORDAR algo que no
# está en el estado cacheado: verbos de recuerdo, referencias a sesiones pasadas o preguntas por una posesión/dato
# personal ("¿dónde está mi coche?"). La charla normal NO lo dispara → esos turnos ni tocan el retriever (rápidos).
# Multilenguaje por normalización (sin acentos, sin apóstrofes) + patrones es/en; un falso positivo solo cuesta un
# recall de más (fuera del loop), un falso negativo pierde un recuerdo → se prefiere pecar de inclusivo sin abrir
# la puerta a la charla trivial.
_RECALL_RE = _re.compile(
    r"\b("
    r"recuerdas|te acuerdas|acuerdas|que te dije|que dije|te conte|me dijiste|dijiste que|"
    r"hablamos de|comentamos|mencion|la otra vez|el otro dia|antes te|"
    r"remember|recall|reminded|what did i (say|tell)|you told me|we talked about|we discussed|"
    r"donde esta mi|donde estan mis|cuando es mi|cuando tengo|como se llama mi|que dije de|"
    r"where is my|where are my|wheres my|when is my|when do i|what is my|whats my|how is my|"
    # V2-013: preguntas por gustos / atributos / posesiones del operador (recall humano: "¿qué deporte me gusta?").
    r"me gusta|me gustan|te gusta|te gustan|que me gusta|cual es mi|cuales son mis|"
    r"odio|no soporto|detesto|no aguanto|no me gusta|que (no )?soporto|no me gustan|"
    r"que deporte|que deportes|que aficion|que hobby|que musica|que comida|que peli|que serie|"
    r"tengo un|tengo una|tienes un|tienes una|mi perro|mi gato|mi coche|mis aficiones|mis gustos|"
    r"do i like|what sports|what music|what food|my hobbies|my interests|my dog|my cat|my car|"
    # V2-013: recall TEMPORAL (preguntas por experiencias/acciones pasadas) — "¿adónde viajé el mes pasado?".
    r"el mes pasado|la semana pasada|hace unos meses|hace un mes|hace una semana|hace unos dias|"
    r"que hice|que hicimos|adonde (viaje|fui|fuimos)|donde (estuve|estuvimos)|que estuve|que estabamos|"
    r"last month|last week|months ago|weeks ago|what did we do|where did i go|"
    # V2-013: preguntas por el TRABAJO/PROYECTO/situación actual del operador — "¿en qué proyecto trabajo?".
    r"que proyecto|en que proyecto|mi proyecto|en que (estoy|ando)\s+trabajando|que estoy haciendo|"
    r"en que trabajo|de que trabajo|what project|working on|"
    # V2-013: recall de MENSAJES recibidos — "¿qué me dijo Carlos?".
    r"que me dijo|que me escribio|me escribio|que me conto|que decia|mensaje de|que dijo|"
    r"what did .* (say|tell me|write)|message from|"
    # V2-013: recall de salud/atributos ("¿a qué soy alérgico?") y de personas cercanas.
    r"alergic|a que soy|mi pareja|mi novi|mi mujer|mi marido|mi madre|mi padre|mi hermano|mi hermana|"
    r"mi amigo|mi mejor amigo|allergic|my partner|my wife|my husband|"
    # V2-013: recall de importes/transacciones/datos numéricos y de dirección — "¿por cuánto vendí la bici?".
    r"por cuanto|cuanto (vendi|pague|costo|cost[oó]|vale|gane)|vendi|compre|mi direccion|mi telefono|"
    r"mi numero|how much|my address|my phone|"
    # V2-013 T126: recall por CATEGORÍA (dispara el grafo de conceptos) — "¿cómo van mis finanzas?", "¿qué sabes
    # de mi familia?". Sin esto, una pregunta de categoría no dispara memory.query y el cluster del concepto no
    # aflora. Cubre los conceptos ligeros habituales + fórmulas genéricas de "cuéntame sobre X".
    r"mi salud|mis finanzas|mi familia|mi trabajo|mi dieta|mis estudios|mis viajes|mis aficiones|mi vivienda|"
    r"que sabes de|cosas de mi|sobre mi|como (va|van|estan|esta|llevo|tengo)\b|"
    # nombres de CATEGORÍA sueltos (disparan el grafo de conceptos aunque no digan "mi X"): "¿qué estudios hago?"
    r"salud|finanzas|trabajo|familia|deporte|viajes|estudios|estudi|ocio|comida|cocina|mascota|vivienda|"
    r"tecnolog|master|máster|apuntad|anotad|agenda|tengo apuntado|"
    # V2-013: recall de RECORDATORIOS / TAREAS / COMPROMISOS / AGENDA pendientes — "¿qué tengo que recordar?",
    # "¿qué te pedí?", "¿qué tengo pendiente?". Una instrucción/recordatorio reciente es durable → recall.
    r"que recordar|tengo que recordar|recordatorio|recordarme|te pedi|me pediste|me encargaste|te encargu[eé]|"
    r"que prepararas|que buscaras|que escribieras|pendiente|"
    r"que tengo que hacer|mis tareas|mi agenda|mis recordatorios|tengo cita|mis citas|"
    r"remind me|what do i have to|my tasks|my reminders|my agenda|my appointment|i ask(?:ed)? you|"
    # más stems de recall frecuentes (ahorro, trato, obra, colección, cita, viaje…)
    r"ahorr|trat|obra|colecc|colecion|\bcita\b|para que|con quien|de que"
    r")"                         # SIN \b final: permite que los STEMS (apuntad→apuntada, aprend→aprendiendo,
)                               # estudi→estudiando, trat→tratarme) casen palabras más largas. \b inicial basta.
# NOTA: ni una sola alternativa vacía ni un `|` colgando antes del `)` → casaría la cadena vacía (siempre True).


def _norm(text: str) -> str:
    n = _ud.normalize("NFKD", text or "")
    n = "".join(c for c in n if not _ud.combining(c)).lower()
    return n.replace("'", "").replace("’", "")


# Saludos / asentimientos / charla trivial — NUNCA disparan recall (no hay nada que recordar).
_TRIVIAL_RE = _re.compile(
    r"^\s*[¿¡]?\s*("
    r"hola|buenas|buenos dias|buenas tardes|buenas noches|hey|holi|ey|"
    r"que tal( estas| andas| va| te va| todo)?|que pasa|que hay|como estas|como andas|como va( todo)?|todo bien|"
    r"vale|ok|okay|oka|de acuerdo|entendido|perfecto|genial|estupendo|guay|dale|hecho|"
    r"gracias|muchas gracias|mil gracias|gracias tio|de nada|"
    r"si|no|claro|sip|nop|ajam|aja|ya|nada|bueno|"
    r"adios|chao|hasta luego|hasta pronto|hasta manana|nos vemos|buenas noches"
    r")\b[\s!.,¿?¡]*$"
)

# Verbos IMPERATIVOS que piden recordar ("cuéntame de mi familia", "recuérdame lo que dije"). EXIGE un objeto de
# recuerdo tras el verbo (de/sobre/qué/mi/lo que…) para NO disparar en "cuéntame un chiste" / "resúmeme esto".
# El recall explícito conocido ya lo cazó `_RECALL_RE` antes (p. ej. "dime dónde está mi coche").
_RECALL_IMPERATIVE_RE = _re.compile(
    r"\b(cu[eé]ntame|h[aá]blame|rec[uú]erda|recu[eé]rdame|refr[eé]sca|res[uú]me(me)?|rememora)\b"
    r"[^.?!]*?\b(de|del|sobre|acerca|qu[eé]|lo que|mi|mis|cuando|d[oó]nde|qui[eé]n|"
    r"que (te |me )?(dij|cont|pedi|escrib)|todo lo)\b", _re.I
)

# Expresiones de DESEO/INTENCIÓN: aunque no sean pregunta, deben aflorar los intereses/intenciones guardados
# ("me apetecería un viaje" → el cerebro debe recordar que le gusta el buceo y que quería un viaje de mar).
_DESIRE_RECALL_RE = _re.compile(
    r"\b(me apetec|me gustar[ií]a|tengo ganas|me encantar[ií]a|me molar[ií]a|me pide el cuerpo|"
    r"quiero hacer|quiero probar|quiero ir|quiero irme|podr[ií]amos|deber[ií]amos|y si (nos|me)|estar[ií]a bien|"
    # PLANIFICACIÓN/acción-con-contexto (auditoría 2026-07-19, falsos negativos MEDIDOS: «quiero irme de
    # vacaciones», «organízame un viaje», «búscame un hotel», «reserva un restaurante para mi aniversario» no
    # disparaban recall → el cerebro planeaba a ciegas). Es PREFETCH optimista: barato si sobra, amnesia si falta.
    r"vacaciones|un viaje|una escapada|un hotel|organ[ií]za(?:me)?|planea(?:r|me)?|planifica(?:me)?|"
    r"prep[aá]ra(?:me)? (?:un|una|el|la)|res[eé]rva(?:me)? (?:un|una|el|la)|"
    r"i feel like|i'?d like to|i want to|we could|maybe we|vacation|a trip|book me)", _re.I   # SIN \b final: stems
)

# COMANDOS de interfaz/dispositivo en forma de pregunta ("¿me pones el tiempo en pantalla?", "¿bajas el
# volumen?") — piden ACCIÓN, no recuerdo. Cortan el fallback genérico de pregunta. Si además fuera recall real
# ("muéstrame lo que te dije"), `_RECALL_RE` ya lo habría cazado ANTES (este guard va después).
_NON_RECALL_RE = _re.compile(
    r"\b(pon|ponme|pones|qu[ií]ta|quitame|abre|cierra|muestra|ense[ñn]a|saca|sube|baja|"
    r"activa|desactiva|enciende|apaga|reproduce|pausa)\b[^.?!]*\b(en pantalla|la pantalla|el widget|"
    r"widget|el tiempo|la hora|la agenda|la m[uú]sica|el volumen|volumen|la luz|las luces)\b", _re.I
)

# Arranque de PREGUNTA (WH) — con o sin signos de interrogación (el STT a veces se los come).
_WH_START_RE = _re.compile(
    r"^\s*[¿]?\s*(qu[eé]|cu[aá]l(es)?|cu[aá]ndo|d[oó]nde|qui[eé]n(es)?|c[oó]mo|cu[aá]nto|cu[aá]ntos|cu[aá]ntas|"
    r"por qu[eé]|para qu[eé]|a qu[eé]|de qu[eé]|con qui[eé]n|sab[eé]s|te acuerdas|recuerdas)\b", _re.I
)

# CIRCUITO DE CORTO PLAZO (C, 2026-07-14): el turno referencia la INTERACCIÓN RECIENTE (no un dato durable de
# memoria — eso es `needs_recall`), p. ej. "lo que te dije antes", "de qué hablábamos", "repite eso", "hace un
# rato", "vuelve a lo de antes". Dispara el 2º pase de CORTO que inyecta el buffer conversacional AMPLIADO
# (verbatim, más turnos que la ventana normal) fuera del event loop. es/en, determinista.
_RECENT_RE = _re.compile(
    r"\b(antes|hace\s+(un\s+)?(rato|momento|un\s+momento|nada|poco)|hace\s+un\s+par\s+de|anteriormente|"
    r"reci[eé]n|dec[ií]amos|dec[ií]as|dije|dijiste|dijimos|hablamos|habl[aá]bamos|coment[eé]|comentaste|"
    r"mencion[eé]|mencionaste|lo\s+de\s+antes|eso\s+[uú]ltimo|lo\s+[uú]ltimo|retoma|retomamos|vuelve\s+a\s+lo|"
    r"como\s+te\s+dije|como\s+dec[ií]a|rep[ií]te(lo|melo)?|otra\s+vez\s+(eso|lo)|"
    r"earlier|a\s+moment\s+ago|(just|right)\s+now|we\s+(were\s+)?(talking|said|discussed)|"
    r"(you|i)\s+said|as\s+i\s+said|repeat\s+that|go\s+back\s+to)\b", _re.I
)


def needs_recent(text: str) -> bool:
    """True si el turno referencia la INTERACCIÓN RECIENTE (corto plazo) más allá de lo que ya cabe en la ventana
    → dispara `compose_recent_block` (2º pase, fuera del loop). Distinto de `needs_recall` (dato DURABLE por
    significado, vía embeddings): esto es "de qué hablábamos / lo que te dije antes / repite eso". Sesga a NO
    disparar en charla trivial (coste de FP: una lectura directa µs que el modelo ignora)."""
    n = _norm(text or "")
    if not n.strip() or _TRIVIAL_RE.match(n):
        return False
    return bool(_RECENT_RE.search(n))


def compose_recent_block(limit: int = 20, max_chars: int = 2200) -> str:
    """2º PASE DE CORTO PLAZO: el buffer conversacional AMPLIADO (más turnos/chars que la ventana normal de 10),
    verbatim, para cuando el operador referencia algo reciente ("de qué hablábamos", "lo que te dije antes").
    Lectura DIRECTA (µs, sin LLM ni retriever) desde `memory.recent_window`. Devuelve un bloque etiquetado listo
    para el prompt, o '' si no hay conversación. El llamador lo corre FUERA del event loop (respeta V2-011)."""
    try:
        from memory import api as memory
        turns = memory.recent_window(limit=limit, max_chars=max_chars)
    except Exception:
        return ""
    if not turns:
        return ""
    lines = []
    for t in turns:
        who = "Operador" if t.get("role") == "user" else "zaelar"
        c = (t.get("content") or "").strip().replace("\n", " ")
        if c:
            lines.append(f"· {who}: {c}")
    if not lines:
        return ""
    return ("── CONTEXTO RECIENTE AMPLIADO (lo que habéis hablado hace un rato; el operador se refiere a esto) ──\n"
            + "\n".join(lines))


def needs_recall(text: str) -> bool:
    """True si el turno pide RECORDAR un dato de memoria (más allá del estado cacheado) → dispara `compose_recall`
    (fuera del loop, off-hot-path). Diseño ROBUSTO (V2-013, ya no una whitelist frágil): dispara ante cualquier
    PREGUNTA con sustancia o imperativo de recuerdo; NO dispara en saludo/asentimiento/charla trivial. El coste de
    un falso positivo es bajo (una query al retriever fuera del loop, que el LLM ignora si no viene a cuento); el
    de un falso NEGATIVO es alto (el cerebro parece amnésico). Por eso sesgamos a RECORDAR."""
    raw = text or ""
    n = _norm(raw)
    if not n.strip():
        return False
    if _RECALL_RE.search(n):                 # fast-path explícito (patrones de recall conocidos)
        return True
    if _TRIVIAL_RE.match(n):                  # saludo / ack / charla → nunca
        return False
    if _RECALL_IMPERATIVE_RE.search(n):       # "cuéntame de…", "recuérdame…"
        return True
    if _DESIRE_RECALL_RE.search(n):           # deseo/intención: "me apetecería un viaje" → conecta con intereses
        return True                            # e intenciones guardadas (buceo, viajes de mar…) para tenerlo en cuenta
    if _NON_RECALL_RE.search(n):              # comando de widget/dispositivo en forma de pregunta → acción, no recall
        return False
    is_question = ("?" in raw) or ("¿" in raw) or bool(_WH_START_RE.match(n))
    # pregunta con SUSTANCIA (≥2 palabras): dispara. La charla trivial en forma de pregunta ("¿qué tal?",
    # "¿cómo estás?") ya la cortó `_TRIVIAL_RE` arriba.
    return is_question and len(n.split()) >= 2
