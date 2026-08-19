"""nucleo/flash/router_guards.py — deterministic backstop guards for the router (split out of router.py, V2-108
follow-up, 2026-08-17: an architecture audit found `router.py` mixing two unrelated concerns — the OpenAI-style
tool catalog/decode machinery, and this cluster of ~340 lines of pure regex classifiers that exist purely to
correct a small non-reasoning model's routing mistakes. Neither half references the other (verified before the
split); every external caller already imports the whole `router` module and calls e.g. `router.looks_like_close`,
so this file is re-exported from `router.py` and no call site anywhere in the repo needed to change.

Every function here is a pure, self-contained text classifier over normalized (accent-stripped) input — no shared
mutable state, no I/O. Each one exists because of a REAL observed routing mistake by the small model; the
docstrings/comments on each function keep that incident history, since it's what justifies the guard existing
at all (see [[feedback_no_hardcoded_understand]] in the workspace memory: these are grammar/pattern guards for
model mistakes, never a keyword table standing in for understanding)."""

# Verbos de TAREA (es/en, stems) que implican HACER algo en la web más allá de solo iniciar sesión. Deterministas
# (agnósticos del LLM): un login PURO ("conéctame a Wallapop", "inicia sesión en Gmail") no lleva ninguno; "entra
# en mi Gmail y BÓRRAME los correos" sí → es una TAREA. Sin acentos (se normaliza antes de comparar).
import re as _re

_TASK_VERB_RE = _re.compile(
    r"\b("
    r"borr|elimin|mand|envi|escrib|respond|contest|reenvi|gestion|revis|lee|leer|mira|mir[ae]|orden|compr|"
    r"public|descarg|reserv|anad|agreg|cambi|actualiz|sub[ae]|archiv|marca|mueve|rellen|apunt|"
    # `anul` junto a `cancel` (V2-138, 2026-08-19): son sinónimos exactos para esto y solo estaba uno, así que
    # «cancela la suscripción de Spotify» contaba como tarea web y «ANULA la suscripción de Spotify» no — la
    # misma orden, enrutada a un worker con navegador o sin él según qué verbo eligiera la persona.
    r"puj|pag|cancel|anul|confirm|solicit|vot|inscrib|contrat|licit|acept|rechaz|"
    # `de baja` / `suscrib` (V2-126, 2026-08-18): «date de baja de Netflix» es LA forma de pedir esto en
    # castellano y no llevaba ningún verbo de la lista, así que no contaba como tarea web. Va la locución
    # entera, nunca «baja» suelta — «estoy de baja» no es una orden a nadie.
    r"de\s+baja|suscrib|unsubscrib|"
    r"delete|remove|send|write|reply|forward|manage|check|read|buy|post|download|book|add|update|fill|move|"
    r"bid|pay|apply|vote|order|subscribe|purchase|checkout"
    r")", _re.I)


def _norm_txt(text: str) -> str:
    import unicodedata as _ud
    n = _ud.normalize("NFKD", text or "")
    return "".join(c for c in n if not _ud.combining(c)).lower()


def looks_like_web_task(text: str) -> bool:
    """True si el turno pide HACER una tarea en una web (no solo iniciar sesión). Determinista, agnóstico del LLM.
    Se usa para reclasificar una llamada errónea a `authenticate_web` (login) → escalada al navegador cuando en
    realidad hay una tarea ("entra en mi Gmail y BÓRRAME los correos")."""
    return bool(_TASK_VERB_RE.search(_norm_txt(text)))


# Intención de LOGIN PURO ("conéctame a Wallapop", "inicia sesión en mi Gmail", "vincula mi LinkedIn") — sin verbo
# de tarea después. Determinista. Espejo de `looks_like_web_task`: garantiza el routing de login aunque el modelo
# pequeño se despiste y no dispare la tool (jitter observado).
# NB (bug 2026-07-23): `conect(?!ad|or)` casaba CUALQUIER conjugación de "conectar" salvo "conectado"/"conector"
# — "¿tienes capacidad para conectarte al cluster?" (pregunta) o "el agente se conectaba ahí" (narración en 3ª
# persona) casaban igual y abrían un login de navegador que nadie pidió (a wallapop.com por el fallback de sitio
# desconocido, ver `nucleo.py::_start_web_auth`). Solo debe disparar la forma DIRIGIDA a zaelar en 1ª persona
# ("conéctame"/"conectarme"/"conecta mi cuenta"/"conecta a mi cuenta"), nunca una conjugación reflexiva/3ª persona
# ni una pregunta sobre capacidad. Mismo criterio para el inglés y para "vincula"/"vincular".
_LOGIN_INTENT_RE = _re.compile(
    r"\b(conectame|conectarme|conect(?:a|ar)\s+mi\b|conect(?:a|ar)\s+a\s+mi\b|"
    r"inicia(?:r)?\s*sesion|loguea(?:te)?|logue(?:ate)?|vincul[ae](?:me)?\s+mi\b|"
    r"accede a mi|entra en mi|log ?in|sign ?in|connect\s+(?:me|my)\b|autenti[cf])", _re.I)
# Sitios conocidos → dominio (para el fallback de producción que abre el login sin arg de la tool).
_KNOWN_SITES = {
    "wallapop": "wallapop.com", "gmail": "google.com", "google": "google.com", "linkedin": "linkedin.com",
    "amazon": "amazon.es", "ebay": "ebay.es", "twitter": "twitter.com", "instagram": "instagram.com",
    "facebook": "facebook.com", "outlook": "outlook.com", "github": "github.com", "idealista": "idealista.com",
    "milanuncios": "milanuncios.com", "netflix": "netflix.com", "spotify": "spotify.com",
}


def looks_like_login_request(text: str) -> bool:
    """True si el turno pide SOLO iniciar sesión/conectar una cuenta (sin tarea posterior) → authenticate_web."""
    return bool(_LOGIN_INTENT_RE.search(_norm_txt(text))) and not looks_like_web_task(text)


