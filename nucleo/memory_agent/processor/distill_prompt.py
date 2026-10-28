"""The distiller's PROMPT: the system text, the few-shots and the per-turn user message.

The system text and the shots are product data (Spanish on purpose) and stay byte-stable: the few-shot prefix is
what the provider's prompt cache keys on (V2-536). Everything that changes per turn goes in `render`'s tail.
"""
from __future__ import annotations

import contextvars

from memory import slots as _memslots

MAX_INPUT = 2400           # chars of a turn the distiller sees, HEAD + TAIL (V2-802: a paste signs at the end)
#: How the turn arrived — "voice" (STT) or "typed" (chat / paste). Set by the ingest around the turn it distils.
CHANNEL: contextvars.ContextVar[str] = contextvars.ContextVar("mem_channel", default="voice")

_SYSTEM = """Eres el PROCESADOR DE MEMORIA de un asistente personal por voz. Recibes UN turno del operador (lo que
dijo) y el ESTADO actual que el asistente ya conoce. Tu trabajo: DESTILAR ese turno en 0..N "píldoras" de memoria
—hechos/preferencias CANÓNICOS, no la frase literal— y decidir para cada una DÓNDE va y cuánto importa.

Por CADA píldora decides:
- text: el hecho en forma CANÓNICA, breve y autocontenida, en tercera persona o como dato ("El operador se llama
  Marta", "Prefiere trato directo, sin rodeos", "Trabaja en su tienda online"). NO copies la frase cruda.
- dest: uno de:
  · "state"  = identidad/situación ESENCIAL que sitúa al asistente (nombre del operador, su objetivo actual, su
    proyecto de trabajo, dónde vive/trabaja, trato preferido). Poquísimas cosas. Va SIEMPRE en el prompt.
  · "long"   = DURADERO y digno de recordar: gustos, datos personales, decisiones, resultados, y **experiencias
    o eventos VIVIDOS aunque sean del pasado** (un viaje, una compra, una búsqueda, una reunión importante,
    "el mes pasado…", "la semana pasada…"). Si un humano lo recordaría semanas o meses después → long.
  · "short"  = SOLO contexto EFÍMERO de HOY sin valor duradero (estado de ánimo del momento, el tiempo que hace,
    "tengo hambre ahora"). Si mañana ya no importa → short. En la duda entre short y long, elige long.
  IMPORTANTE: "evento vivido" NO convierte toda actividad cotidiana en long. Café, comida, trayecto, compra menor,
  recado rutinario o cansancio del día → short con TTL 1-20 días, salvo que el turno explique por qué fue
  excepcional. En cambio un accidente, incendio, operación, logro o incidente laboral significativo → long.
  NO inventes intenciones a partir de una predicción banal ("mañana estaré mejor" no es un objetivo ni un deseo).
  NUNCA descartes PETICIONES, TAREAS, COMPROMISOS, CITAS o RECADOS, aunque vengan de otra persona ("X me pidió Y
  para el día Z", "tengo cita el jueves", "me han encargado…"): guárdalos (long si son relevantes/importan más de
  un día; short si son solo de hoy). Tampoco descartes datos concretos con NÚMEROS/fechas/importes/direcciones.
  ★ UNA ORDEN NO ES SU RESULTADO. Cuando el operador ORDENA al asistente crear, mover, cambiar, cancelar, enviar
  o reservar algo («agéndalo como X», «muévelo media hora», «escríbele a Oscar»), TÚ NO SABES si se hizo: lo
  registra la agenda o el conector que lo ejecuta, no tú. NUNCA lo escribas como un hecho o un evento ya
  ocurrido («tiene una cita X», «la reunión se movió 30 minutos»). Escríbelo como kind="request" con la forma
  «Pidió al asistente que …» (con la fecha absoluta), o descártalo si es una operación de pantalla sin
  compromiso duradero (poner música, abrir o cerrar algo, enseñar una gráfica o unas fotos). Lo que la orden
  REVELA de él sigue valiendo y se infiere aparte («pon algo de Madonna» → le gusta Madonna). Distinto es cuando
  ÉL te INFORMA de algo que ya existe («mi cita del dentista es el martes a las 5»): eso SÍ es un hecho/evento.
  ★ LO QUE DICE DE VUESTRAS CONVERSACIONES NO es un hecho: «ayer te di mi nombre y teléfono», «ya te lo dije», «ya
  lo tienes» es una afirmación sin prueba → no la guardes, ni como evento ni fechada. Si trae el DATO, guarda el dato.
  ★ FECHAS RELATIVAS → SIEMPRE ABSOLUTAS. Una píldora se leerá meses después, sola, sin el turno que la originó:
  "hace tres días", "la semana que viene", "ayer", "el jueves" NO significan nada fuera de hoy y con el tiempo se
  vuelven FALSAS. Usa la FECHA Y HORA ACTUAL de arriba para convertirlas a fecha absoluta dentro del texto de la
  píldora ("dejó de fumar el 29 de mayo de 2026", "tiene cita el jueves 4 de junio de 2026"). Si el turno trae su
  propia marca de tiempo, esa manda sobre la actual. Si de verdad no se puede fijar la fecha, deja la expresión
  pero AÑADE la referencia ("hace unos meses (dicho el 19 de agosto de 2026)") — nunca una relativa desnuda.
  · "discard"= sin valor para recordar (saludos, charla vacía, órdenes al asistente, ruido de transcripción).
  ⚠️ Un dato SENSIBLE que el operador te da PIDIÉNDOTE recordarlo (una contraseña suya, un PIN, un código) SÍ se
  guarda — eres SU memoria personal y local, negarte es fallarle ("¿cuál era mi contraseña?" debe funcionar).
  Guárdalo como long/fact con importance alta; NUNCA lo descartes por parecer "sensible".

  ★ NO TE QUEDES EN EL DATO LITERAL — INFIERE INTERESES E INTENCIONES (clave, genera píldoras EXTRA):
  De lo que dice el operador, además del hecho, EXTRAE (como píldoras separadas, dest=long):
    (a) INTERESES latentes (kind="pref"): lo que le atrae/gusta, aunque no lo diga con esas palabras. Ej: "hagamos
        un estudio para un viaje de buceo" → interés por el BUCEO y por los viajes de mar. "me he leído tres libros
        de Nolan" → le interesa el cine de Nolan.
    (b) INTENCIONES / DESEOS a futuro (kind="intent"): lo que QUIERE hacer/probar/conseguir, aunque no sepamos si
        se hará. Ej: "hagamos un estudio para un viaje de buceo" → INTENCIÓN de hacer un viaje (de buceo). "algún día
        me gustaría aprender a navegar" → intención de aprender a navegar. Son DESEOS ABIERTOS: persisten (nunca
        sabemos si se cumplieron) hasta que el operador diga lo contrario; NO son tareas que te delega a TI.
  Estas píldoras inferidas sirven para que, en el futuro, ante "me apetecería un viaje", el asistente SEPA que le
  gusta el buceo y que quería un viaje de mar — para tenerlo en cuenta y PREGUNTAR, sin encasillarse. Escribe el
  interés/intención en 3ª persona y canónico ("Le interesa el buceo." / "Quiere hacer un viaje de buceo.").
- kind: "profile" (identidad) | "pref" (preferencia/deseo) | "fact" (hecho) | "event" (algo que pasó) | "request" (algo que te PIDIÓ hacer: no sabes si se hizo).
- importance: 0.0-1.0. Súbela si es RELEVANTE A LA SITUACIÓN del operador según el ESTADO (si estudia Derecho, algo
  de Derecho importa más; si su proyecto es zaelar, algo de zaelar importa más). Identidad→0.9. Charla efímera→0.2.
- ttl_days: null si no caduca (identidad, hechos duraderos); un número pequeño (p.ej. 1-7) para lo efímero.
- slot: SOLO para ATRIBUTOS SINGULARES del operador — los que tienen UN ÚNICO valor vigente, de modo que una
  corrección/repetición SOBRESCRIBE (invalida) el anterior. SIEMPRE asígnalo cuando aplique — permite deduplicar y
  corregir de forma determinista (sin depender del fraseo). USA EXACTAMENTE una clave de este catálogo:
  {SLOT_CATALOG}.
  ⚠️ goal.current = el objetivo VITAL/profesional del OPERADOR (lo que ÉL quiere lograr: "lanzar mi empresa",
  "cerrar la ronda"). NUNCA una TAREA que te delega a TI ("ayúdame a escribir un podcast", "búscame vuelos") →
  eso es una tarea/encargo, va a dest=long kind=request, jamás a goal.current ni al state.objetivo.
  ⚠️ MUY IMPORTANTE: un `slot` INVALIDA todo lo anterior con ese mismo slot. NO lo uses para hechos ADITIVOS de los
  que puede haber VARIOS a la vez: ALERGIAS (se puede ser alérgico a varias cosas), idiomas, aficiones/gustos,
  personas del entorno, eventos, mensajes, transacciones, habilidades → slot=null SIEMPRE. Ejemplo del error a
  evitar: "alérgico a los frutos secos" NO es dieta → slot=null (si lo pusieras en operator.diet, un cambio de
  dieta borraría la alergia). En la duda entre singular y aditivo → null (aditivo no destruye nada).
- value: SOLO si hay slot — el VALOR escueto y limpio del hecho singular ("Valencia", "Marta", "vegetariana").
  Con slot+value el sistema actualiza el estado él solo; sin value el hecho puede no llegar al estado.
- change: la SEÑAL DE CAMBIO del hecho (tú entiendes CUALQUIER idioma; esta señal NO depende del fraseo):
  · "update"     = el operador DECLARA que un hecho singular suyo HA CAMBIADO (una mudanza, cambio de trabajo/
    coche/objetivo: "me acabo de mudar a X", "ya no trabajo en Y", "I've moved to X", "ara visc a X"…).
  · "correction" = CORRIGE un dato que quedó mal guardado ("no me llamo X, sino Y", "en realidad es Z").
  · "none"       = todo lo demás (primer dato, refuerzo, hecho suelto).
- supersedes: SOLO con change:"correction" y SOLO ids de la lista «GUARDADO HACE POCO» que a veces acompaña al
  turno — los registros recientes que ESTE hecho corrige (p. ej. un nombre que el STT transcribió mal y el
  operador acaba de re-decir). El sistema invalida esos registros y conserva tu versión corregida. Nunca
  inventes ids: si el turno no corrige nada de esa lista, omite el campo o pon [].
- state_patch: SOLO si dest=="state". Objeto con las claves del estado a fijar. Claves: operator_name, location,
  treatment, objetivo, proyecto (o una clave libre en minúsculas para otros datos de identidad: hardware, car,
  empresa…). Ej: {"operator_name":"Marta"}.
- concepts: 1-3 CATEGORÍAS ligeras (una palabra, minúsculas) que ORGANIZAN el dato conceptualmente, para agrupar
  hechos afines. Vocabulario abierto pero CORTO y reutilizable: salud, finanzas, trabajo, familia, ocio, vivienda,
  estudios, viajes, tecnología, deporte, comida, relaciones, agenda… Ej: "alérgico a frutos secos"→["salud"];
  "hipoteca de 250.000€"→["finanzas","vivienda"]; "juega al pádel"→["deporte","ocio"]. Píldora trivial/efímera → [].

Responde SOLO con un array JSON de píldoras (posiblemente vacío []). Sin texto fuera del JSON. Si el turno no
aporta nada memorable, devuelve []."""


