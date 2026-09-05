"""nucleo/research_prompts.py — the research-brief composer's prompt text (split out of research.py, 2026-08-17
modularization pass). `_SYSTEM` (the LLM instructions for turning a request into a structured research brief)
and `to_prompt_block()` (the ~140-line formatter that renders a composed brief into the worker's prompt) are
pure string assembly with no I/O and no orchestration state — the audit that led to this split found them a
clean, separable concern from `research.py`'s actual compose/expand/persist logic.

Deliberately a LEAF module: it takes `min_candidates_floor` as a parameter instead of importing
`research.py`'s `_MIN_CANDIDATES_FLOOR` constant, so this file has zero dependency on `research.py` — avoids a
circular import (research.py needs `_SYSTEM`/`to_prompt_block` back from here) without duplicating the
constant's value anywhere. `research.py` re-exports `_SYSTEM` directly and wraps `to_prompt_block` with its own
constant, so the external call shape (`research.to_prompt_block(brief)`, used by `nucleo/dispatch_prompts.py`)
is unchanged."""
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
  "soft": ["preferencias que PUNTÚAN pero no descalifican"],
  "assumed": ["datos que el operador NO dio y has tenido que asumir, con el valor asumido — para poder decírselo"],
  "enrichments": ["lo que un EXPERTO de este dominio añadiría y el operador no pensó en pedir, con su porqué"],
  "breadth": {
    "min_candidates": 40,
    "angles": ["formas DISTINTAS de buscar, para no ver el mismo subconjunto tres veces"]
  },
  "quality_bar": ["qué hay que VERIFICAR de verdad para que un finalista cuente como verificado"],
  "deliverable": {
    "widget": "results",
    "n_final": 10,
    "//n_final": "CUÁNTAS se entregan. Si el operador DIJO un número («las tres mejores», «ponme veinte»), pon ESE
                  número. Si no dijo ninguno, pon 10 — no 3: con tres no se ve el segundo pelotón y el operador no
                  puede juzgar si el corte fue bueno. Máximo 20.",
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
- MIN_CANDIDATES: cuántos candidatos hay que REUNIR antes de empezar a descartar. Sé exigente: elegir «el mejor»
  entre 8 no es elegir, es conformarse. Para una selección normal, decenas. Piensa en cuántos habría que ver para
  que la respuesta sea defendible.
- ANGLES: rutas de búsqueda que devuelven conjuntos DISTINTOS (un agregador y la web del propio proveedor no dan
  lo mismo; buscar por zona, por característica o por nombre tampoco). Sin ángulos variados la amplitud es falsa.
- QUALITY_BAR: verificaciones CONCRETAS y comprobables, no adjetivos. «Que sea bueno» no es un baremo; «nota
  media ≥8 con al menos 100 opiniones» y «confirmar en las fotos que existe lo prometido» sí lo son.
- DELIVERABLE: si cada propuesta se compone de varias piezas que hay que reservar/conseguir por separado, marca
  composite:true y nombra los ROLES en `parts` — así el ejecutor entrega propuestas completas y comparables en vez
  de tres listas sueltas que el operador tendría que combinar a mano."""


def to_prompt_block(brief: dict, min_candidates_floor: int = 25) -> str:
    """The brief as a block for the worker's prompt. The FUNNEL is explicit and placed first because it is the
    instruction the worker skips unless told: gather broadly BEFORE discarding. Written without naming any
    domain — it works equally for hotels, papers, or libraries."""
    if not isinstance(brief, dict) or not brief.get("goal"):
        return ""
    b = brief.get("breadth") or {}
    d = brief.get("deliverable") or {}
    minc = b.get("min_candidates") or min_candidates_floor
    nfin = d.get("n_final") or 3
    L: list[str] = []
    rnd = int(brief.get("round") or 1)
    L.append(f"BRIEF DE INVESTIGACIÓN (ronda {rnd}) — esto NO es una búsqueda rápida: es una SELECCIÓN que hay "
             "que poder defender.")
    L.append(f"OBJETIVO: {brief['goal']}")
    if brief.get("domain"):
        L.append(f"DOMINIO: {brief['domain']}")
    L.append("")
    L.append(f"EMBUDO OBLIGATORIO — en este orden, y NO te salgas del orden:\n"
             f"  1) REÚNE al menos {minc} candidatos reales antes de descartar NINGUNO. Buscar 5 y quedarte con 3 "
             f"no es seleccionar, es conformarse: la primera página de un buscador no es el espacio de opciones.\n"
             f"  2) FILTRA por los criterios duros (los que incumplan quedan fuera, sin excepción).\n"
             f"  3) PUNTÚA los que sobrevivan con los criterios blandos y los enriquecimientos.\n"
             f"  4) VERIFICA A FONDO solo a los finalistas, contra el baremo de calidad — ahí es donde se gasta el "
             f"esfuerzo: entrar en la fuente, leer las opiniones, mirar las fotos, confirmar los datos.\n"
             f"  5) ENTREGA las {nfin} mejores, cada una con sus datos verificados.")
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
    if b.get("angles"):
        L.append(f"\nÁNGULOS DE BÚSQUEDA (usa VARIOS: por un solo camino verás siempre el mismo subconjunto y los "
                 f"{minc} candidatos serán falsos):\n" + "\n".join(f"  · {x}" for x in b["angles"]))
    if brief.get("quality_bar"):
        L.append("\nBAREMO DE CALIDAD (verifícalo de verdad en los finalistas; no lo des por supuesto):\n"
                 + "\n".join(f"  · {x}" for x in brief["quality_bar"]))
    if brief.get("feedback"):
        L.append("\nPOR QUÉ NO VALIÓ LA RONDA ANTERIOR (corrígelo en esta):\n"
                 + "\n".join(f"  · {x}" for x in brief["feedback"]))

    parts = d.get("parts") or []
    L.append("")
    if d.get("composite") and parts:
        L.append(f"ENTREGABLE — {nfin} PROPUESTAS COMPLETAS, no {nfin} listas sueltas. Cada propuesta se compone "
                 f"de: {' + '.join(parts)}. El operador tiene que poder comparar propuestas enteras y elegir una, "
                 f"no combinar piezas a mano. Cada pieza va en `parts` del item, con su `kind` ({', '.join(parts)}), "
                 f"su precio y su enlace real.")
    else:
        L.append(f"ENTREGABLE — las {nfin} mejores opciones, cada una con sus datos verificados y su enlace real.")
    # ORDER = part of the deliverable, not cosmetic (operator request 2026-08-12: «sort the ten best from one to
    # ten»). An unordered list forces the operator to redo the comparison the worker has already made.
    L.append(f"ORDENADAS DE MEJOR A PEOR — la primera es tu nº1 y la última tu nº{nfin}. El orden en que las mandes "
             f"ES el ranking (la hoja las pinta en ese orden), y cada una lleva su `score` con el `why` en una "
             f"frase: sin el porqué, el operador no puede discutir ni corregir tu criterio. Si dos empatan, "
             f"desempata con los criterios blandos y dilo.")
    L.append("Móntalas en la superficie de resultados con `python -m nucleo.widget_cli read results` para ver el "
             "contrato exacto. IMPORTANTE para que el operador pueda PREGUNTAR después ('¿lleva desayuno?', '¿a qué "
             "hora es la entrada?'): mete los datos duros en `facts` del item y de cada pieza, y las fotos REALES "
             "en `images` — lo que no dejes ahí, zaelar no lo sabrá cuando él pregunte, y tendrá que buscarlo otra vez.")
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
             f"  · Al entregar, un `present` FINAL con las {nfin} definitivas y verificadas, que REEMPLAZA lo "
             f"provisional. Lo que quede en pantalla al acabar tiene que ser exactamente tu selección.\n"
             f"  · Si al final descartas algo que habías publicado, que desaparezca: la hoja no es un historial, es "
             f"el estado ACTUAL de tu trabajo.")
    # THE OTHER THREE TABS (2026-08-12). The sheet is no longer just the list: it includes SUMMARY, SOURCES, and
    # CRITERIA. Sources are the missing piece that lets the operator AUDIT the work: until now, a website that
    # kept us out (login, limit of 50, block) and a website with no results looked exactly the same —«I found
    # nothing»—so they could not know whether it was worth entering manually, changing sites, or giving up.
    L.append("\nDEJA RASTRO DE CÓMO TRABAJAS — la hoja tiene tres pestañas más y se llenan MIENTRAS buscas:\n"
             "  · FUENTES: cada sitio en el que entras (o al que no puedes entrar) se reporta con "
             "`python -m nucleo.widget_cli data results sources @fuentes.json` → "
             "`{\"sources\":[{\"name\":…,\"url\":…,\"status\":…,\"detail\":…,\"found\":N}]}`. `status`: `ok` · "
             "`partial` (entraste pero te limitó los resultados) · `auth` (pedía sesión) · `blocked` · `error` · "
             "`pending`. Es UPSERT por url, así que puedes anunciar la fuente y actualizarla al terminar con "
             "ella. ESTO NO ES OPCIONAL: si una web te deja fuera, decir solo «no encontré nada» le oculta al "
             "operador que ahí SÍ había algo y que él sí puede entrar.\n"
             "  · SUMARIO: `… data results progress` con `{\"state\":\"…\",\"explored\":N,\"discarded\":N,"
             "\"steps\":[\"…\"]}` cada vez que haya avance de verdad (no un mensaje por candidato).\n"
             "  · CRITERIOS: ya están sembrados con este brief; solo los tocas (`… data results criteria` con "
             "`{\"changes\":[\"…\"]}`) si el operador te corrige a mitad de camino.")
    L.append(f"AMPLITUD REPORTADA: cuando entregues, di cuántos candidatos has considerado DE VERDAD y con qué "
             f"criterio has cortado, y repórtalo también con "
             f"`python -m nucleo.agent_report considered <nº> --kept {nfin}`. Es lo que le permite al operador "
             f"saber si la selección es sólida o si conviene seguir buscando.")
    L.append("NO COMPROMETAS NADA: tu trabajo acaba en PROPONER. No reserves, no compres, no pagues, no contrates "
             "ni envíes nada en nombre del operador —aunque encuentres la opción perfecta y aunque parezca el "
             "siguiente paso obvio—: esa decisión es suya y la toma al ver las propuestas.")
    L.append("CIERRE HONESTO: acaba ofreciéndole SEGUIR buscando o AFINAR los criterios. Si algo del baremo no has "
             "podido verificar, dilo en vez de darlo por bueno — una propuesta con un dato sin confirmar y avisado "
             "vale; una con un dato inventado, no. Si el operador te dice que sigas, se reanuda esta misma "
             "investigación con más amplitud, así que no hace falta que él repita los criterios.")
    return "\n".join(L)