# Servicios de MÚSICA por streaming: se conectan desde el widget `musica` (OAuth in-app), NUNCA por login de
# navegador. "amazon music"/"apple music"/"youtube music" van con la palabra 'music' para NO pisar el marketplace
# Amazon ni el vídeo de YouTube (que sí son login de navegador / otra cosa).
_MUSIC_SERVICES = ("spotify", "apple music", "youtube music", "tidal", "deezer", "amazon music")
# Servicios de MENSAJERÍA que se VINCULAN DENTRO del widget `mensajeria` (WhatsApp/Telegram por QR, email por
# app-password), NUNCA por login de navegador. Incluye el email (V2-051): 'conéctame a Gmail/mi correo/Outlook' →
# el widget mensajeria (su tarjeta de conexión), no el Chromium.
_MESSAGING_SERVICES = ("whatsapp", "wasap", "telegram", "email", "e-mail", "correo", "gmail", "outlook", "hotmail",
                       "icloud", "imap")


_SHOW_VERB_RE = _re.compile(r"\b(muestra|muestrame|ensena|ensename|abre|abreme|abrir|mostrar|ensenar|ver|"
                            r"visualiza|saca|pon(?:me)? en pantalla)\b")
# match por STEM (sin \b final): 'anad' cubre añade/añadir, 'apunt' apunta/apuntar, etc. (tras _norm_txt sin acentos).
_CHANGE_VERB_RE = _re.compile(r"\b(anad|apunt|agreg|marca|quita|borr|elimin|cambi|aplaz|silenci|crea|edit|modific|"
                              r"met[ae]|programa|reserv|pon(?!(?:me|nos|te)?\s*en\s*pantalla)|añad)")


def is_pure_show_request(text: str) -> bool:
    """True si el turno es un ABRIR/MOSTRAR un widget PURO (sin intención de CAMBIAR datos). GUARD de ejecución
    de widget_data: un "abre/muéstrame el widget X" NUNCA debe ejecutar un data-op (el modelo a veces cuela una
    acción inventada 'unhide' o ALUCINA un add_meeting) → se redirige a mostrar la tarjeta. Determinista, es."""
    n = _norm_txt(text)
    return bool(_SHOW_VERB_RE.search(n)) and not _CHANGE_VERB_RE.search(n)


def is_music_service(site: str = "", text: str = "") -> bool:
    """True si el login pedido es un SERVICIO DE MÚSICA (Spotify…). GUARD DE EJECUCIÓN de authenticate_web: la
    música se conecta en el widget `musica` (su tarjeta), no por el navegador → garantiza el invariante AUNQUE el
    routing del modelo elija authenticate_web (patrón terco de 'conéctame a mi cuenta de Spotify')."""
    blob = f"{site} {text}".lower()
    return any(s in blob for s in _MUSIC_SERVICES)


_CLOSE_VERB_RE = _re.compile(r"\b(cierr\w*|cerr\w*|ocult\w*|escond\w*|apag\w*|quit\w*|close|hide|turn\s+off)\b")
_DELETE_VERB_RE = _re.compile(r"\b(borr|elimin|delete|remove|deshaz)\w*")
# negación del cierre: "no cierres / no lo cierres / don't close" — no debe contar como close (evita cerrar al revés)
_NO_CLOSE_RE = _re.compile(r"\bno\s+(?:me\s+|lo\s+|la\s+|los\s+|las\s+)?(?:cierr\w*|ocult\w*|escond\w*)\b|\bdon'?t\s+close\b")


def looks_like_close(text: str) -> bool:
    """True si el turno pide CERRAR (ocultar) un widget, NO borrarlo. GUARD DE EJECUCIÓN de delete_widget (V2-045,
    invariante V2-017 'cerrar ≠ borrar'): el no-razonador a veces elige delete_widget para 'cierra el widget de X';
    borrar es PARA SIEMPRE y cerrar es reversible → si hay verbo de cerrar y NINGÚN verbo de borrar, es un close.
    Determinista, sin acentos (se normaliza). Ignora la NEGACIÓN ('no cierres')."""
    n = _norm_txt(text)
    return (bool(_CLOSE_VERB_RE.search(n)) and not _DELETE_VERB_RE.search(n)
            and not _NO_CLOSE_RE.search(n))


# GUARD de ejecución de show_widget (2026-07-17): CREAR un widget NUEVO se ESCALA al generador (código), NO se
# "muestra". Tras añadir la tool show_widget, el no-razonador la elegía para 'créame un widget de X' y `identify`
# devolvía un widget EXISTENTE equivocado (fuzzy laxo: 'conversor de divisas'→'results'). Backstop determinista
# (misma clase que looks_like_close/stop): verbo de CREAR + 'widget', o 'widget NUEVO' → es un CREATE, no un show.
# SINÓNIMOS de "widget" que usa el operador de forma natural (mar de testing 2026-07-21: "créame un PANEL/GADGET"
# no se detectaba → el backstop de promesa no escalaba). Gated SIEMPRE por un verbo de crear → seguro (no captura
# "el panel de control del coche"). "tarjeta/cuadro/contador" van con verbo de crear delante.
_WIDGET_SYN = r"(?:widget|panel|gadget|tablero|contador|cuadro de mando|mini[- ]?app|tarjeta)"
_CREATE_WIDGET_RE = _re.compile(
    r"(\b(cre[ae]\w*|cr[eé][aá]me\w*|haz\w*|h[aá]zme\w*|hac[eé]\w*|hacer|hag\w*|gener\w*|mont\w*|dise[nñ]\w*|"
    r"constru\w*|prepar\w*|program\w*|make|build|create)\b[^.!?]{0,45}\b" + _WIDGET_SYN + r"\b)"
    r"|(\b" + _WIDGET_SYN + r"\b[^.!?]{0,25}\bnuev[oa]\b)|(\bnuev[oa]\b[^.!?]{0,12}\b" + _WIDGET_SYN + r"\b)", _re.I)