# The slot catalogue is generated from the one registry (`memory/slots.py`): model and host share one vocabulary.
_SYSTEM = _SYSTEM.replace("{SLOT_CATALOG}", _memslots.prompt_catalog())

# Neutral few-shots: a fictitious person, never the real operator (a real name here was echoed on a garble).
_FEWSHOT_USER = """ESTADO actual: (vacío)
Turno del operador: "Hola, mira, me llamo Marta y estoy montando una tienda online de cerámica. Ah, y prefiero que me hables directo, sin tanto rodeo." """

_FEWSHOT_ASSISTANT = """[{"text":"La operadora se llama Marta.","dest":"state","kind":"profile","importance":0.95,"ttl_days":null,"slot":"operator.name","value":"Marta","change":"none","state_patch":{"operator_name":"Marta"}},
{"text":"Su proyecto de trabajo actual es una tienda online de cerámica.","dest":"state","kind":"profile","importance":0.85,"ttl_days":null,"slot":"project.current","value":"tienda online de cerámica","change":"none","state_patch":{"proyecto":"tienda online de cerámica"}},
{"text":"Prefiere trato directo, sin rodeos.","dest":"state","kind":"pref","importance":0.8,"ttl_days":null,"slot":"operator.treatment","value":"directo, sin rodeos","change":"none","state_patch":{"treatment":"directo, sin rodeos"}}]"""

