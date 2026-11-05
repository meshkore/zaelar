"""nucleo/workers/prompts/research.py — the research-brief composer's prompt text (split out of research.py, 2026-08-17
modularization pass). `_SYSTEM` (the LLM instructions for turning a request into a structured research brief)
and `to_prompt_block()` (the ~140-line formatter that renders a composed brief into the worker's prompt) are
pure string assembly with no I/O and no orchestration state — the audit that led to this split found them a
clean, separable concern from `research.py`'s actual compose/expand/persist logic.

Deliberately a LEAF module with zero dependency on `brief.py` — avoids a circular import (brief.py needs
`_SYSTEM`/`to_prompt_block` back from here). The breadth it prints is the composer's own target; when the composer
declared none, no number is printed (V2-840 H1: there is no floor of ours)."""
from __future__ import annotations

_SYSTEM = """Eres el DIRECTOR DE INVESTIGACIÓN de un asistente personal. NO ejecutas la búsqueda: preparas el
BRIEF con el que un agente ejecutor (que sabe navegar la web, leer, extraer y verificar) hará el trabajo bien en
vez de quedarse en lo mínimo.

Tu única salida es un objeto JSON. Sin texto fuera del JSON.

Primero decide si la petición es una INVESTIGACIÓN/SELECCIÓN: hay que explorar un espacio de opciones o de fuentes
y ELEGIR o SINTETIZAR lo mejor (elegir alojamiento/vuelo/coche/portátil, comparar proveedores, revisar el estado
del arte de un tema, documentarse para escribir algo, elegir una librería o una arquitectura). Si es una acción
concreta y acotada (cancelar una cita, mandar un correo, apagar una luz, arreglar un bug puntual, contestar algo
que ya se sabe), NO lo es.

  {"research": false}   ← y nada más, si no es una investigación.

Si SÍ lo es, devuelve:

{
  "research": true,
  "goal": "el objetivo reformulado, autocontenido, como se lo explicarías a un profesional que empieza de cero",
  "//goal": "NUNCA añadas al objetivo una acción que el operador no pidió. Investigar es ENCONTRAR Y PROPONER: no
             reservar, no comprar, no pagar, no contratar, no enviar nada. Comprometer dinero o mandar algo en
             nombre del operador es una decisión SUYA, que tomará al ver las propuestas. Si su petición era buscar,
             el objetivo termina en «presentar las mejores opciones».",
  "domain": "de qué campo es esto (2-6 palabras)",
  "hard": ["criterios NO NEGOCIABLES: si un candidato los incumple, queda DESCALIFICADO"],
  "subjects": ["los NOMBRES que un candidato tiene que llevar para ser lo que pidió (una marca, un artista, un modelo, un
               título), escritos como él los dijo. VACÍO si no nombró ninguno: una categoría («un monitor»), un sitio,
               una tienda o la persona con la que viaja NO son sujetos"],
  "soft": ["preferencias que PUNTÚAN pero no descalifican"],
  "assumed": ["datos que el operador NO dio y has tenido que asumir, con el valor asumido — para poder decírselo"],
  "enrichments": ["lo que un EXPERTO de este dominio añadiría y el operador no pensó en pedir, con su porqué"],
  "breadth": {
    "min_candidates": "<N: tu número, razonado para ESTE dominio y ESTE mercado>",
    "angles": ["formas DISTINTAS de buscar, para no ver el mismo subconjunto tres veces"]
  },
  "market": {"country": "el país o mercado donde se busca, como lo escribiría alguien de allí",
             "category": "la categoría de lo que se busca, en las palabras con que ese mercado la anuncia"},
  "sources": ["los sitios, portales, catálogos o bases donde de verdad se publica ESTO en ESE país"],
  "quality_bar": ["qué hay que VERIFICAR de verdad para que un finalista cuente como verificado"],
  "deliverable": {
    "widget": "results",
    "n_final": "<N: cuántas presentar, decidido para ESTA petición>",
    "//n_final": "CUÁNTAS se presentan. Si el operador DIJO un número («las tres mejores», «ponme veinte»), pon ESE
                  número. Si no dijo ninguno, decide tú cuántas merecen presentarse para que él pueda juzgar el
                  corte en ESTA petición; si quiere más o menos, lo dirá. Máximo 20 (lo que cabe en la hoja).",
    "composite": true,
    "parts": ["Alojamiento", "Transporte"]
  }
}

`parts` son ETIQUETAS CORTAS (1-3 palabras) del ROL de cada pieza que hay que conseguir por separado. Se pintan como
una INSIGNIA en la tarjeta, así que tienen que caber en una: «Alojamiento», «Transporte», «Equipo», «Fuente»,
«Capítulo», «Servidor». Una frase descriptiva («Tarifa del transporte para 4 pasajeros detallando los cargos») NO es
un rol: eso es el CONTENIDO de la pieza y va en sus datos, no en su nombre. Ejemplos de cuándo aplica: un viaje se
compone de alojamiento + transporte; un trabajo escrito, de fuentes + capítulos; una arquitectura, de sus
componentes. Si lo que se busca es UNA sola cosa (un portátil, un piso, un artículo), composite:false y `parts` vacío.

Cómo pensar cada campo:

- HARD vs SOFT: sepáralos de verdad. Un blando tratado como duro deja la búsqueda vacía; un duro tratado como
  blando entrega algo inservible. Fechas, número de personas, medidas físicas, límite de presupuesto y requisitos
  legales/técnicos suelen ser duros. «Idealmente», «si puede ser», «nos gustaría» son blandos.
- ASSUMED: si falta un dato para poder buscar, ASÚMELO con el valor más razonable y anótalo aquí. No bloquees la
  investigación por un dato menor, pero que quede dicho para poder confirmarlo luego.
- ENRICHMENTS: es tu aportación como experto y es lo que distingue un brief bueno. Deduce consecuencias de lo que
  el operador SÍ dijo (si viajan con su propio vehículo, en destino necesitarán dónde aparcarlo; si son niños de
  cierta edad, lo que les sirve no es lo mismo que para un bebé; si hay una fecha límite, la disponibilidad
  importa tanto como el precio). Cada enriquecimiento con su porqué en una línea.
- MIN_CANDIDATES: un número entero, el tuyo. Razónalo: ¿cuántos hay que EVALUAR para que la selección sea
  defendible en ESTE dominio y ESTE mercado? Un mercado grande pide muchos; uno pequeño o raro tiene pocos, y
  entonces el número es lo que existe — dilo en `assumed` («mercado pequeño: apenas hay N»), no lo infles.
- MARKET y SOURCES: el país y la categoría de la PETICIÓN (si no los dijo, los que se deducen de él y del contexto, y
  anótalo en `assumed`), y las fuentes donde ese tipo de cosa se publica en ESE país — las que usaría un experto
  local, no las de otro país. Tantas como pidan sus criterios: un solo portal ve un solo subconjunto.
- ANGLES: rutas de búsqueda que devuelven conjuntos DISTINTOS (un agregador y la web del propio proveedor no dan
  lo mismo; buscar por zona, por característica o por nombre tampoco). Sin ángulos variados la amplitud es falsa.
- QUALITY_BAR: verificaciones CONCRETAS y comprobables, no adjetivos. «Que sea bueno» no es un baremo; «nota
  media ≥8 con al menos 100 opiniones» y «confirmar en las fotos que existe lo prometido» sí lo son.
- DELIVERABLE: si cada propuesta se compone de varias piezas que hay que reservar/conseguir por separado, marca
  composite:true y nombra los ROLES en `parts` — así el ejecutor entrega propuestas completas y comparables en vez
  de tres listas sueltas que el operador tendría que combinar a mano."""


