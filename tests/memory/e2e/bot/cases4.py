"""Natural multi-fact dialogue corpus for the production memory gateway.

These are deliberately not commands such as "remember X". Each turn resembles
ordinary spoken conversation and is evaluated after the real CORAZÓN has split,
classified and stored zero or more canonical memory atoms.
"""

CASES = [
    {
        "t": "extract", "dim": "AD-dialogue", "text": "Hola, ¿qué tal? Bueno, nada, aquí estamos.",
        "discard": True,
        "note": "saludo y muletillas: cero píldoras, cero basura durable",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": (
            "Pues mira, estaba en el trabajo y tuvimos que apagar un incendio bastante feo. Soy bombero. "
            "Me gustaba mucho cuando vivía en Mallorca, pero ahora vivo en Madrid y espero quedarme aquí un "
            "par de años. Luego quizá me vaya a Barcelona o Menorca, o vuelva a Mallorca; todavía no lo sé."
        ),
        "require_llm": True, "min_atoms": 3,
        "state": {"location": "Madrid", "job": "bombero"},
        "contains": ["Mallorca", "incendio"],
        "note": "un solo turno contiene trabajo, evento, residencia histórica, residencia vigente e intenciones inciertas",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": (
            "Lo del incendio me dejó pensando. Cada vez me interesa más estudiar arquitectura, sobre todo cómo "
            "se diseñan edificios seguros; no es una tarea para hoy, es algo que quiero aprender en serio."
        ),
        "require_llm": True, "min_atoms": 1, "contains": ["arquitectura"],
        "allowed_levels": {"arquitectura": ["long"]},
        "note": "interés latente y objetivo durable extraídos de una reflexión, no de un formulario",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": (
            "Esta mañana me tomé un café al salir de guardia y ahora estoy bastante cansado, pero mañana seguro "
            "que ya estoy bien."
        ),
        "require_llm": True, "max_atoms": 2, "contains_any": ["café", "cansado"],
        "allowed_levels": {"café": ["short"], "cansado": ["short"]},
        "note": "actividad y estado del día: puede recordarse brevemente, nunca convertirse en identidad durable",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": (
            "Por cierto, cuando cenamos fuera hay que acordarse de que soy alérgico a la penicilina. "
            "No venía mucho a cuento, pero prefiero que no se pierda ese dato."
        ),
        "require_llm": True, "min_atoms": 1, "contains": ["penicilina"],
        "allowed_levels": {"penicilina": ["long"]}, "pinned": ["penicilina"],
        "note": "dato médico crítico enterrado dentro de charla lateral",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": "Oye, ¿qué tiempo va a hacer mañana en Bilbao? Si llueve ya veremos qué hacemos.",
        "discard": True,
        "note": "pregunta al asistente: no inventar una preferencia ni memorizar la meteorología solicitada",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": (
            "Antes te he dicho Madrid por inercia, pero no: me mudé a Valencia hace unas semanas. Madrid fue la "
            "ciudad anterior; ahora vivo en Valencia."
        ),
        "require_llm": True, "min_atoms": 1, "state": {"location": "Valencia"},
        "slots": {"operator.location": "Valencia"}, "slot_not": {"operator.location": "Madrid"},
        "note": "corrección natural: el slot vigente cambia y el dato previo queda histórico",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": (
            "Y otra precisión: cuando digo que soy bombero simplifico demasiado. Dejé ese puesto; ahora trabajo "
            "como coordinador de emergencias."
        ),
        "require_llm": True, "min_atoms": 1, "state": {"job": "coordinador"},
        "slots": {"operator.job": "coordinador"}, "slot_not": {"operator.job": "bombero"},
        "note": "cambio profesional expresado como rectificación conversacional",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": (
            "Mi hermana Laura me llamó mientras trabajaba: la operación de mi padre será el jueves y me pidió "
            "que la acompañe al hospital."
        ),
        "require_llm": True, "min_atoms": 1, "contains": ["jueves", "hospital"],
        "allowed_levels": {"jueves": ["mid", "long"], "hospital": ["mid", "long"]},
        "note": "tercero, parentesco, evento médico y compromiso futuro en una sola frase",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": (
            "No sé si te lo había contado: de pequeño pasaba los veranos en Segovia con mis abuelos. "
            "Recuerdo especialmente el olor de la panadería de la plaza."
        ),
        "require_llm": True, "min_atoms": 1, "contains": ["Segovia"],
        "allowed_levels": {"Segovia": ["long"]},
        "note": "recuerdo autobiográfico narrado con detalle sensorial",
    },
    {
        "t": "extract", "dim": "AD-dialogue",
        "text": "Vale, gracias, cierra eso y no me muestres nada más ahora.",
        "discard": True,
        "note": "orden efímera de UI: se ejecuta en el turno, no contamina la memoria",
    },
    {
        "t": "query", "dim": "AD-recall", "q": "¿Dónde vivo ahora?",
        "want": ["Valencia"], "not_want": ["vivo en Madrid"], "via": "state",
        "note": "el valor vigente responde y la ubicación superseded no se filtra como actual",
    },
    {
        "t": "query", "dim": "AD-recall", "q": "¿En qué trabajo actualmente?",
        "want": ["coordinador", "emergencias"], "not_want": ["soy bombero"], "via": "state",
        "note": "la ocupación corregida manda sobre la simplificación inicial",
    },
    {
        "t": "query", "dim": "AD-recall", "q": "¿Qué asunto familiar importante tengo el jueves?",
        "want": ["hospital", "jueves"], "via": "long",
        "note": "recuperación diferida de compromiso extraído de diálogo complejo",
    },
    {
        "t": "query", "dim": "AD-recall", "q": "¿Qué quiero aprender en serio?",
        "want": ["arquitectura"], "via": "long",
        "note": "recuperación de un interés inferido, no declarado como campo",
    },
]