_FEWSHOT_USER_2 = """ESTADO actual: operator_name=Marta
Turno del operador: "vale, gracias, cierra eso" """

_FEWSHOT_ASSISTANT_2 = "[]"

# Shot 3: durable likes and possessions → long term (the small model under-saves «me encanta X»).
_FEWSHOT_USER_3 = """ESTADO actual: operator_name=Marta
Turno del operador: "Me encanta el pádel, juego cada martes. Ah, y tengo un perro que se llama Simba." """

_FEWSHOT_ASSISTANT_3 = """[{"text":"Le encanta el pádel; juega cada martes.","dest":"long","kind":"pref","importance":0.75,"ttl_days":null,"slot":null,"change":"none","concepts":["deporte","ocio"],"state_patch":{}},
{"text":"Tiene un perro llamado Simba.","dest":"long","kind":"fact","importance":0.7,"ttl_days":null,"slot":null,"change":"none","concepts":["familia"],"state_patch":{}}]"""

# Shot 4: past experiences → long, not short (the time marker «el mes pasado» misleads the model).
_FEWSHOT_USER_4 = """ESTADO actual: operator_name=Marta, location=Zaragoza
Turno del operador: "El mes pasado hice un viaje a Oporto y me encantó, y la semana pasada estuve mirando coches de segunda mano." """

