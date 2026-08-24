"""nucleo/errand_kind.py — QUÉ CLASE DE ENCARGO es esto, y cómo se llama mientras corre.

Extraído de `nucleo/dispatch.py` el 2026-08-24 porque el trinquete de arquitectura pidió un módulo en vez de un
techo más alto, y el corte estaba dado: todo lo de aquí es una función PURA sobre el TEXTO de la petición — no
mira el registro de sesiones, no toca el pool, no escribe nada. `dispatch` se queda con lo suyo, que es qué hacer
con la respuesta.

Lo que gobierna este módulo es una frontera que ha costado varias rondas medirla, y por eso las regex llevan su
evidencia pegada: «rellena el widget con los resultados» es DATOS y no CÓDIGO, «pon un informe en pantalla» es
una investigación y no una gestión web, y un sitio conocido en la frase no convierte en navegación lo que era una
pregunta. Cada una de esas líneas nació de un worker que se fue a hacer lo que no era.
"""
from __future__ import annotations

import re


_WEB_RE = re.compile(
    r"\b(en\s+wallapop|wallapop|en\s+amazon|amazon|navegador|abre\s+la\s+web|abre\s+la\s+p[áa]gina|"
    r"en\s+linkedin|linkedin|en\s+el\s+sitio|en\s+la\s+p[áa]gina|automatiza|"
    r"in[ií]ciame?\s+sesi[óo]n|log[ui]n)\b", re.I)
# El generador (kind="code") SOLO construye/modifica el CÓDIGO de un widget. Antes `_CODE_RE` matcheaba la palabra
# «widget/tarjeta/panel» A SECAS → CUALQUIER tarea que la mencionara (p.ej. «abre y muestra el mensaje… se refleja
# en el widget de mensajería») caía en el generador y CONSTRUÍA un widget basura (incidente 2026-08-01, clase del
# 25/07). Fix V2-081: exige un VERBO de crear/modificar CÓDIGO junto al nombre — coherente con el guard del router
# (`looks_like_create_widget`, que también usa verbo+nombre); create se reutiliza de ahí (fuente única), aquí solo
# se añade el lado MODIFICAR-código. Mostrar/abrir/leer/gestionar un widget existente NO es código → kind="generic"
# (un worker general que, si hace falta, OPERA el widget vía hbwidget — nunca lo regenera).
_MODIFY_CODE_RE = re.compile(
    r"\b(modific\w*|cambi\w*|edit\w*|reescrib\w*|refactor\w*|redise[nñ]\w*|actualiz\w+ el c[oó]digo|"
    r"a[ñn]ad\w*\s+(?:una?\s+)?columna|modify|redesign|rewrite)\b[^.!?]{0,45}\b(widget|tarjeta|panel|componente)\b",
    re.I)
# …y lo MISMO con «proyecto», que estaba A SECAS una línea debajo del comentario que lo prohíbe (incidente
# 2026-08-12, auditando una búsqueda de veleros de punta a punta). El criterio que dio el propio operador era
# «listo para navegar, no un PROYECTO para restaurar» — en la compraventa de barcos «un proyecto» es el término
# corriente para un barco a medio reformar. Esa palabra sola mandó su BÚSQUEDA al `kind="code"`, o sea al backend
# del GENERADOR de widgets (`registry.get_backend` elige por `spec.kind`): un buscador despachado al sitio que
# escribe código. Es la misma clase exacta que V2-081, sin arreglar en esta rama.
# `architect` se queda A SECAS a propósito: es el nombre de nuestro conector, nadie lo dice de pasada. «Proyecto»
# es una palabra del castellano de todos los días, así que exige —como el lado MODIFICAR-código— un VERBO de
# trabajo de proyecto delante, o una palabra de repositorio detrás.
_ARCHITECT_RE = re.compile(
    r"\barchitect\b"
    r"|\b(crea\w*|monta\w*|arranca\w*|planifica\w*|retoma\w*|abre|cierra|a[ñn]ad\w*|actualiz\w*|"
    r"create|start|plan)\b[^.!?]{0,45}\bproyecto\b"
    r"|\bproyecto\b[^.!?]{0,45}\b(repo\w*|rama\w*|commit\w*|c[oó]digo|tarea\w*|meshkore|daemon)\b",
    re.I)