# UN WIDGET NOMBRADO COMO DESTINO NO ES UN WIDGET QUE HAYA QUE PROGRAMAR (2026-08-13).
#
# Incidente que lo motiva: una investigación de viaje (ferry + hotel + restaurante) acabó en el GENERADOR DE
# WIDGETS, que se puso a escribir código de un widget nuevo llamado `prepara-ricart-viaje` en vez de buscar nada.
# Causa única: la última frase de la escalada era «Entrega el resultado MONTADO en el widget results…». `mont\w*`
# es verbo de crear y `widget` estaba a nueve caracteres → CREATE. O sea que **pedir que el resultado se entregue
# en la hoja de resultados desviaba la tarea al generador**, y la hoja de resultados es JUSTO la superficie de
# entrega de toda investigación: el fallo estaba en el camino más transitado del producto.
#
# La distinción no es una lista de excepciones ([[feedback_no_hardcoded_understand]]) sino GRAMÁTICA: cuando el
# widget va detrás de una preposición de destino («en el widget», «al panel», «dentro de la tarjeta», «into the
# widget»), es el SITIO DONDE VA el resultado, no la cosa que se construye. El verbo que aparezca antes describe
# qué se pone ahí. Se neutralizan esas menciones ANTES de buscar el patrón de crear, así una frase que traiga las
# DOS cosas («créame un panel y entrégalo en el widget results») sigue detectando el create de verdad.
# OJO con la preposición castellana «a» SUELTA: colisiona con el artículo INGLÉS «a» y neutralizaba
# «build me A WIDGET that tracks my steps», que es un create de libro. Se queda `al` (la contracción que es la que
# de verdad aparece: «al widget»); «a el widget» no es castellano.
#
# EL ARTÍCULO INDETERMINADO ERA EL AGUJERO (2026-08-18, mismo incidente una vez más). La lista de artículos solo
# llevaba los DETERMINADOS, así que «monta el resultado en UN widget del canvas» —que es la forma NATURAL de decir
# «ponlo en una tarjeta», y la que el propio FlashBrain escribió al reformular la escalada— no se neutralizaba y
# volvía a caer en el generador. La gramática no cambia con el artículo: «en un widget» sigue siendo el SITIO donde
# va el resultado. Un create de verdad no lleva preposición de destino delante («créame un widget», «build me a
# widget»), así que ampliar la lista no le quita nada al lado create.
# ÚNICA excepción, y es real: «en un widget NUEVO» sí pide uno nuevo — ahí la preposición de destino y el create
# coexisten, y manda el create. Se deja fuera de la neutralización con un lookahead para que
# `_CREATE_WIDGET_RE` siga viendo su patrón `SYN … nuevo`.
_WIDGET_DEST_RE = _re.compile(
    r"\b(?:en|al|sobre|dentro\s+de|dentro\s+del|hacia)\s+"
    r"(?:el\s+|la\s+|los\s+|las\s+|un\s+|una\s+|unos\s+|unas\s+)?" + _WIDGET_SYN + r"\b(?!\s+nuev[oa]\b)"
    r"|\b(?:into|in|on)\s+(?:the\s+|a\s+|an\s+)?" + _WIDGET_SYN + r"\b(?!\s+nuev[oa]\b)", _re.I)


def looks_like_create_widget(text: str) -> bool:
    """True si el turno pide CREAR/GENERAR un widget NUEVO (→ escalate al generador), no mostrar uno existente ni
    ENTREGAR algo dentro de uno. GUARD de ejecución de show_widget: si el modelo elige show_widget para un CREATE,
    se redirige a escalar."""
    t = _WIDGET_DEST_RE.sub(" <destino> ", _norm_txt(text))
    return bool(_CREATE_WIDGET_RE.search(t))


# PROMESA SIN ACCIÓN (2026-07-19, mar de testing): el no-razonador, ante fraseo CORTÉS/indirecto/subjuntivo
# ('¿podrías…?', 'deberías…', 'sería genial que…', 'me haría falta…'), CHARLA una promesa ('voy a…', 'aquí lo
# tienes', 'me pongo con ello', 'ahora te lo abro') SIN llamar a la tool. Es la causa nº1 de "dice que lo hace y no
# lo hace" y NO se arregla parcheando verbo a verbo (cada conjugación es un caso). Backstop UNIFICADO gated por la
# promesa en la RESPUESTA de zaelar (se comprometió) → re-deriva la intención con los clasificadores deterministas.
_PROMISE_RE = _re.compile(
    r"\b(voy a|te lo|te la|te los|te las|aqui (?:lo|la|los|las) tienes|aqui tienes|ahora (?:mismo|te|lo|la)|"
    r"me pongo con|me pongo a|lo hago|la hago|enseguida|en un momento|un momento|dame un momento|lo abro|"
    # V2-132 — medido sobre el transcript de `find-theatre-tickets`: «Me pongo a buscarte las dos entradas»
    # y «Todavía estoy con ello» daban False, así que el backstop de promesa ni se planteaba. Son las formas
    # MÁS llanas de decir «estoy en ello», y son justo las que salen cuando no hay ninguna tarea detrás.
    r"estoy con ello|sigo con ello|sigo buscando|sigo con la busqueda|estoy en ello|"
    r"te aviso en cuanto|te lo confirmo en cuanto|en cuanto (?:lo|la) tenga|"
    # 1ª persona de acción con o SIN clítico: «te muestro el reloj» / «te abro X» / «te enseño X» / «te saco X»
    # (bug mar 2026-07-21: el gate exigía «te LO muestro» → se colaba «te muestro el reloj» y el show no se re-derivaba).
    r"te (?:(?:lo|la|los|las) )?(?:abr|muestr|ense[nñ]|ensen|sac)\w*|"
    r"voy a (?:abrir|mostrar|crear|poner|buscar)|"
    r"estoy (?:abriendo|creando|poniendo|buscando))\b")
# promesa de MÚSICA en la respuesta ('voy a poner algo de rock', 'te pongo música') → el backstop la reproduce
_PROMISE_MUSIC_RE = _re.compile(r"\b(poner|pongo|pondre|reproduc\w*)\b[^.!?]{0,20}\b(m[uú]sica|canci|rock|jazz|algo de)\b|"
                                r"\b(m[uú]sica|canci|rock|jazz)\b[^.!?]{0,15}\b(ahora|para ti|un momento)\b")


def promises_music(reply: str) -> bool:
    return bool(_PROMISE_MUSIC_RE.search(_norm_txt(reply)))
# verbos de SHOW ESTRICTOS para el backstop de promesa: SOLO inequívocos (sin 'pon'/'sube'/'ver' → colisionan con
# 'pon música'/'va a poner el tiempo'/'a ver si…'). Cubre 'abrir/mostrar/enseñar/sacar' en cualquier conjugación.
_SHOW_STRICT_RE = _re.compile(r"\b(abr\w*|muestr\w*|ensen\w*|ense[nñ]\w*|saca\w*)\b")


def promises_action(reply: str) -> bool:
    """True si la RESPUESTA de zaelar promete una acción en 1ª persona (se comprometió a hacer algo)."""
    return bool(_PROMISE_RE.search(_norm_txt(reply)))


