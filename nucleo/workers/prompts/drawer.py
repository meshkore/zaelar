"""The rules of the box a worker runs in (the drawer, the interpreter) and how it presents what it found.
"""
from __future__ import annotations


# PRESENTATION (2026-08-10): the brief says WHAT to find, this says how it is SHOWN — a flawless 45-candidate search
# was painted unreadable because each field's budget lived only in the widget's CSS.
def _with_presentation(prompt: str) -> str:
    """Añade las reglas de presentación de las superficies en blanco que el prompt mencione. Fail-open."""
    try:
        from widgets import presentation
        block = presentation.directive_for(prompt)
    except Exception:
        return prompt
    return prompt + "\n\n" + block if block else prompt


# The brief is WRITTEN with `python -m nucleo.…` for reading; what REACHES the worker is the real absolute interpreter
# (a bare `python` does not exist here, and the worker obeyed it literally and failed — 2026-08-02). One substitution.
def _with_interpreter(prompt: str) -> str:
    # Solo si el prompt REALMENTE trae puentes. El perfil UNTRUSTED (texto de un peer) va sin tools por
    # construcción: colarle la cabecera le daría la ruta absoluta del engine sin ninguna necesidad.
    if "python -m nucleo." not in prompt:
        return prompt
    try:
        from nucleo.workers.providers.claude import bridge_python
        py = bridge_python()
    except Exception:
        return prompt
    if not py or py == "python":
        return prompt
    out = prompt.replace("python -m nucleo.", f"{py} -m nucleo.")
    # V2-211 — LAS TRES FORMAS MEDIDAS de morir en nuestra propia puerta, el mismo día y en tres casos distintos:
    #   `find-theatre-tickets__es` 15:24  cd in '…/zaelar/engine' was blocked. For security, Claude Code may only
    #                                     change directories to the allowed working directory
    #   `cheapest-monitor`         15:35  This Bash command contains multiple operations. The following part
    #                                     requires approval: curl -s "https://www.pccomponentes.com/monitores"
    #   `remember-and-remind`      15:38  …requires approval: cd /Users/…
    # En headless NADIE aprueba, así que una petición de aprobación es un callejón sin salida: el worker muere ahí,
    # callado, y el turno sigue contando que avanza. Es el confirm-gate una capa más abajo — un gate que para el
    # trabajo y no tiene camino de vuelta.
    #
    # Se ataca por delante, que es lo que ya funcionó con el intérprete el 2026-08-02 (el worker se pasaba minutos
    # probando `python`, `python3`, `.venv/bin/python`… porque el prompt no le decía cuál). Las reglas del cajón
    # donde corre no las puede deducir: o se las damos, o las descubre chocando, y chocar aquí cuesta la tarea.
    return _drawer_rules(py) + out


def _drawer_rules(py: str = "") -> str:
    """Las reglas del cajón donde corre el worker, en UN solo sitio.

    Estaban dentro de `_with_interpreter`, al que solo llama `_build_prompt` — así que el worker WEB, que es el
    que más shell compone porque conduce un navegador, era el único que NUNCA las recibía. Medido en
    `search-secondhand-monitor__es` (2026-08-24 00:56): tres `cd in '<engine>' was blocked` seguidos, a los
    42 s, en una ronda que entregó cero. Misma asimetría que V2-257 y con el mismo perjudicado.

    Sin `py` no se nombra el intérprete: la lista de fuera del cajón es la misma con o sin él, y el builder web
    ya escribe la ruta absoluta en cada línea de comando.
    """
    _py = (py or "").strip()
    cab = (f"INTÉRPRETE: para CUALQUIER puente (`-m nucleo.…`) usa EXACTAMENTE `{_py}`, tal cual, siempre. Está "
           f"permitido y funciona. NO uses `python` a secas ni `python3` ni rutas relativas.\n") if _py else ""
    _puente = f"`{_py} -m nucleo.nav_cli`" if _py else "`nucleo.nav_cli`"
    _busca = f"`{_py} -m nucleo.worker_bridge`" if _py else "`nucleo.worker_bridge`"
    _abs = f"`{_py}` es absoluto" if _py else "el intérprete es absoluto"
    return (cab +
            "TU CAJÓN (reglas del shell donde corres; romperlas NO da error, pide una aprobación que aquí no va a "
            "llegar nunca):\n"
            "  · NO SALGAS DE TU DIRECTORIO, y no es solo el `cd`: el cajón bloquea CUALQUIER comando que "
            "navegue o liste carpetas del repo del motor (`cd`, `ls`, `find`, `cat` de rutas del repo…). No "
            f"hace falta: los puentes funcionan desde donde estás — {_abs} y el resto ya viaja en "
            "el entorno (el `-m nucleo.…` PARECE pedir que te muevas a otro sitio y NO lo pide: el entorno ya lo "
            "lleva). Si lo intentas, lo que vas a leer es «cd in '…' was blocked. For security, Claude Code "
            "may only change directories to the allowed working directories», y no hay rodeo: no es una "
            "forma del comando que se pueda reescribir, es un sitio al que no se va. Lo que SÍ puedes es ABRIR con Read un fichero concreto cuya ruta absoluta te hayamos "
            "dado nosotros (la captura del navegador); eso está permitido y probado.\n"
            "  · UN comando por llamada. Nada de `&&`, `;`, `|`, `$(…)`, `${…}`, comillas invertidas ni "
            "varias cosas en la misma línea: se lee como varias operaciones, o como una expansión que el "
            "guarda no puede verificar, y se para ahí («Contains simple_expansion»).\n"
            "  · Un `$` dentro de comillas DOBLES es una variable, también en un precio: \"under $400\" se "
            "rechaza igual («Contains simple_expansion») y, si pasara, el shell lo convertiría en «under 00». "
            "Escríbelo `\\$400` o pon ese texto entre comillas simples.\n"
            "  · Y NI UN SOLO `&` AL FINAL para dejar algo corriendo de fondo. No es lo mismo que `&&` y por "
            "eso va aparte: el guarda lo para con otro mensaje («uses the `&` background operator, which "
            "defers execution past approval-time safety checks») y quien solo haya leído «nada de `&&`» no "
            "puede atar una cosa con la otra. Tampoco te hace falta: lo que tarda ya es asíncrono por los "
            "puentes — lanza y recoge con `wait`, que para eso está.\n"
            "  · NINGÚN argumento con llaves y comillas dentro. Un JSON pegado en la línea se bloquea "
            "(«Contains brace with quote character»): escríbelo con Write a un fichero de tu directorio y "
            "pásalo con `@fichero.json`. Todos los puentes lo aceptan.\n"
            "  · Solo los puentes. Ni `curl`, ni `wget`, ni scripts propios: para ABRIR una página usa "
            f"{_puente}. Lo que traigas "
            "con `curl` además no pasa por el navegador del operador, así que ni ve las cookies ni cuenta como "
            "evidencia.\n"
            # TWO search engines, and the order between them (operator, 2026-09-28): the provider's own built-in
            # search is the most direct when it works; when its quota runs out, the worker falls over to ours —
            # the same search the FlashBrain uses (Google + several APIs), reached through the per-task bridge.
            "  · Para BUSCAR en la web tienes DOS buscadores. Primero el TUYO, si tu proveedor te lo da (tu "
            "herramienta integrada de búsqueda o de lectura web): es el más directo. Si falla por cuota o límite "
            "(«429», «quota», «limit», «usage»), o no lo tienes, usa el de Zaelar, que es el mismo que usa el "
            "asistente: "
            f"{_busca} act use_tool \"<qué buscas>\" — la consulta ENTRE COMILLAS, sin llaves ni ficheros. Devuelve "
            "una respuesta ya sintetizada, las páginas con su enlace y lo que NO encontró. No insistas con el tuyo "
            "después de un fallo de cuota: no vuelve en esta tarea.\n"
            "  · Si un comando te pide aprobación, lo escribiste mal: REESCRÍBELO en la forma de arriba. No lo "
            "reintentes igual, no busques otra vía y no te calles — si de verdad no hay forma, DILO como "
            "resultado (`hbnote`/tu entrega) en vez de terminar en silencio.\n\n")


