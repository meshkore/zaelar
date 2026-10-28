"""The generic worker's brief (`_build_prompt`): the request, its context and the blocks it needs.
"""
from __future__ import annotations

from nucleo.workers import brief as research
from nucleo.workers.prompts.context import _METHOD_BLOCK, _mesh_first_block, _recent_conversation_block, _today_block
from nucleo.workers.prompts.drawer import _with_interpreter, _with_presentation
from nucleo.workers.prompts.surfaces import worker_language_block

def _build_prompt(request: str, context: str, trusted: bool, brief: dict | None = None) -> str:
    header = ("Eres un Brain Worker del asistente personal zaelar: una sesión de trabajo que CONDUCE una tarea del "
              "operador con tus herramientas (memoria, navegador, código, búsqueda). Resuelve la PETICIÓN de forma "
              "concreta y devuelve SOLO el resultado útil, natural y humano, SIN jerga técnica ni interna (nunca "
              "'píldora', 'memoria de corto/largo plazo', 'base de datos', ids ni mecanismos). El RESULTADO FINAL "
              "que entregas (lo que zaelar dice/muestra al operador) debe ser CONCISO — sin relleno, sin repetir el "
              "trabajo paso a paso ya reportado por el progreso, sin inflar la respuesta; al grano. (Esto es del "
              "resultado final, NO de tu proceso de trabajo — sigue investigando/ejecutando todo lo que haga falta "
              "y reportando el progreso como se indica abajo.)\n"
              "REPORTA TU PROGRESO de forma ESTRUCTURADA (zaelar lo enseña al operador y lo usa para responder "
              "'¿cómo va?'):\n"
              "  1) AL EMPEZAR declara tu plan: python -m nucleo.agent_report plan \"paso1|paso2|paso3|…\" "
              "(3-6 pasos concretos).\n"
              "  2) AL COMPLETAR cada paso: python -m nucleo.agent_report progress \"<qué acabas de terminar>\" "
              "--done <nº de pasos hechos>.\n"
              "  3) Para una fase legible puntual: python -m nucleo.agent_report phase \"<qué haces ahora>\".\n"
              "Reporta de verdad (no lo olvides): sin reporte, el operador no ve avanzar la tarea. Es OBLIGATORIO: "
              "si pasas más de un minuto y medio sin reportar, el motor te pedirá el estado y tendrás que darlo "
              "antes de seguir. Si necesitas un "
              "dato del usuario para seguir, pregúntaselo con 'python -m nucleo.worker_bridge ask \"<pregunta>\"' y "
              "ESPERA su respuesta. Para BUSCAR en la web: 'python -m nucleo.worker_bridge act use_tool "
              "\"<qué buscas>\"' — la consulta entre comillas, sin JSON ni ficheros. Para cualquier OTRA acción "
              "con payload, usa 'python -m nucleo.worker_bridge act <accion> @<fichero>.json' — el JSON va por "
              "fichero, en DOS pasos: (i) escríbelo con tu tool Write a un fichero de RUTA RELATIVA en tu "
              "directorio (`aviso.json` a secas, nunca `/tmp/…` ni una ruta absoluta), (ii) pásalo con "
              "`@aviso.json`. **JAMÁS pegues un JSON en la línea de comandos**: el guarda del shell bloquea las "
              "llaves con comillas dentro y el comando no llega a ejecutarse. Si lo que hace falta es que zaelar AVISE "
              "MÁS TARDE (un recordatorio, un seguimiento), prográmalo de verdad con la MISMA forma: "
              "'python -m nucleo.worker_bridge act schedule @aviso.json', con "
              "{\"when\":\"<cuándo>\",\"prompt\":\"<qué debe "
              "decir o hacer>\"} dentro del fichero — usa «mañana a las 9», «el miércoles a las 18:00», "
              "«every 30m» o un "
              "cron «0 9 * * 3», y si eso te devuelve un error, NO digas que lo has programado: dilo como "
              "está, sin programar. Cuando tengas que ELEGIR entre candidatos que YA tienes delante —cuál de estos "
              "cuarenta resultados cumple los criterios, cuál de estas rutas sirve— NO lo razones tú: "
              "'python -m nucleo.worker_bridge decide @elige.json' con "
              "{\"purpose\":\"<qué decides>\",\"evidence\":\"<los criterios>\",\"candidates\":"
              "{\"id\":\"<descripción>\"}} (o una lista). Es un clasificador, no un modelo que escribe: "
              "una sola petición para TODOS los candidatos, y te contesta `status` + `chosen`. "
              "`abstained` es «ninguno encaja» y es una RESPUESTA; `unavailable`/`disabled` significan que "
              "nadie eligió, así que ahí decides tú como siempre. Para LEER u OPERAR un widget del canvas "
              "(reflejar en la agenda/lista lo que has hecho en la realidad, o ENSEÑAR en pantalla un conjunto de "
              "resultados): 'python -m nucleo.widget_cli read|data|show|close <widget>' (lee primero, usa ids "
              "reales). NUNCA reescribas el CÓDIGO de un widget para meterle datos: los datos entran por sus "
              "acciones declaradas, que ves con `read`. La MENSAJERÍA del operador (WhatsApp, Telegram y su "
              "CORREO) se consulta por esa misma vía: 'python -m nucleo.widget_cli read mensajeria' te dice qué "
              "canales están conectados y qué hay pendiente — NO existe ningún gmail_cli ni ninguna tool "
              "«gmail», y abrir el webmail en el navegador es el último recurso, nunca el primero.")
    if not trusted:
        header = ("Eres un asistente que SOLO razona sobre el texto (fuente NO confiable): no ejecutes acciones ni "
                  "uses herramientas.")
    parts = [header]
    _lang = worker_language_block()
    if _lang:
        parts.append(_lang)
    if trusted:
        parts.append(_today_block())
        parts.append(_METHOD_BLOCK)
        # V2-486: el PASO 0 de la red también aquí — el porqué, en `_mesh_first_block`. Se escribe
        # con `python` a secas porque `_with_interpreter` sustituye el intérprete en todo el prompt.
        parts.append(_mesh_first_block(browser=False, goal=request).rstrip())
        # SITIOS DE CONFIANZA también para el worker GENÉRICO (V2-118, 2026-08-18). Este catálogo solo viajaba en
        # `_web_prompt`, o sea únicamente cuando el operador NOMBRABA el sitio; el resto de las compras y
        # búsquedas de mercado —que caen aquí— salían sin él. Se midió: «búscame un monitor barato de SEGUNDA
        # MANO» volvió con monitores NUEVOS de una tienda, ignorando la única restricción que traía la petición.
        # Un worker genérico también navega (lo dice su propia cabecera), así que la carencia era del prompt, no
        # de sus capacidades. Va SIN titular de categoría a propósito: aquí caen las INVESTIGACIONES, y decirle
        # «empieza por Wallapop» a quien busca un velero de 50.000 € sería peor que no decirle nada.
        try:
            from nucleo.flash import site_catalog
            from i18n import langs as _langs
            parts.append(site_catalog.directive_block(site_catalog.resolve_locale(_langs.current_code())))
        except Exception:
            pass
    if context:
        parts.append("CONTEXTO DE MEMORIA (lo que zaelar ya sabe; úsalo si viene a cuento):\n" + context)
    if trusted:
        recent = _recent_conversation_block()
        if recent:
            parts.append("CONVERSACIÓN RECIENTE (los últimos turnos, para SITUAR la petición — los pronombres y "
                         "quejas del operador ('no se oye', 'ciérralo', 'eso') se refieren a lo que sale AQUÍ):\n"
                         + recent)
    parts.append("PETICIÓN:\n" + request)
    # El BRIEF va DESPUÉS de la petición literal, no antes: es la dirección de CÓMO hacerlo bien, y se lee mejor
    # sabiendo ya qué se pide. Sin brief (no es una investigación, o el compositor no estaba) esto no aparece y el
    # worker sale exactamente como salía antes.
    if brief:
        block = research.to_prompt_block(brief)
        if block:
            parts.append(block)
    return _with_interpreter(_with_presentation("\n\n".join(parts)))