def looks_like_show_strict(text: str) -> bool:
    """Verbo de SHOW inequívoco (abrir/mostrar/enseñar/sacar), NO crear, NO cerrar — para el backstop de promesa."""
    n = _norm_txt(text)
    return (bool(_SHOW_STRICT_RE.search(n)) and not looks_like_create_widget(text)
            and not looks_like_close(text))


# TAREA que EXIGE navegador/worker (marketplace real o informe/investigación a fondo). SOLO para el backstop de
# promesa (mar 2026-07-21: «voy a buscar el sofá en Milanuncios» / «te preparo el informe» se quedaban en chat).
# Gated por la promesa en la respuesta → seguro. Nombres de sitio = señal fuerte de NAVEGAR (no web_search puntual).
_MARKETPLACE_RE = _re.compile(
    r"\b(idealista|coches\.?net|autoscout|wallapop|milanuncios|fotocasa|vibbo|amazon|ebay|"
    r"segundamano|habitaclia|pisos\.com)\b", _re.I)
_REPORT_RE = _re.compile(r"\b(informe|estudio|comparativa|investig\w*)\b[^.!?]{0,40}\b(a fondo|compar\w*|detallad\w*|"
                         r"mejor\w*|opcion\w*)\b|\b(compar\w*|investig\w*)\b[^.!?]{0,30}\b(a fondo|entre|los|las)\b", _re.I)


def looks_like_escalate_task(text: str) -> bool:
    """True si el TEXTO describe una gestión que exige worker/navegador (marketplace nombrado, informe/investigación
    a fondo, o una categoría TRANSACCIONAL del catálogo de sitios). Úsalo SOLO tras confirmar una promesa en la
    respuesta (gate del backstop) — no como router primario.

    V2-132: la tercera rama no es una lista de verbos nueva sino la MISMA fuente que ya decide el `kind` de la
    tarea en `dispatch._classify_kind` (`site_catalog.TRANSACTIONAL_CATEGORIES`). Reservar una mesa, una noche
    de hotel, un vuelo o conseguir entradas exige entrar en un sitio real; que este guard no lo supiera y el
    clasificador de `kind` sí es exactamente cómo dos piezas que deciden lo mismo acaban discrepando."""
    n = _norm_txt(text)
    if _MARKETPLACE_RE.search(n) or _REPORT_RE.search(n):
        return True
    try:
        from nucleo.flash import site_catalog as _sc
        return (_sc.category_of(text) or "") in _sc.TRANSACTIONAL_CATEGORIES
    except Exception:
        return False


# HANDING THE LOOKUP BACK (V2-142). Measured on `reorder-prescription__es`: the operator wrote «¿puedes buscar
# tú el teléfono de esa, por favor? Para eso te pido ayuda» and got «la forma más rápida es que busques
# "farmacia Plaza de Chamberí" en Google Maps y me pasas el teléfono». That is the whole job handed back, on a
# turn where zaelar has `web_search` and a browser.
#
# The distinction that makes this SAFE, and it is the whole design: telling the operator to look in HIS OWN
# private things — his inbox, his contract, the paper receipt in a drawer — is CORRECT behaviour when zaelar has
# no connector for it, and `pay-known-bill` earns points for exactly that («abre tu correo, busca la factura de
# la luz y dime cuál es»). What is never acceptable is sending him to look up PUBLIC information he asked US to
# find. So the pattern requires a public destination (Google, Maps, internet, a search engine), never a private
# one — the same reason the rest of this module pairs a verb with its object instead of trusting the verb alone.
_PUBLIC_LOOKUP_RE = _re.compile(
    r"\b(google|maps|internet|la red|un buscador|el buscador|paginas amarillas|paginas blancas|"
    r"yelp|tripadvisor)\b", _re.I)
_LOOKUP_VERB_RE = _re.compile(
    r"\b(busca\w*|buscar\w*|busques|busque|mira\w*|mires|consulta\w*|consultes|"
    r"look\s+(?:it\s+)?up|search\w*|check)\b", _re.I)
# zaelar SAYING IT IS DOING IT is the opposite of handing it back, and the same words appear in both. First
# person (and the past tense of having already looked) is what tells them apart.
_FIRST_PERSON_LOOKUP_RE = _re.compile(
    r"\b(busco|buscare|he buscado|estoy buscando|voy a buscar|miro|mirare|he mirado|estoy mirando|"
    r"voy a mirar|consulto|he consultado|te paso|te traigo|te digo|"
    r"i(?:'| a)?m (?:looking|searching)|i (?:will |'ll )?(?:look|search|check)|i (?:looked|searched|checked))\b",
    _re.I)


def hands_public_lookup_back(reply: str) -> bool:
    """True when zaelar's own reply sends the operator off to look up PUBLIC information himself.

    Deliberately NOT true for his private material (inbox, contract, the paper bill in a drawer): there, asking
    him is the correct move — zaelar genuinely has no connector — and `pay-known-bill__es` scores it as such
    («abre tu correo, busca la factura de la luz y dime cuál es»). The line is the DESTINATION, not the verb.

    Nor is it true when zaelar says it is doing the looking itself: «busco yo el teléfono», «he mirado en Google
    Maps y la más cercana es esta». Same words, opposite meaning, told apart by the person of the verb.
    """
    n = _norm_txt(reply)
    if not _PUBLIC_LOOKUP_RE.search(n) or not _LOOKUP_VERB_RE.search(n):
        return False
    return not _FIRST_PERSON_LOOKUP_RE.search(n)