# V2-840 H4 — a resource formula, not a script: after what he asked for, the material that shows it.
_MEDIA_FIRST = ("MATERIAL VISUAL CON PRIORIDAD: después de la información pedida, donde exista foto, vídeo o gráfico "
                "del candidato, va en el item (`image`/`images`, el enlace al vídeo o al gráfico): se juzga mirando.")


def _count_words(n) -> dict:
    """How the block names the count: the composer's number, or none when it declared none (V2-840 H1)."""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    if n:
        return {"best": f"las {n} mejores", "props": f"{n} PROPUESTAS COMPLETAS, no {n} listas sueltas",
                "last": f"tu nº{n}", "final": f"las {n} definitivas", "kept": str(n)}
    return {"best": "las mejores (cuántas, las que merezcan presentarse)",
            "props": "PROPUESTAS COMPLETAS, no listas sueltas", "last": "la última que presentes",
            "final": "las definitivas", "kept": "<nº presentadas>"}


def _gather(breadth: dict) -> str:
    """The funnel's first step with the composer's own number, or with none when it declared none (V2-840 H1)."""
    try:
        minc = int(breadth.get("min_candidates") or 0)
    except (TypeError, ValueError):
        minc = 0
    return (f"al menos {minc} candidatos reales" if minc else
            "los candidatos reales que hagan falta para que la selección sea defendible en este mercado")