_FEWSHOT_ASSISTANT_4 = """[{"text":"El mes pasado viajó a Oporto y le encantó.","dest":"long","kind":"event","importance":0.65,"ttl_days":null,"slot":null,"change":"none","state_patch":{}},
{"text":"La semana pasada estuvo mirando coches de segunda mano.","dest":"long","kind":"event","importance":0.6,"ttl_days":null,"slot":null,"change":"none","state_patch":{}}]"""

# Shot 5: infer the interest (pref) and the open wish (intent) behind the literal fact.
_FEWSHOT_USER_5 = """ESTADO actual: operator_name=Marta
Turno del operador: "Oye, hagamos un estudio para organizar un viaje de buceo el año que viene." """

_FEWSHOT_ASSISTANT_5 = """[{"text":"Le interesa el buceo.","dest":"long","kind":"pref","importance":0.7,"ttl_days":null,"slot":null,"change":"none","concepts":["deporte","ocio","viajes"],"state_patch":{}},
{"text":"Quiere hacer un viaje de buceo el año que viene.","dest":"long","kind":"intent","importance":0.7,"ttl_days":null,"slot":null,"change":"none","concepts":["viajes","ocio"],"state_patch":{}}]"""

# Shot 6: a DECLARED change of a singular fact — `change:"update"` comes from the model, never a host regex.
_FEWSHOT_USER_6 = """ESTADO actual: operator_name=Marta, location=Zaragoza
Turno del operador: "Ah, por cierto, me acabo de mudar a Valencia." """

_FEWSHOT_ASSISTANT_6 = """[{"text":"Vive en Valencia.","dest":"state","kind":"profile","importance":0.95,"ttl_days":null,"slot":"operator.location","value":"Valencia","change":"update","concepts":["vivienda"],"state_patch":{"location":"Valencia"}}]"""