# PROMESA DE UN AVISO CON FECHA (V2-146). «apúntame que el jueves… y recuérdamelo el miércoles» acabó con
# `scheduled_jobs.created` VACÍO: el modelo prometió en prosa —«te avisaré el miércoles»— y no emitió ninguna
# tag. El ejecutor de crons funciona (V2-134) y el prompt lo pide con todas las letras; faltaba el backstop.
#
# La frontera que lo separa de la familia de V2-132/V2-143: «te aviso EN CUANTO lo tenga» es un worker
# terminando, no un aviso programado. Lo que distingue a este es que hay un MOMENTO resoluble — y quien decide
# si lo hay es `scheduler.parse_when`, que devuelve "" ante cualquier expresión que no sea inequívoca.
#
# V2-151: the first shape of this pattern spelled out the ARTICLE («program\\w* el recordatorio») and the run it
# was written for said «te programo UN recordatorio» — one word away, and the backstop never fired, so the turn
# promised an alert with `scheduled_jobs.created` empty all over again. Measured on seven natural phrasings of
# the same promise, five missed. A promise is a VERB plus a reminder NOUN; the determiner in between is noise.
# It is listed explicitly instead of `\\w+` so that a NEGATED promise («no te pongo ningún recordatorio») cannot
# match and schedule the very thing the sentence declined to schedule.
_REMIND_NOUN = r"(?:recordatorio|aviso|alarma|alerta)"
_REMIND_DET = r"(?:un|una|el|la|tu|ese|este|esa|esta)\s+"
_REMIND_VERB_RE = _re.compile(
    r"\b(te\s+aviso|te\s+avisare|te\s+lo\s+recuerdo|te\s+lo\s+recordare|te\s+recuerdo|te\s+recordare|"
    r"dejo\s+puesto\s+" + _REMIND_DET + _REMIND_NOUN + r"|"
    r"dejo\s+programad[oa]\s+" + _REMIND_DET + _REMIND_NOUN + r"|"
    r"(?:program|pon|cre|configur|activ|dej)\w*\s+" + _REMIND_DET + _REMIND_NOUN + r"|"
    r"i'?ll\s+remind\s+you|i\s+will\s+remind\s+you|i'?ll\s+let\s+you\s+know\s+on|"
    r"i'?ll\s+set\s+(?:up\s+)?(?:a|the)\s+reminder|i'?ll\s+put\s+(?:a|the)\s+reminder)\b", _re.I)


def promises_a_dated_reminder(reply: str, operator_text: str = "") -> str:
    """The reply promises to remind the operator AT A GIVEN TIME → the schedule spec for it, else "".

    Returns the spec rather than a bool so the caller cannot promise what it could not resolve: if the moment is
    not unambiguous the answer is "", and nothing gets scheduled on a guessed date.
    """
    n = _norm_txt(reply)
    m = _REMIND_VERB_RE.search(n)
    if not m:
        return ""
    try:
        from nucleo import scheduler as _sched
    except Exception:
        return ""
    # The reminder day is the one that follows the promise. Both halves of this exchange name TWO weekdays
    # («el JUEVES renuevas el seguro… te avisaré el MIÉRCOLES»), and `parse_when` refuses an ambiguous pair on
    # purpose — but here the position disambiguates it: what comes after «te avisaré» is when the notice goes.
    # Only if that tail resolves nothing do we look at what the operator said, and there ambiguity stands.
    return _sched.parse_when(n[m.end():]) or _sched.parse_when(operator_text)


# APUNTE CON FECHA (V2-159). Hermano del backstop del aviso, para la OTRA mitad del mismo encargo. El prompt lo
# pide con todas las letras —«si el compromiso tiene fecha, además apúntalo en su agenda… son dos cosas
# distintas, el apunte y el aviso, y el operador pide las dos»— y la corrida salió con el cron puesto y NINGUNA
# cita: «Te apunto la renovación del seguro del coche para el jueves» sin una sola data-op detrás.
_NOTE_VERB_RE = _re.compile(
    r"\b(te\s+(?:lo\s+|la\s+)?apunto|apunto|te\s+(?:lo\s+|la\s+)?anoto|anoto|"
    r"queda\s+(?:apuntad|anotad)[oa]|lo\s+apunto|lo\s+anoto|"
    r"(?:anado|pongo|meto)\w*\s+(?:a|en)\s+tu\s+agenda|i'?ll\s+note\s+(?:it|that)\s+down)\b", _re.I)
# Dónde EMPIEZA la fecha dentro de la frase — sirve para dos cosas: recortar el título antes de ella y no
# arrastrarla dentro del texto de la cita.
_DATE_LEAD_RE = _re.compile(
    r"\s*,?\s*\b(?:para\s+el|para|este|esta|el|on|the)?\s*\b("
    r"lunes|martes|miercoles|jueves|viernes|sabado|domingo|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"manana|tomorrow|dia\s+\d{1,2})\b", _re.I)


def dated_note_backstop(reply: str, operator_text: str = "") -> dict | None:
    """The reply promises to WRITE DOWN a dated commitment → the `add_meeting` payload for it, else None.

    V2-159, measured: the reminder half now works (one cron, right Wednesday, right prompt — V2-151/V2-153) and
    the run still failed because the OTHER half never happened. The case demands both: the commitment REGISTERED
    and the notice scheduled. zaelar said «Te apunto la renovación del seguro del coche para el jueves» and the
    mechanism showed no agenda data-op at all.

    Two details this shares with its sibling, and one it does not:
      · the moment is resolved by `scheduler.parse_when`, so an expression that is not unambiguous schedules
        nothing — a note on a guessed day is the same class of harm as an alert on one;
      · the tail is CUT at the reminder promise before resolving. One sentence carries BOTH days («…para el
        JUEVES y te programo un recordatorio para el MIÉRCOLES») and `parse_when` refuses a pair on purpose;
        position is what tells them apart, exactly as in `promises_a_dated_reminder`.
      · unlike the alert, the title matters: an agenda entry saying «el jueves» is not an entry. It comes from
        the words between the promise verb and the date, falling back to the operator's own request.
    """
    n = _norm_txt(reply)
    m = _NOTE_VERB_RE.search(n)
    if not m:
        return None
    tail = n[m.end():]
    cut = _REMIND_VERB_RE.search(tail)
    if cut:
        tail = tail[:cut.start()]
    try:
        from nucleo import scheduler as _sched
    except Exception:
        return None
    when = _sched.parse_when(tail)
    if not when:
        return None
    lead = _DATE_LEAD_RE.search(tail)
    title = (tail[:lead.start()] if lead else tail).strip(" ,.;:")
    if len(title) < 4:
        title = (operator_text or "").strip()[:120]
    return {"title": title[:120], "date": when.split(" ")[0]} if title else None


_CLAUSE_SPLIT_RE = _re.compile(r"[,;.!?\n]|\sy\s|\sand\s", _re.I)