def _market_lines(brief: dict) -> list[str]:
    """V2-840 H3/H5 — the angles, the market, its sources and what he excluded travel to the worker: one portal swept is one subset
    seen, a search with no country pulls another country's classifieds, and an exclusion is judged by each row's facts."""
    L: list[str] = []
    angles = (brief.get("breadth") or {}).get("angles")
    if angles:
        L.append("\nÁNGULOS DE BÚSQUEDA (usa VARIOS: por un solo camino verás siempre el mismo subconjunto y la "
                 "amplitud será falsa):\n" + "\n".join(f"  · {x}" for x in angles))
    mk = brief.get("market") or {}
    if mk:
        L.append("\nMERCADO: " + " · ".join(str(mk[k]) for k in ("country", "category") if mk.get(k))
                 + " — tus búsquedas llevan este país y esta categoría; lo de otro país no es candidato.")
    if brief.get("sources"):
        L.append("\nFUENTES CANDIDATAS de este mercado (usa tantas como pidan los criterios, y añade las que "
                 "descubras; cada una que pruebes va a `sources` con su estado):\n"
                 + "\n".join(f"  · {x}" for x in brief["sources"]))
    if brief.get("excluded"):
        L.append("\nLO QUE ÉL HA EXCLUIDO (juzga cada candidato por SUS datos — dónde está, cómo es —, no por si la "
                 "palabra aparece):\n" + "\n".join(f"  · {x}" for x in brief["excluded"]))
    return L