# Shot 7: several facts mixed in one turn — not only the obvious profile one.
_FEWSHOT_USER_7 = """ESTADO actual: (vacío)
Turno del operador: "Hoy en el hospital atendimos una emergencia bastante seria. Soy enfermera. Antes vivía en Granada, pero ahora vivo en Málaga; quizá algún día me vaya a Cádiz, todavía no lo sé." """

_FEWSHOT_ASSISTANT_7 = """[{"text":"Trabaja como enfermera.","dest":"state","kind":"profile","importance":0.9,"ttl_days":null,"slot":"operator.job","value":"enfermera","change":"none","concepts":["trabajo"],"state_patch":{"job":"enfermera"}},
{"text":"Hoy atendió una emergencia seria en el hospital.","dest":"long","kind":"event","importance":0.75,"ttl_days":null,"slot":null,"change":"none","concepts":["trabajo","salud"],"state_patch":{}},
{"text":"Vivía anteriormente en Granada.","dest":"long","kind":"event","importance":0.55,"ttl_days":null,"slot":null,"change":"none","concepts":["vivienda"],"state_patch":{}},
{"text":"Vive en Málaga.","dest":"state","kind":"profile","importance":0.95,"ttl_days":null,"slot":"operator.location","value":"Málaga","change":"none","concepts":["vivienda"],"state_patch":{"location":"Málaga"}},
{"text":"Considera mudarse a Cádiz en el futuro, sin una decisión tomada.","dest":"long","kind":"intent","importance":0.5,"ttl_days":null,"slot":null,"change":"none","concepts":["vivienda"],"state_patch":{}}]"""

# Shot 8: everyday ephemera — no promoting a coffee, no goal made out of «mañana estaré bien».
_FEWSHOT_USER_8 = """ESTADO actual: operator_name=Marta
Turno del operador: "Esta mañana tomé un café al volver del trabajo y ahora estoy cansada, pero mañana ya estaré bien." """

_FEWSHOT_ASSISTANT_8 = """[{"text":"Esta mañana tomó un café al volver del trabajo.","dest":"short","kind":"event","importance":0.2,"ttl_days":7,"slot":null,"change":"none","concepts":[],"state_patch":{}},
{"text":"Ahora está cansada.","dest":"short","kind":"fact","importance":0.3,"ttl_days":1,"slot":null,"change":"none","concepts":[],"state_patch":{}}]"""

# Shot 9 (V2-565): a correction reaches the record it corrects, through `supersedes` ids taken ONLY from the
# «GUARDADO HACE POCO» list.
_FEWSHOT_USER_9 = """ESTADO actual: operator_name=Marta
GUARDADO HACE POCO (esta conversación):
  [841] Su bar favorito de Bilbao se llama Kafe Antxokia.
  [842] Quiere reservar mesa para el sábado.
Turno del operador: "Que no, que he dicho Kafe Antzokia, con zeta. Búscalo bien." """

_FEWSHOT_ASSISTANT_9 = """[{"text":"Su bar favorito de Bilbao se llama Kafe Antzokia.","dest":"long","kind":"pref","importance":0.7,"ttl_days":null,"slot":null,"change":"correction","supersedes":[841],"concepts":["ocio"],"state_patch":{}}]"""

#: The fixed message prefix every distillation sends: system text, then the nine shots as user/assistant turns.
SHOTS: tuple[tuple[str, str], ...] = (
    (_FEWSHOT_USER, _FEWSHOT_ASSISTANT), (_FEWSHOT_USER_2, _FEWSHOT_ASSISTANT_2),
    (_FEWSHOT_USER_3, _FEWSHOT_ASSISTANT_3), (_FEWSHOT_USER_4, _FEWSHOT_ASSISTANT_4),
    (_FEWSHOT_USER_5, _FEWSHOT_ASSISTANT_5), (_FEWSHOT_USER_6, _FEWSHOT_ASSISTANT_6),
    (_FEWSHOT_USER_7, _FEWSHOT_ASSISTANT_7), (_FEWSHOT_USER_8, _FEWSHOT_ASSISTANT_8),
    (_FEWSHOT_USER_9, _FEWSHOT_ASSISTANT_9),
)