# …y el contrapeso: LLENAR un widget con datos NO es tocar su código (incidente 2026-08-02). El brief «finaliza y
# muestra el informe … REFLEJANDO EL CAMBIO en el widget de informes» casaba `cambi\w*` + `widget` dentro de la
# ventana de 45 chars → se despachó al GENERADOR, que se pasó 3,5 min REESCRIBIENDO widget.js para un caso que solo
# necesitaba una data-op, y el operador siguió sin ver nada. Un verbo de DATOS/PRESENTACIÓN en la misma frase gana:
# la petición es «pon estos datos ahí», no «cámbiame el componente». (Crear un widget nuevo sigue mandando: eso lo
# decide `looks_like_create_widget` con verbo+nombre y no pasa por aquí.)
_DATA_NOT_CODE_RE = re.compile(
    r"\b(refleja\w*|rellena\w*|llena\w*|puebla\w*|presenta\w*|muestra\w*|mostrar|ense[nñ]a\w*|pinta\w*|vuelca\w*|"
    r"pon(?:er|ga|gas)?\b[^.!?]{0,30}\b(?:datos|resultados|informe|lista|items)|fill|populate|render|display)\b",
    re.I)

def classify_kind(request: str) -> str:
    r = request or ""
    if _WEB_RE.search(r):
        return "web"
    # …y también cuando el operador NO nombra el sitio pero la tarea es una GESTIÓN que solo existe dentro de uno
    # (V2-119, 2026-08-18). `_WEB_RE` es una lista de sitios nombrados: sirve para «búscalo en Wallapop» y dejaba
    # fuera «resérvame mesa para 2 en Casa Lucio», que caía en `generic` — un worker sin el catálogo de sitios de
    # confianza y sin la ruta del navegador. El caso de uso `restaurant-tonight-madrid` lo midió: la corrida
    # terminó sin UN SOLO intento de reserva, con el modelo inventándose la política del restaurante.
    # Solo las categorías TRANSACCIONALES (reservar mesa/habitación/vuelo) promocionan: los clasificados de
    # segunda mano NO, porque comparten fraseo con una investigación y esa tiene su propio embudo desde
    # `generic`. El porqué completo, y la taxonomía, en `site_catalog.TRANSACTIONAL_CATEGORIES`.
    try:
        from nucleo.flash import site_catalog as _sc
        if _sc.category_of(r) in _sc.TRANSACTIONAL_CATEGORIES:
            return "web"
    except Exception:
        pass
    # …y cuando el operador SÍ nombra un sitio, pero uno que `_WEB_RE` no conoce (V2-126, 2026-08-18).
    #
    # Había DOS inventarios de sitios conocidos y llevaban tiempo desincronizados: `_WEB_RE` (aquí: wallapop,
    # amazon, linkedin, «abre la web»…) y `router_guards._KNOWN_SITES` (quince, los que el motor sabe abrir para
    # un login). DOCE estaban solo en el segundo — netflix, spotify, gmail, google, ebay, twitter, instagram,
    # facebook, outlook, github, idealista, milanuncios. Medido en el caso `cancel-subscription-before-charge`:
    # «Cancela mi suscripción a Netflix» → `generic`, o sea un worker SIN navegador. Y ese es el daño real, no la
    # falta de una cuenta de Netflix: sin navegador la tarea no puede llegar al muro de login, así que no puede
    # PEDIRLE al operador que entre ni decir «no puedo acceder a tu cuenta» — el sistema se queda sin la única
    # respuesta honesta que tenía, y el turno rellena el hueco narrando.
    #
    # Se exige NOMBRE DE SITIO + VERBO DE TAREA, nunca el verbo suelto: `looks_like_web_task` por sí solo es
    # ancho (`lee|mira|revis|compr`) y su propio docstring dice que existe como DISPARADOR, no como clasificador
    # — enrutar de más ya costó una vez dos tarjetas de navegador que nadie pidió (ver `_MODIFY_CODE_RE` arriba).
    # Música y mensajería quedan FUERA aunque nombren su sitio: esas cuentas se vinculan DENTRO de su widget
    # (OAuth/QR), nunca por el Chromium, y sus dos guards existen justo para sostener ese invariante.
    try:
        from nucleo.flash import router_guards as _rg
        _site = _rg.login_site(r)
        # V2-138: those two guards exist because CONNECTING one of those accounts happens inside its own widget
        # (OAuth/QR), never through the Chromium — a real invariant. But they were excluding the site for ANY
        # request, and ending a PAID commitment with that provider has nothing to do with linking it: «anula la
        # suscripción de Spotify» happens on spotify.com like any other cancellation. Measured: it classified as
        # `generic`, i.e. a worker with NO browser, so it could not even reach the login wall to tell the
        # operator what it needed. The carve-out is narrow on purpose — `ends_a_commitment` is False for «quita
        # la música de Spotify» and for «conecta mi Spotify».
        from nucleo import danger as _danger_cls
        _linking_guard = (_rg.is_music_service(_site, r) or _rg.is_messaging_service(_site, r))
        if _site and _rg.looks_like_web_task(r) and (not _linking_guard or _danger_cls.ends_a_commitment(r)):
            return "web"
    except Exception:
        pass
    # …y una gestión de DINERO o de COMPROMISO ocurre en una WEB, aunque el proveedor no esté en ninguna lista
    # (V2-148, 2026-08-19). Medido sobre las frases del propio caso: «paga la factura de la luz», «paga la
    # factura de Endesa», «paga la factura de la luz en la web de Endesa» — las tres a `generic`, o sea un
    # worker SIN navegador, incluso después de que el operador nombrara el proveedor y dijera dónde la paga.
    #
    # Lo había dejado abierto DOS veces (V2-141, V2-144) anotando que «el destino de un pago es la web del
    # proveedor CONCRETO, no un sitio de confianza común, así que no es la misma solución que una categoría del
    # catálogo». Era cierto y era la conclusión equivocada: no necesita entrada de catálogo NINGUNA, necesita
    # NAVEGADOR — el destino es el proveedor que nombre el operador, y encontrarlo es trabajo del worker.
    #
    # Va DESPUÉS de las ramas anteriores para no pisarlas (un sitio nombrado o una categoría transaccional ya
    # resolvieron), y el daño que repara no es «no paga» —imposible sin cuenta real, y el caso no lo penaliza—
    # sino que sin navegador la tarea no puede llegar al muro de login: el sistema pierde la única respuesta
    # honesta que tenía y el turno rellena el hueco narrando (el argumento de V2-126 para Netflix, otra vez).
    try:
        from nucleo.flash import router_guards as _rg_money
        if _rg_money.money_work_needs_a_browser(r):
            return "web"
    except Exception:
        pass
    # CÓDIGO de widget = CREAR (reusa la detección del router, verbo+nombre) o MODIFICAR-código, o architect.
    # NUNCA por mencionar «widget» a secas (V2-081): abrir/mostrar/gestionar uno existente NO es código.
    try:
        from nucleo.flash import router as _router
        _create = _router.looks_like_create_widget(r)
    except Exception:
        _create = False
    _modify_code = bool(_MODIFY_CODE_RE.search(r)) and not _DATA_NOT_CODE_RE.search(r)
    if _create or _modify_code or _ARCHITECT_RE.search(r):
        return "code"
    return "generic"


def default_label(kind: str, request: str = "") -> str:
    return {"web": "Buscando en la web…", "code": "Trabajando en un widget…",
            "memory": "Actualizando la memoria…", "research": "Investigando…"}.get(kind, "Pensando…")
