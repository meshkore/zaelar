"""What a worker is told about where its result goes: the document, the library, the errand, its language.
"""
from __future__ import annotations


# V2-644 — the errand whose surface is `informe`: the DOCUMENT sheet is already on screen, bound to this task,
# streaming its process view. The delivery contract flips: step 4d is the PRIMARY route and the results sheet
# does not exist for this errand. Measured need (the Juncal research, 2026-09-09): a report errand on the
# results surface ended with a page-scrape's trust badges shown as «resultados» and no report at all.
# V2-831 T-25 — and the skeleton is the FIRST step after the plan: «once you have the structure» let a worker research
# for six minutes (demo pass 8, F1) with the sheet empty on his screen.
DOC_SURFACE_BLOCK = (
    "ENTREGA COMO INFORME (la superficie de este encargo es un DOCUMENTO): el operador pidió un ESCRITO y la "
    "hoja `documento` YA ESTÁ ABIERTA en su pantalla, enseñando tu progreso en vivo mientras trabajas — tus "
    "fases de cli.report son lo que él lee ahí, repórtalas de verdad (qué fuente miras, qué acabas de "
    "confirmar). La hoja de RESULTADOS NO está abierta para este encargo: NO entregues en `results` ni "
    "vuelques listas de candidatos — el paso 4b no aplica; aplica el 4d con `documento`. TU PRIMER PASO DESPUÉS "
    "DEL PLAN, antes de buscar o leer nada: `show` con el esqueleto del informe (título del asunto y sus "
    "secciones, aunque aún estén vacías). Después, cada sección con `data documento append @parte.json` EN "
    "CUANTO la tengas: escribe pronto y afina después (un `show` nuevo con el texto mejorado sustituye al "
    "anterior) — el operador ve crecer el documento en vez de esperar callado. Justo antes de redactar, di la "
    "fase «Elaborando el informe con toda la documentación». El `title` del documento lleva el nombre "
    "VERDADERO del asunto (si las fuentes dicen otro que el fonético del encargo, corrígelo en el siguiente "
    "`show`), y `source` de dónde sale. La voz final es corta: el informe ya lo está leyendo.")


def library_block() -> str:
    """V2-661 — WHERE the operator's files live, for a worker that has to SAVE one.

    Measured (session 1cdcb08e, 2026-09-11): asked to «guardar la Declaración en mis archivos», the worker
    wrote a perfect `.md` into `widgets/_data/navegador/` — the browser task's directory, the only path it had
    ever been told — then read the `archivos` card, saw nothing, and spent four minutes trying to download a
    PDF through the browser. Nobody had told it the library exists. Resources are nailed down (the doctrine):
    the ROOT path, the shelves, and the one action that files a text. Fail-soft: without a resolvable library
    the block is empty rather than a guess."""
    try:
        from library import paths as _paths
        root = str(_paths.root())
        shelves = "/".join(_paths.KINDS)
    except Exception:  # noqa: BLE001
        return ""
    return (f"LOS ARCHIVOS DEL OPERADOR viven en la BIBLIOTECA del agente: `{root}` con una carpeta por clase "
            f"({shelves}) — es EXACTAMENTE lo que enseña el widget `archivos`, y NADA fuera de ese árbol aparece en "
            f"«sus archivos» (ni tu directorio de trabajo, ni el del navegador, ni Descargas del sistema). Para "
            f"GUARDAR un texto como fichero: escribe el JSON {{\"name\": \"…\", \"text\": \"…\"}} a `doc.json` y "
            f"`python -m nucleo.cli.widget data archivos save_document @doc.json` — lo deja en documents/ y abre esa "
            f"carpeta en la tarjeta. Un fichero que ya tienes en disco (un PDF descargado) se copia dentro de "
            f"`{root}/<carpeta>/` y luego `python -m nucleo.cli.widget data archivos refresh`. Si el texto ya está "
            f"en la hoja `documento`, `python -m nucleo.cli.widget data documento save_to_library` lo guarda sin "
            f"volver a traerlo.")