def create_widget_request(text: str) -> str:
    """Just the CLAUSE of `text` that asks to build a widget, or "" if none does.

    V2-155, measured on `three-tasks-at-once`: the backstop that adds a missing widget task appended the WHOLE
    turn, and a turn that asks for three things carries the other two inside it. That mattered because the
    request then went through `dispatch.find_duplicate`, whose STRONGEST signal is «same destination widget»:

        _target_widget("…un informe sobre coches eléctricos… y móntame un widget de un juego…") -> 'results'
        _target_widget("Elaborar un informe detallado sobre coches eléctricos para ciudad…")     -> 'results'
        find_duplicate(whole turn, "code")  -> the REPORT's session       ← the game is swallowed
        find_duplicate(just the game, "code") -> None                     ← it would have been created

    So the third task was not lost by the model failing to ask for it: it was correctly detected, appended as a
    sentence that says «informe» in it, and deduplicated against the report it was supposed to run alongside.

    Splitting on clause separators and reusing `looks_like_create_widget` keeps this free of a second vocabulary
    — the predicate that decides WHETHER a turn asks for a widget is the same one that decides WHICH part does.
    Falls back to the whole text when no single clause matches but the text as a whole does, so a plain «móntame
    un widget de X» (no separators) behaves exactly as before.
    """
    text = (text or "").strip()
    if not text or not looks_like_create_widget(text):
        return ""
    for part in (p.strip(" ,;.!?") for p in _CLAUSE_SPLIT_RE.split(text)):
        if part and looks_like_create_widget(part):
            return part
    return text


def dated_reminder_backstop(reply: str, operator_text: str = "") -> dict | None:
    """The whole backstop decision in ONE place: what to schedule when the model promised a notice in prose.

    Both channels — `nucleo/flash/probe.py` and the voice provider — carried their own copy of this (resolve the
    moment, then build the tag), and V2-153 is what a divergence of that shape costs: the run scheduled the
    reminder TWICE, once per turn that promised it, because neither copy looked at what was already scheduled.
    Measured against the real scheduler, two `create()` calls with the same spec both return ok and leave two
    live jobs; nothing downstream deduplicates them.

    Returns the tag payload, or None when there is nothing to add — either no resolvable moment, or that moment
    is already covered. Skipping on an existing job at the same instant is the conservative side on purpose: a
    backstop exists for the turn the model forgot, and a second alert for something the operator asked once is a
    defect he SEES, while the model's own `cron.create` tag is not gated by this and can still schedule freely.
    """
    when = promises_a_dated_reminder(reply, operator_text)
    if not when:
        return None
    try:
        from nucleo import scheduler as _sched
        for job in _sched.list_jobs(active_only=True):
            if str(job.get("schedule") or "").strip() == when:
                return None
    except Exception:
        pass          # cannot read the schedule → still better to back the promise than to drop it
    return {"schedule": when, "prompt": (operator_text or "")[:200], "name": "aviso"}


def escalate_goal_from_window(window, current_text: str = "", max_back: int = 6) -> str:
    """The operator's request that a promise refers to, which is NOT always in this turn's text.

    V2-132, measured on `find-theatre-tickets__es`: the task was described across TWO turns — «consígueme dos
    entradas para el musical de El Rey León» and then, after zaelar correctly asked for the missing data,
    «este sábado, la sesión de tarde». zaelar answered the second one with «dame un momento que lo miro» and
    called no tool at all. The promise backstop looked only at THIS turn's text, which on its own describes no
    task, so it could not fire — and the run became eight turns of narrating a search that never started.

    Returns the goal to escalate (this turn's text appended, since it carries the detail that completes it), or
    "" if nothing in the window describes a task that needs a worker. Same lookback shape as the window the
    brain already sees; the caller still gates on "no tool fired AND nothing is running".
    """
    if current_text and _needs_real_work(current_text):
        return current_text
    # V2-147: `max_back` counts the operator's OWN turns, not window ENTRIES. It used to slice the raw window,
    # so every exchange cost two of the budget and three «¿alguna novedad?» were enough to push the request out
    # of reach. Measured on the run: the task was named in the first turn, `_needs_real_work` recognised it, and
    # the lookback simply could not see that far — the promise «dame un momento que lo miro» came back with no
    # goal and nothing escalated. Counting assistant turns against a budget meant for the operator's history
    # punishes a conversation for the very thing that makes it normal: asking how it is going.
    seen = 0
    for msg in reversed(list(window or [])):
        if (msg or {}).get("role") != "user":
            continue
        seen += 1
        if seen > max_back:
            break
        content = str((msg or {}).get("content") or "").strip()
        if content and _needs_real_work(content):
            return f"{content} — {current_text}".strip(" —") if current_text else content
    return ""


_SCREEN_TARGET_RE = _re.compile(r"\b(en pantalla|la pantalla|en el canvas|el widget|widget)\b", _re.I)


_DATA_OP_RE = _re.compile(r"\b(de\s+(?:la\s+|mi\s+)?agenda|del\s+calendario|de\s+la\s+lista|"
                          r"de\s+(?:la\s+|mis\s+)?tareas|from\s+(?:the\s+)?(?:agenda|calendar|list))\b", _re.I)


def money_work_needs_a_browser(text: str) -> bool:
    """A money / commitment errand that has to happen on a WEBSITE, so the worker must get a browser.

    V2-148 — every payment classified `generic`, measured on the case's own sentences: «paga la factura de la
    luz», «paga la factura de Endesa», «paga la factura de la luz en la web de Endesa» — all of them a worker
    with NO browser, even after the operator named the provider and said where he pays it.

    I had left this open TWICE (V2-141, V2-144) with the note «the destination of a payment is the provider's
    specific site, not a common trusted one, so it is not the same solution as a catalog category». That was
    right and it was also the wrong conclusion: it does not need a catalog entry AT ALL, it needs a BROWSER —
    the destination is whatever provider the operator names, and finding it is the worker's job.

    And the damage is not «it does not pay» (impossible without a real account, and the case does not penalise
    it): without a browser the task cannot reach the login wall, so the system loses the only honest answer it
    had — «llego al login de Endesa y necesito que entres tú» — and the turn fills the gap by narrating. That
    is literally the argument V2-126 wrote down for Netflix and V2-138 repeated for the rest of the providers.

    Carve-outs are the ones that already resolve inside the turn, plus a data-op on the operator's own lists:
    «borra la factura de la agenda» carries a money word and is a widget mutation, not an errand.
    """
    if not _needs_real_work(text):
        return False
    try:
        from nucleo import danger as _danger
        if not (_danger.moves_money(text) or _danger.ends_a_commitment(text)):
            return False           # a marketplace/report errand routes by its own branch, not through here
    except Exception:
        return False
    return not _DATA_OP_RE.search(_norm_txt(text))