def to_prompt_block(brief: dict) -> str:
    """The brief as a block for the worker's prompt. The FUNNEL is explicit and placed first because it is the
    instruction the worker skips unless told: gather broadly BEFORE discarding. Written without naming any
    domain — it works equally for hotels, papers, or libraries."""
    if not isinstance(brief, dict) or not brief.get("goal"):
        return ""
    b = brief.get("breadth") or {}
    d = brief.get("deliverable") or {}
    gather = _gather(b)
    w = _count_words(d.get("n_final"))
    L: list[str] = []
    rnd = int(brief.get("round") or 1)
    L.append(f"BRIEF DE INVESTIGACIÓN (ronda {rnd}) — esto NO es una búsqueda rápida: es una SELECCIÓN que hay "
             "que poder defender.")
    L.append(f"OBJETIVO: {brief['goal']}")
    if brief.get("domain"):
        L.append(f"DOMINIO: {brief['domain']}")
    L.append("")
    L.append(f"EMBUDO OBLIGATORIO — en este orden, y NO te salgas del orden:\n"
             f"  1) REÚNE {gather} antes de descartar NINGUNO. Buscar 5 y quedarte con 3 "
             f"no es seleccionar, es conformarse: la primera página de un buscador no es el espacio de opciones. "
             f"Si el mercado tiene menos, entrega lo que hay y di en el sumario POR QUÉ (mercado pequeño, muros).\n"
             f"  2) FILTRA por los criterios duros (los que incumplan quedan fuera, sin excepción).\n"
             f"  3) PUNTÚA los que sobrevivan con los criterios blandos y los enriquecimientos.\n"
             f"  4) VERIFICA A FONDO solo a los finalistas, contra el baremo de calidad — ahí es donde se gasta el "
             f"esfuerzo: entrar en la fuente, leer las opiniones, mirar las fotos, confirmar los datos.\n"
             f"  5) ENTREGA {w['best']}, cada una con sus datos verificados.")
    if brief.get("hard"):
        L.append("\nCRITERIOS DUROS (incumplir = descalificado):\n" + "\n".join(f"  · {x}" for x in brief["hard"]))
    if brief.get("soft"):
        L.append("\nCRITERIOS BLANDOS (puntúan, no descalifican):\n" + "\n".join(f"  · {x}" for x in brief["soft"]))
    if brief.get("enrichments"):
        L.append("\nLO QUE HAY QUE TENER EN CUENTA aunque no se pidiera explícitamente:\n"
                 + "\n".join(f"  · {x}" for x in brief["enrichments"]))
    if brief.get("assumed"):
        L.append("\nDATOS ASUMIDOS (el operador no los dijo; se han supuesto — MENCIÓNALOS al entregar para que "
                 "pueda corregirlos):\n" + "\n".join(f"  · {x}" for x in brief["assumed"]))
    L += _market_lines(brief)
    if brief.get("quality_bar"):
        L.append("\nBAREMO DE CALIDAD (verifícalo de verdad en los finalistas; no lo des por supuesto):\n"
                 + "\n".join(f"  · {x}" for x in brief["quality_bar"]))
    if brief.get("feedback"):
        L.append("\nPOR QUÉ NO VALIÓ LA RONDA ANTERIOR (corrígelo en esta):\n"
                 + "\n".join(f"  · {x}" for x in brief["feedback"]))

    parts = d.get("parts") or []
    L.append("")
    if d.get("composite") and parts:
        L.append(f"ENTREGABLE — {w['props']}. Cada propuesta se compone "
                 f"de: {' + '.join(parts)}. El operador tiene que poder comparar propuestas enteras y elegir una, "
                 f"no combinar piezas a mano. Cada pieza va en `parts` del item, con su `kind` ({', '.join(parts)}), "
                 f"su precio y su enlace real.")
    else:
        L.append(f"ENTREGABLE — {w['best']} opciones, cada una con sus datos verificados y su enlace real.")
    # ORDER = part of the deliverable, not cosmetic (operator request 2026-08-12: «sort the ten best from one to
    # ten»). An unordered list forces the operator to redo the comparison the worker has already made.
    L.append(f"ORDENADAS DE MEJOR A PEOR — la primera es tu nº1 y la última {w['last']}. El orden en que las mandes "
             f"ES el ranking (la hoja las pinta en ese orden), y cada una lleva su `score` con el `why` en una "
             f"frase: sin el porqué, el operador no puede discutir ni corregir tu criterio. Si dos empatan, "
             f"desempata con los criterios blandos y dilo.")
    L.append("Móntalas en la superficie de resultados con `python -m nucleo.cli.widget read results` para ver el "
             "contrato exacto. IMPORTANTE para que el operador pueda PREGUNTAR después ('¿lleva desayuno?', '¿a qué "
             "hora es la entrada?'): mete los datos duros en `facts` del item y de cada pieza, y las fotos REALES "
             "en `images` — lo que no dejes ahí, zaelar no lo sabrá cuando él pregunte, y tendrá que buscarlo otra vez.")
    # V2-851 F3 — the results sheet's full contract (media first, what an item is, filling it while working, the
    # trail tabs, the breadth reported) is the catalogue family `results`, read on request: headline here.
    L.append("LA HOJA, ENTERA (qué es un item, llenarla mientras trabajas, fuentes, descartados, amplitud): "
             "`python -m nucleo.cli.bridge catalog results` — antes de tu primer `present`.")
    L.append("NO COMPROMETAS NADA: tu trabajo acaba en PROPONER. No reserves, no compres, no pagues, no contrates "
             "ni envíes nada en nombre del operador —aunque encuentres la opción perfecta y aunque parezca el "
             "siguiente paso obvio—: esa decisión es suya y la toma al ver las propuestas.")
    L.append("CIERRE HONESTO: acaba ofreciéndole SEGUIR buscando o AFINAR los criterios. Si algo del baremo no has "
             "podido verificar, dilo en vez de darlo por bueno — una propuesta con un dato sin confirmar y avisado "
             "vale; una con un dato inventado, no. Si el operador te dice que sigas, se reanuda esta misma "
             "investigación con más amplitud, así que no hace falta que él repita los criterios.")
    return "\n".join(L)