def errand_block() -> str:
    """V2-692 — a gestión with a THIRD PARTY is HANDED OVER, never sat out.

    Measured twice in a row (2026-09-13 and 2026-09-14). Asked to organise a meeting, the worker sent the
    message and then WAITED for the answer inside its own session: 25 `peek` calls, `sleep 150`, `sleep
    240`, `sleep 300`, `sleep 420`, a `Monitor` loop the permission gate refused — ten minutes of paid
    session doing nothing, and then the session ended and the task ended with it. When the person finally
    answered, nothing was left to read it. The operator had to drive every step by hand and said so:
    «tenía que asociarla a esa tarea en marcha y tenía que continuar ese workflow hasta que consiguiéramos
    cerrar la tarea».

    The mechanism for that already exists and is DURABLE — `nucleo/errands/`, a row rather than a process,
    woken by the world, surviving a restart. What was missing is that nobody told the worker it exists, so
    it reimplemented a worse version of it inside a session that dies. The line is short on purpose: the
    resource is nailed down (which call opens it, and that the job ENDS there), the reasoning is not.
    """
    return ("SI EL ENCARGO DEPENDE DE QUE OTRA PERSONA CONTESTE (organizar una reunión, acordar una hora, "
            "pedir algo a un tercero), NO te quedes esperando: eso NO es tu trabajo y tu sesión se muere "
            "antes que la conversación. Manda el mensaje con "
            "`python -m nucleo.cli.widget data mensajeria send_to @msg.json` incluyendo el campo "
            "`objective` con LO QUE HAY QUE CONSEGUIR en palabras del operador — ese campo es el que abre "
            "un ENCARGO durable, que el motor despierta solo cuando esa persona conteste, hoy o dentro de "
            "diez horas, y que apunta la cita y manda el enlace de Meet por su cuenta cuando se acuerde la "
            "hora. `send_to` es la puerta AUNQUE ya exista la conversación: lo que decide no es si te han "
            "escrito antes, es si esto abre una gestión que hay que seguir. Y un mensaje ANTIGUO que "
            "diga que algo ya se acordó NO es la prueba de que esté hecho: lo hecho se mira en la "
            "AGENDA, nunca en la conversación (medido: el worker leyó un «confirming our call» suyo de "
            "hace una hora, dijo «done, the call is set» y no había ninguna cita). Ese primer mensaje PROPONE: "
            "no des por confirmada una hora que esa persona no ha dicho, no apuntes tú la cita y no "
            "escribas tú ningún enlace de Meet — de las tres cosas se encarga el encargo cuando haya "
            "acuerdo, y adelantarlas es cómo se le acaba mandando a un tercero una hora inventada o un "
            "enlace de una cita que ya no existe (medido el 2026-09-14). En cuanto salga el mensaje, "
            "TERMINA y dilo — «le he escrito y sigo yo la conversación por ahí». Nada de `sleep`, ni "
            "bucles de `peek`, ni esperar la respuesta.")


def trusted_blocks(surface: str = "") -> str:
    """The extra blocks a TRUSTED worker's prompt carries, in order: the report-surface contract (V2-644) when
    the errand delivers a document, and where the operator's files live (V2-661). Empty when neither applies."""
    from nucleo import surfaces as _surfaces; from widgets.results import hard_checks as _hard  # noqa: E702
    out = [_hard.worker_block()] if _surfaces.opens_sheet(surface or "") else []   # his must-haves are columns
    from nucleo import picture_errand as _pe              # a picture errand delivers into the photo viewer
    out += [DOC_SURFACE_BLOCK] if _surfaces.opens_doc(surface or "") else _pe.prompt_blocks(surface or "")
    lib = library_block()
    if lib:
        out.append(lib)
    out.append(errand_block())
    return ("\n\n" + "\n\n".join(out)) if out else ""


def worker_language_block() -> str:
    """The language rule for ANY worker prompt — what the operator HEARS goes in the operator's language.

    V2-677. `_web_prompt` named the target language in its closing step; `_build_prompt`, the GENERIC worker,
    named it NOWHERE — and every block it does carry is Spanish, so a worker in an English session had a
    fully Spanish prompt and no statement that the conversation is in another language. Measured live
    2026-09-11 (session e896f596, 23:17:49): the worker's delivery came back «¡Hola, Richard! Qué gusto
    tenerte aquí — soy Johnny, tu asistente…» into an English conversation.

    Naming the language is not enough on its own, which is V2-452's finding: the model copies what it READS
    unless the prompt says which language is OURS. So this says both — the same two sentences the FlashBrain's
    own `_lang_lock` has carried since that batch, at the one seam every worker passes through.
    """
    try:
        from i18n import langs as _lg
        spec = _lg.current_language()
        native, name = spec.native, spec.name
    except Exception:
        return ""
    block = ("── IDIOMA DE LA ENTREGA (REGLA ABSOLUTA) ──\n"
             f"El operador habla {native} ({name}). TODO lo que llegue a él —tu conclusión final, el progreso "
             f"que reportas, lo que escribas en una hoja o un widget, y cualquier pregunta que le hagas— va "
             f"ENTERO en {native}.")
    if not str(native).lower().startswith("espa"):
        block += ("\n⚠️ ESTAS INSTRUCCIONES ESTÁN EN CASTELLANO A PROPÓSITO: son NOTAS INTERNAS del sistema, "
                  f"NO el idioma de la conversación. NUNCA copies su lengua — ni una palabra suelta: la "
                  f"petición puede venirte en castellano y tu entrega sigue yendo en {native}.")
    return block