def _needs_real_work(text: str) -> bool:
    """Does this request need a worker, i.e. something happening OUTSIDE the conversation?

    V2-143 — `renew-gym-membership__es` measured the gap: «Renueva mi cuota del gimnasio de este mes» is not a
    marketplace, not a report and not a transactional category of the site catalog, so `looks_like_escalate_task`
    said no. Then the operator gave the missing datum, zaelar said «ahora me pongo con ello — busco los gimnasios
    de Sevilla», and NOTHING fired: 0 searches, 0 browser tasks. The signal that would have caught it was already
    in the tree and unused — `danger.moves_money` returns True for that exact sentence.

    SPENDING MONEY is real-world work by definition: no membership was ever renewed by talking. Show/close are
    excluded because they are resolved in the turn itself (V2-017) and «pon la factura en pantalla» would
    otherwise look like a money task.
    """
    if looks_like_escalate_task(text):
        return True
    try:
        from nucleo import danger as _danger
        # V2-138: ending a standing commitment is real-world work too, and it costs nothing — «cancela mi
        # suscripción a Netflix» is not money, so `moves_money` said no and the promise backstop could not fire
        # for the whole cancel family. `is_dangerous` would be too wide (it is also True for «borra el widget
        # de música», resolved inside the turn); `ends_a_commitment` is exactly the right width, measured on
        # both classes.
        if not (_danger.moves_money(text) or _danger.ends_a_commitment(text)):
            return False
    except Exception:
        return False
    # …and neither is putting something ON THE SCREEN. «pon la factura en pantalla» carries a money word and no
    # show VERB (`pon` is deliberately out of that list — it collides with «pon música»), so the screen has to
    # be named explicitly here.
    if _SCREEN_TARGET_RE.search(_norm_txt(text)):
        return False
    return not (is_pure_show_request(text) or looks_like_close(text) or looks_like_create_widget(text))


# verbos de BÚSQUEDA/NAVEGACIÓN para el guard de marketplace (busca/mira/enséñame/encuentra/ver/ojea). Un sitio
# de compraventa NOMBRADO + uno de estos = ENTRAR y navegar el catálogo (no un dato puntual, no un "no puedo").
_MKT_VERB_RE = _re.compile(
    r"\b(busc\w*|b[uú]scame|mir[ae]\w*|ense[nñ]\w*|ens[eé][nñ]\w*|muestr\w*|encuentr\w*|encu[eé]ntr\w*|"
    r"ojea\w*|vistazo|quiero ver|ver si|encontrar)\b", _re.I)


def looks_like_marketplace_nav(text: str) -> bool:
    """True si el turno pide NAVEGAR un marketplace nombrado (sitio + verbo de buscar/ver). Guard determinista de
    alta precisión: no dispara con una mención de pasada ('me encanta comprar en Amazon') — exige intención de
    búsqueda. → escala al navegador aunque el modelo hubiera elegido web_search / chat / show."""
    n = _norm_txt(text)
    return bool(_MARKETPLACE_RE.search(n) and _MKT_VERB_RE.search(n))


# MODIFICAR el CÓDIGO/aspecto de un widget = trabajo del generador (escala), NO una data-op ni un "no puedo".
# Modo de fallo FIABLE del no-razonador (mar 2026-07-21, modify 1-7/8 según tirada: declina, hace widget_data, o
# muestra). Guard determinista de alta precisión: verbo de cambiar + propiedad de CÓDIGO/estilo/estructura + la
# palabra widget (o sinónimo). No captura una data-op de VALOR (marcar hecho, cambiar un título/dato) — solo
# color/fondo/estilo/diseño/columna/campo/sección/botón/tamaño… que son CÓDIGO.
_MODIFY_VERB_RE = _re.compile(
    r"\b(cambi\w*|modific\w*|edit\w*|a[nñ]ad\w*|agreg\w*|incorpor\w*|met\w*|pon\w*|p[oó]n\w*|quit\w*|"
    r"actualiz\w*|redise[nñ]\w*|reestructur\w*|reorganiz\w*)\b", _re.I)
_CODE_PROP_RE = _re.compile(
    r"\b(color\w*|fondo|estilo\w*|dise[nñ]o|apariencia|columna\w*|campo\w*|secci[oó]n\w*|tama[nñ]o|"
    r"bot[oó]n\w*|layout|formato|encabezad\w*|fuente|tipograf\w*|borde\w*|margen\w*|tema)\b", _re.I)
_WIDGET_SYN_RE = _re.compile(r"\b" + _WIDGET_SYN + r"\b", _re.I)


def looks_like_modify_widget(text: str) -> bool:
    """True si el turno pide CAMBIAR el CÓDIGO/aspecto de un widget (color/columna/estilo… + 'widget') → escala al
    generador. No es una data-op (marcar/mover un item) ni un 'no puedo'. Guard determinista de alta precisión."""
    n = _norm_txt(text)
    return bool(_MODIFY_VERB_RE.search(n) and _CODE_PROP_RE.search(n) and _WIDGET_SYN_RE.search(n)
                and not looks_like_create_widget(text))


_RULE_REMOVAL_RE = _re.compile(
    r"\b(olvida|olvidate|quita|elimina|borra|anula|retira|deja de aplicar|ya no (?:hace falta|quiero|apliques))\b")


def looks_like_rule_removal(text: str) -> bool:
    """True si el turno pide QUITAR una user rule ('olvida esa regla', 'ya no hace falta que seas tan breve') en
    vez de añadir una. GUARD del handler de set_style_directive (V2-046 A1): la MISMA tool añade o retira; el
    sentido lo decide este guard sobre el texto del turno, determinista, no el LLM."""
    n = _norm_txt(text)
    return bool(_RULE_REMOVAL_RE.search(n))


# Referencia de item VACÍA o un PRONOMBRE DEÍCTICO SUELTO ("lo", "eso", "esto", "it", "that"…) — sin sustantivo que la
# ancle. En una data-op de widget significa que el modelo NO sabe a qué item apunta: el antecedente ("cancélalo") vive
# en la CONVERSACIÓN, no en el widget. Reconocimiento GRAMATICAL de pronombre, NO una tabla de verbos de routing.
_BARE_REF_RE = _re.compile(
    r"^(?:lo|la|le|los|las|les|eso|esto|esa|ese|esas|esos|aquello|aquella|aquel|aquellos|aquellas|"
    r"esta|este|estas|estos|it|that|this|them|those|these)$")