# HUMAN behaviour on the web (operator's rule, 2026-07-21): generic, names no site, how a PERSON moves through a page.
# The technical stealth lives in widgets/navegador/owner.py; this is the rhythm, order and gestures the model controls.
_HUMAN_NAV_GUIDE = (
    "NAVEGA COMO UNA PERSONA, no como un robot (vale para casi cualquier web, en español o inglés; eres un "
    "asistente navegando POR el operador, no un extractor masivo):\n"
    "• RITMO humano: una acción cada vez, deja que la página cargue y 'léela' con `look` antes de seguir. No "
    "dispares comandos a ráfagas ni recargues la misma página en bucle.\n"
    "• Usa la PROPIA web como un usuario: su buscador y sus FILTROS (precio, ubicación, categoría, orden por "
    "fecha/precio) en vez de forzar URLs raras o parámetros a mano. Escribe en su caja de búsqueda y pulsa buscar.\n"
    "• COOKIES/consentimiento: acéptalos con naturalidad (un humano lo hace) para poder ver el contenido; si el "
    "banner reaparece, ciérralo y sigue.\n"
    "• Desplázate GRADUALMENTE (scroll de a poco, como quien ojea) para que carguen los resultados; abre una "
    "ficha/anuncio concreto para leer el detalle, como una persona interesada de verdad.\n"
    "• Si aparece una VERIFICACIÓN anti-robot, un captcha o un aviso de 'demasiadas peticiones': NO insistas a lo "
    "bruto (eso confirma que eres un bot). Para, espera unos segundos y reintenta UNA vez despacio; si sigue "
    "bloqueado, prueba OTRA web equivalente que tenga el mismo dato, o dilo con honestidad. Nunca machaques ni "
    "recargues en bucle.\n"
    "• No hagas nada 'raro': no toques login/pagos salvo que el objetivo lo pida y tengas permiso; no aceptes "
    "promos ni suscripciones; céntrate en el objetivo como lo haría una persona con prisa pero educada.\n\n"
)


def _category_lead(goal: str, lang_code: str | None) -> str:
    """One line naming the trusted site for THIS goal's category, ahead of the whole catalog (V2-119).

    The catalog block that follows lists every category, and a worker reading six bullets still has to decide
    which one is its own — `restaurant-tonight-madrid` shows what that costs: the run never reached TheFork at
    all, and the worker ended up asserting a policy about the restaurant it had never opened. Naming the site
    the dispatcher ALREADY matched (it is the same call that routed this task to the browser in the first
    place, `dispatch._classify_kind`) removes that decision. When no category matches, this is empty and the
    catalog behaves exactly as before."""
    from nucleo.flash import site_catalog
    loc = site_catalog.resolve_locale(lang_code)
    category = site_catalog.category_of(goal, loc)
    entry = site_catalog.entry_for(category, loc) if category else None
    if entry is None:
        return ""
    return (f"ESTA TAREA es de categoría «{category}»: EMPIEZA por {entry.name} ({entry.url}) — {entry.note} "
            f"Solo si el objetivo genuinamente NO aparece ahí, ve a otro sitio, y DILO al entregar.\n\n")