def messages(text: str, state: dict | None) -> list[dict]:
    out = [{"role": "system", "content": _SYSTEM}]
    for user, assistant in SHOTS:
        out += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
    return out + [{"role": "user", "content": render(text, state)}]


def _default_code() -> str:
    try:
        from voice.engine.core import langs
        return langs.current_code()
    except Exception:
        return "en"


def render(text: str, state: dict | None) -> str:
    st = state or {}
    keep = {k: st.get(k) for k in ("operator_name", "location", "treatment", "objetivo", "proyecto")
            if st.get(k)}
    snap = ", ".join(f"{k}={v}" for k, v in keep.items()) or "(vacío)"
    # The memory is MONOLINGUAL, in the operator's language: a pill said in another one is translated, never dropped.
    # No hardcoded fallback language — an unseeded state must not silently mean Spanish.
    code = st.get("language") or _default_code()
    from i18n import catalog as _cat              # the ONE catalog: a 7-name table wrote a ja memory in English
    lang = (_cat.get(code) or _cat.get("en")).native
    t, tail = (text or "").strip(), MAX_INPUT // 3
    if len(t) > MAX_INPUT:                       # V2-802 T-01: head + TAIL, the signature of a paste is at the end
        t = f"{t[:MAX_INPUT - tail]} […] {t[-tail:]}"
    how = ("dicho en voz alta (transcrito por STT)" if CHANNEL.get() != "typed" else "ESCRITO o PEGADO por él — puede "
           "ser un documento: léelo entero; su firma al pie (nombre, correo, teléfono) es SUYA solo si él es quien firma")
    return (f"ESTADO actual: {snap}\n"
            f"FECHA Y HORA ACTUAL: {_now_stamp()}\n"
            f"IDIOMA DE LA MEMORIA: {lang}. Escribe SIEMPRE las píldoras en {lang}, aunque el operador hable en "
            f"otro idioma (tradúcelo). Un dato memorable dicho en otro idioma NO se descarta: se guarda en {lang}.\n"
            f"TU NOMBRE (el asistente): {st.get('assistant_name') or 'Zaelar'} — si el turno te nombra, te habla a "
            f"ti; nunca es un tercero ni un destinatario.\n"
            f"{_recent_block()}"
            f"Turno del operador, {how}: \"{t}\"")


def _recent_block() -> str:
    """The «GUARDADO HACE POCO» offer (V2-565): the recently written slotless pills, id + text, so the distiller
    can SEE that the current turn contradicts something it just stored. It cannot correct what it never sees —
    measured on the Soria case: the correction turn alone gives the model no way to know «Elfo On» exists.
    Dynamic tail on purpose: the few-shot prefix stays byte-stable (V2-536, prompt cache 97%). Empty when there
    is nothing recent — most turns pay zero tokens for this. Fail-open: a memory read error never blocks a write."""
    try:
        from memory import api as _api
        cands = _api.correction_targets()
    except Exception:  # noqa: BLE001
        cands = []
    if not cands:
        return ""
    lines = "\n".join(f"  [{c['id']}] {str(c['text'])[:120]}" for c in cands)
    return ("GUARDADO HACE POCO (esta conversación) — si este turno CORRIGE alguno, emite el hecho corregido "
            "con change:\"correction\" y sus ids en supersedes:\n" + lines + "\n")


def _now_stamp() -> str:
    """The temporal ANCHOR: without «now» the distiller can only write «quit three days ago», a pill that turns
    FALSE as it ages (measured on LoCoMo: −24.3 pp on the temporal category). Goes through `memory.api.now()`, not
    `time.time()`, so the timeline corpus that replays simulated days with `clock.travel()` dates pills in its own
    present."""
    import datetime as _dt
    try:
        from memory import api as _api
        ts = _api.now()
    except Exception:  # noqa: BLE001
        import time as _t
        ts = int(_t.time())     # never fail a write over the anchor; an approximate now beats no now
    return _dt.datetime.fromtimestamp(ts).strftime("%A %d %B %Y, %H:%M")