def looks_like_bare_ref(ref: str) -> bool:
    """True si la referencia a item es VACÍA o un pronombre deíctico suelto (sin sustantivo). En una data-op indica
    que el modelo no ancló el item — su antecedente está en la conversación reciente, no en el widget. GUARD del
    handler de widget_data (2026-07-21, caso «hay que cancelarlo» tras «¿qué día tengo la ITV?»)."""
    n = (ref or "").strip().lower().strip("¿?¡!.,;:")
    return not n or bool(_BARE_REF_RE.match(n))


def is_messaging_service(site: str = "", text: str = "") -> bool:
    """True si el 'login' pedido es WhatsApp/Telegram. GUARD DE EJECUCIÓN de authenticate_web (espejo de
    is_music_service): esas cuentas se VINCULAN por QR DENTRO del widget `mensajeria`, NO por login de navegador →
    'conéctame a WhatsApp' / 'abre WhatsApp' se redirige a [[show:mensajeria]] (donde está el QR), no al Chromium."""
    blob = f"{site} {text}".lower()
    # 'youtube music'/'amazon music' ya los captura is_music_service; aquí solo mensajería pura.
    return any(s in blob for s in _MESSAGING_SERVICES)


# Backstop DETERMINISTA de PARAR un worker (§v3·M). Exige un verbo de parada Y una referencia a TRABAJO (proceso/
# widget/búsqueda/tarea/creación/"eso"/"todo"). Se usa solo cuando HAY workers vivos.
# Historia de endurecimientos (matar es IRREVERSIBLE → sesgo fuerte a NO matar con duda):
#  · demo 2026-07-14: la charla ambiente ("…necesita PARA poder acceder… CREANDO su memoria…", 500+ chars) mató
#    un worker → cap de longitud (una parrafada nunca es una orden).
#  · test post-P1/P2: el cap NO salva la frase CORTA con "para" PREPOSICIONAL — "hazme un widget PARA el tiempo",
#    "necesito un widget PARA la agenda" (4/8 falsos positivos). "para" es a la vez verbo de parada y la
#    preposición más común. Dos defensas nuevas: (a) si el turno EMPIEZA pidiendo algo (quiero/hazme/crea/abre/
#    muéstrame…) NO es una parada, corta ya; (b) "para" solo cuenta como IMPERATIVO al INICIO del turno y con
#    complemento de parada REAL (deíctico eso/ya/todo, "de <verbo>", o artículo+palabra-de-TRABAJO) — nunca
#    "para <sintagma nominal>" tipo "para el tiempo/la agenda/el finde", ni el "para" a media frase ("eso ES para
#    la búsqueda de piso"). Los otros verbos (detén/cancela/deja de/aborta/stop/kill) son inequívocos y NO se tocan.
_STOP_WORK = (r"eso|ese|esa|esto|proceso|procesos|tarea|tareas|widget|widgets|busqueda|busca|buscar|buscando|"
              r"creacion|crear|creando|modific|navegador|workers?|estudio|investig|"
              r"lo que estas haciendo|lo que haces|todo")
_STOP_WORK_RE = _re.compile(r"\b(" + _STOP_WORK + r")\b")
# Verbos de parada INEQUÍVOCOS (sin "para", que se trata aparte por su ambigüedad).
_STOP_VERB_STRONG_RE = _re.compile(r"\b(deten(?:te|lo|la|los|las)?|cancela(?:r|lo|la|los|las)?|"
                                   r"aborta(?:r|lo|la)?|deja de|stop|kill)\b")
# "para" IMPERATIVO: al inicio del turno (tras signos), + deíctico / "de <verbo>" / artículo+palabra-de-trabajo.
_STOP_PARA_RE = _re.compile(
    r"^[¿¡\s]*para(?:d|lo|la|los|las)?\s+(?:eso|esto|ese|esa|ya|de\s+\w+|"
    # stop MASIVO: "para todo" / "para todas las tareas" / "para todos los procesos|workers" (2026-07-17: el backstop
    # se comía "para todas las tareas" y el stop fallaba en silencio). "tod@s" solo si es TERMINAL o va con
    # los/las+palabra-de-trabajo → NO capta "para todo el mundo es difícil" (falso positivo pre-existente) ni "para
    # toda la comida".
    r"tod[oa]s?(?:\s+l[oa]s\s+(?:" + _STOP_WORK + r"))?(?=[\s.!?]*$)|"
    r"(?:el|la|los|las|ese|esa|este|esta|mi)\s+(?:" + _STOP_WORK + r"))\b")
# Verbos de PETICIÓN al inicio → el turno PIDE algo, no ordena parar (defensa (a)).
_REQUEST_START_RE = _re.compile(
    r"^[¿¡\s]*(?:me\s+)?(?:puedes|podrias|querria|quiero|quisiera|necesito|hazme|haz\b|hazlo|dame|"
    r"crea|crear|crees|creame|genera|generame|monta|montame|construye|abre|abreme|pon|ponme|prepara|"
    r"preparame|muestra|muestrame|ensename|ensename|busca|buscame|anade|agrega|apunta|programa|"
    r"me\s+gustaria|quiero\s+que|puedes\s+hacerme)\b")
_STOP_MAX_WORDS = 12          # una orden de parada real cabe de sobra; una explicación/parrafada no es una orden
_STOP_MAX_CHARS = 90


def looks_like_stop_work(text: str) -> bool:
    """True si el turno es una ORDEN de detener un proceso de fondo (no callar el TTS). Determinista, es/en.
    CONSERVADOR a propósito (matar es irreversible): solo turnos CORTOS que ORDENAN parar. Una petición
    ("hazme un widget para X") o una parrafada NUNCA disparan (el kill fino queda para la tool stop_worker)."""
    n = _norm_txt(text)
    if len(n) > _STOP_MAX_CHARS or len(n.split()) > _STOP_MAX_WORDS:
        return False
    if _REQUEST_START_RE.match(n):        # (a) el turno empieza PIDIENDO algo → no es una parada
        return False
    if _STOP_VERB_STRONG_RE.search(n) and _STOP_WORK_RE.search(n):
        return True                       # detén/cancela/deja de/aborta + referencia a trabajo (inequívoco)
    return bool(_STOP_PARA_RE.match(n))   # (b) "para <complemento de parada real>" AL INICIO


def login_site(text: str) -> str:
    """Mejor esfuerzo: extrae el dominio del sitio a loguear del texto (para el fallback de login de producción)."""
    n = _norm_txt(text)
    for key, dom in _KNOWN_SITES.items():
        if key in n:
            return dom
    return ""