def sheet_contract(n_final=None) -> str:
    """The results sheet's full contract for a research worker (catalogue family `results`, V2-851 F3)."""
    w = _count_words(n_final)
    L: list[str] = []
    L.append(_MEDIA_FIRST)
    # THE SHEET FILLS UP WHILE YOU WORK (2026-08-12, operator request). Serious research takes 5 to 15 minutes,
    # and until now the brief only asked for delivery AT THE END: the operator was left staring at an empty sheet
    # —or worse, the previous search's sheet—without knowing whether anything was happening. Their rule: «a
    # brainworker that is producing results must place candidates in the widget as they obtain them». It is not
    # cosmetic: it lets them CORRECT the direction after two minutes instead of fifteen (and it has already
    # happened: they had to say «narrow it down to 42–49 feet» with the worker halfway through).
    # WHAT AN ITEM IS (V2-538, 2026-09-01, measured on the operator's screen): a live catamaran search filled
    # the sheet with portal LANDING PAGES ("Catamaranes de segunda mano | Milanuncios" + its SEO blurb), a
    # DEALER's name as if it were a boat, and a candidate 4x over the budget. The worker was dumping search
    # snippets as items. The rule is stated here — where the funnel is taught — and in the sheet's own
    # worker_guide, because the sheet's list is what the operator reads as THE result.
    L.append("\nQUÉ ES UN ITEM DE LA HOJA — regla dura:\n"
             "  · Un item es UN candidato CONCRETO y REAL: esta cosa, con su nombre propio, su precio si el "
             "dominio lo tiene, su ubicación y su foto real. La PORTADA de un portal, una página de categoría o "
             "de búsqueda, o la home de un vendedor NO son items — son FUENTES y se reportan en `sources`. Un "
             "candidato que incumple un criterio duro tampoco es un item: se descarta.\n"
             "  · Si aún no tienes candidatos concretos, deja la lista VACÍA y cuenta el avance en el subtítulo "
             "y el sumario: una lista vacía y honesta vale más que una llena de páginas.")
    L.append(f"\nLA HOJA SE LLENA MIENTRAS TRABAJAS, no solo al final — el operador está MIRANDO:\n"
             f"  · En cuanto tengas los PRIMEROS candidatos reales (no esperes a filtrar), haz un `present` con el "
             f"título del encargo, un subtítulo que diga en qué punto vas («en curso · 12 candidatos, aún sin "
             f"filtrar») y los que lleves. Marca lo provisional COMO provisional: una opción sin verificar que "
             f"parece definitiva es peor que un hueco.\n"
             f"  · Después ve AÑADIENDO con `append` a medida que confirmes candidatos que pasan el filtro duro, y "
             f"refresca el subtítulo con el recuento real. Unas pocas actualizaciones con avance de verdad, no una "
             f"por candidato.\n"
             f"  · Al entregar, un `present` FINAL con {w['final']} y verificadas, que REEMPLAZA lo "
             f"provisional. Lo que quede en pantalla al acabar tiene que ser exactamente tu selección.\n"
             f"  · Si al final descartas algo que habías publicado, que desaparezca DE LA LISTA: la hoja no es un "
             f"historial, es el estado ACTUAL de tu trabajo. Pero repórtalo abajo con `rejected` — desaparecer de "
             f"la pantalla y perderse no son lo mismo.")
    # THE OTHER THREE TABS (2026-08-12). The sheet is no longer just the list: it includes SUMMARY, SOURCES, and
    # CRITERIA. Sources are the missing piece that lets the operator AUDIT the work: until now, a website that
    # kept us out (login, limit of 50, block) and a website with no results looked exactly the same —«I found
    # nothing»—so they could not know whether it was worth entering manually, changing sites, or giving up.
    L.append("\nDEJA RASTRO DE CÓMO TRABAJAS — la hoja tiene tres pestañas más y se llenan MIENTRAS buscas:\n"
             "  · FUENTES: cada sitio en el que entras (o al que no puedes entrar) se reporta con "
             "`python -m nucleo.cli.widget data results sources @fuentes.json` → "
             "`{\"sources\":[{\"name\":…,\"url\":…,\"status\":…,\"detail\":…,\"found\":N}]}`. `status`: `ok` · "
             "`partial` (entraste pero te limitó los resultados) · `auth` (pedía sesión) · `blocked` · `error` · "
             "`pending`. Es UPSERT por url, así que puedes anunciar la fuente y actualizarla al terminar con "
             "ella. ESTO NO ES OPCIONAL: si una web te deja fuera, decir solo «no encontré nada» le oculta al "
             "operador que ahí SÍ había algo y que él sí puede entrar.\n"
             "  · SUMARIO: `… data results progress` con `{\"state\":\"…\",\"explored\":N,\"discarded\":N,"
             "\"steps\":[\"…\"]}` cada vez que haya avance de verdad (no un mensaje por candidato).\n"
             # V2-728 — the count was ALL that survived a rejection, so «¿y por qué no este?» had no answer
             # anywhere in the system: fifty candidates looked at and fifty reasons thrown away. Reported as
             # you go, for the reason `sources` is: a decision is written down when it is taken, and a worker
             # asked to reconstruct fifty of them at the end reports none.
             "  · DESCARTADOS: `… data results rejected @descartados.json` → `{\"rejected\":[{\"title\":…,"
             "\"url\":…,\"why\":…,\"source\":…}]}`, CADA candidato real que miraste y dejaste fuera, con su "
             "motivo. `why` es obligatorio y es el valor de la fila: «1.450 €, por encima del tope de 1.200» se "
             "puede discutir, «no encaja» no. No sale en la lista —la lista es tu selección— pero queda vinculado "
             "a la tarea, y es lo que le permite al operador preguntar «¿y por qué descartaste ese?» días "
             "después, en vez de que le repitamos la búsqueda entera.\n"
             "  · CRITERIOS: ya están sembrados con este brief; solo los tocas (`… data results criteria` con "
             "`{\"changes\":[\"…\"]}`) si el operador te corrige a mitad de camino.")
    L.append(f"AMPLITUD REPORTADA: cuando entregues, di cuántos candidatos has considerado DE VERDAD y con qué "
             f"criterio has cortado, y repórtalo también con "
             f"`python -m nucleo.cli.report considered <nº> --kept {w['kept']}`. Es lo que le permite al operador "
             f"saber si la selección es sólida o si conviene seguir buscando. Ese número es el RESUMEN de los "
             f"`rejected` que ya has ido reportando, no un sustituto: el número dice cuánto miraste, las filas "
             f"dicen qué miraste.")
    return "\n".join(L)
