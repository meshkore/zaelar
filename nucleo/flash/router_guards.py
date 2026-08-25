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
    #
    # V2-167, 2026-08-20: that same rule was applied ONLY to the reply, and the operator's sentence — which has
    # the identical shape — was handed to `parse_when` WHOLE, so it refused. Measured on
    # `remember-and-remind-deadline`: «Apúntame que el jueves tengo que renovar el seguro del coche, y
    # recuérdamelo el miércoles» → zaelar answered «Voy a apuntarlo y programarte el aviso», the note half fired
    # and the notice half resolved to nothing. The verdict read «confirmó una acción que nunca ejecutó», and the
    # ambiguity it tripped over is not one a person would perceive: the day belongs to whichever verb it follows.
    # So the operator's own turn gets read positionally too, and only then whole (which is what preserves every
    # case that already worked — one date anywhere still resolves exactly as before).
    return (_sched.parse_when(n[m.end():])
            or _asked_reminder_moment(operator_text)
            or _sched.parse_when(operator_text))


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


def dated_note_backstop(reply: str, operator_text: str = "", window=None) -> dict | None:
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
    if m:
        # STILL ASKING IS NOT SETTLED, and that rule belongs to BOTH branches. It was written for the one below
        # («a question mark means it is still asking, and nothing gets filed on a date it has not settled») and
        # the promise branch never got it — so a reply that promises AND asks in the same breath filed an entry
        # built out of its own question. Reproduced from round 12 of `remember-and-remind-deadline`: «Perfecto,
        # lo anoto. ¿A qué hora del jueves te viene bien la renovación?» put a meeting in the agenda titled
        # «¿a que hora del».
        #
        # Waiting costs one turn and nothing else: this backstop is re-evaluated every turn, so the entry lands
        # as soon as the reply stops asking — measured in the same reproduction, it lands on the turn where the
        # date is finally settled, with the right title. Filing early costs a wrong entry that nobody will go
        # and delete.
        if "?" in (reply or ""):
            return None
        tail = n[m.end():]
        cut = _REMIND_VERB_RE.search(tail)
        if cut:
            tail = tail[:cut.start()]
    else:
        # V2-167 — the reply-verb trigger alone is a treadmill. This run's model said «la cita ESTÁ EN TU AGENDA
        # para el jueves», which asserts the state instead of promising the act, so V2-159's list missed it and
        # the agenda stayed empty for the second run running. What does NOT change between runs is what the
        # OPERATOR asked, so that is what the obligation is read from; the reply is then only consulted for
        # whether the agent backed out — a question mark means it is still asking, and nothing gets filed on a
        # date it has not settled.
        # V2-176: la petición de apuntar no CADUCA porque el operador necesitara otro turno para acertar la
        # fecha. Medido: el «Apúntalo» iba en el turno 3, el turno 4 solo corrigió el día, y la agenda se quedó
        # vacía (`n_after: 1`, solo el aviso) mientras zaelar decía «te lo dejo apuntado en la agenda».
        if not note_asked_in_window(window, operator_text) or "?" in (reply or ""):
            return None
        clause = commitment_from_window(window, operator_text) if window else commitment_clause(operator_text)
        tail = _norm_txt(strip_note_lead(clause))
    try:
        from nucleo import scheduler as _sched
    except Exception:
        return None
    when = _sched.parse_when(tail)
    if not when:
        return None
    lead = _DATE_LEAD_RE.search(tail)
    # The date can come BEFORE what it dates («el jueves tengo que renovar el seguro») or after it («la
    # renovación del seguro el jueves»). Taking only the text in front of it turned the first shape into an
    # empty title, and an agenda entry with no title is not an entry.
    if lead:
        title = (tail[:lead.start()] or tail[lead.end():]).strip(" ,.;:")
    else:
        title = tail.strip(" ,.;:")
    for _lead_in in ("que ", "tengo que ", "he de ", "debo "):
        if title.startswith(_lead_in):
            title = title[len(_lead_in):]
    if len(title) < 4:
        title = (operator_text or "").strip()[:120]
    return {"title": title[:120], "date": when.split(" ")[0]} if title else None


def already_in_agenda(note: dict) -> bool:
    """Is this commitment already written down for that day?

    Lives NEXT TO the write and not inside `dated_note_backstop` on purpose: that function is a pure decision
    over two strings and a clock, which is why it can be tested against a literal transcript. Reading a global
    store from inside it made nine of its own tests depend on the order the previous ones ran in — the same
    coupling this fix exists to remove, one layer down.

    V2-194, measured in the sandbox of the 2026-08-20 02:34 run: the agenda came out with the SAME commitment
    twice on the same date — «Renovar seguro del coche» and «Renovar el seguro del coche», 2026-08-27. One is
    the model's own data-op and the other this backstop, fired on a later turn.

    The sibling backstop has had this since V2-153 (it refuses to schedule a notice for an instant that already
    has one); the note half never got it, and its gate — «only if THIS turn did not already do the data-op» —
    cannot see a data-op from a PREVIOUS turn. A duplicate alert is a defect the operator hears twice; a
    duplicate agenda entry is one he SEES twice, which is worse because it stays there.

    Compared on the DAY plus the content words of the title, not on the exact string: the two measured entries
    differ by one article, and a comparison that an article defeats is not a comparison. Fail-open — if the
    agenda cannot be read, backing the promise beats dropping it.
    """
    try:
        from widgets import store as _store
        meetings = (_store.load("agenda") or {}).get("meetings") or []
    except Exception:
        return False
    mine = _content_words(str(note.get("title") or ""))
    if not mine:
        return False
    for m in meetings:
        if str((m or {}).get("date") or "") != str(note.get("date") or ""):
            continue
        theirs = _content_words(str((m or {}).get("title") or ""))
        if theirs and len(mine & theirs) >= min(2, len(mine)):
            return True
    return False


_STOPWORDS = frozenset({"el", "la", "los", "las", "un", "una", "de", "del", "al", "que", "y", "a", "en",
                        "mi", "tu", "su", "the", "a", "an", "of", "to", "my", "your"})


def _content_words(text: str) -> set[str]:
    return {w for w in _norm_txt(text).split() if len(w) > 2 and w not in _STOPWORDS}


_CLAUSE_SPLIT_RE = _re.compile(r"[,;.!?\n]|\sy\s|\sand\s", _re.I)

# The words that only DATE something and never describe it. Needed to answer one question: does this clause say
# anything BESIDES when?
_DATE_ONLY_WORDS = frozenset({
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "manana", "tomorrow", "hoy", "today", "dia", "day", "esta", "este", "proximo", "proxima", "que", "viene",
})


# Prepositions and fillers that carry no TOPIC. `_content_words` keeps them (it was written for the agenda,
# where the cost of an extra word is different) and it also keeps punctuation attached, so «Hotel Palacio de la
# Merced para el 30 de agosto.» and «entradas para El Rey León» overlapped on «para» — one function word was
# enough to make two unrelated errands look like the same one.
#
# Not fixed inside `_content_words` on purpose: `already_in_agenda` compares with it, and dropping words there
# makes IT match less often, which duplicates agenda entries. Here the error directions are the safe ones — a
# missing stopword creates a spurious overlap and simply keeps today's conduct.
_NON_TOPIC = frozenset({"para", "por", "con", "sin", "sobre", "desde", "hasta", "entre", "una", "uno", "unos",
                        "unas", "los", "las", "del", "las", "que", "más", "mas", "muy", "solo", "algo", "cosa",
                        "for", "with", "from", "about", "some", "any", "just"})


def _topic_words(text: str) -> set[str]:
    """Content words with punctuation stripped and function/date words dropped — what two errands can be
    compared BY."""
    out = set()
    for w in _content_words(text):
        w = w.strip(".,;:!?¿¡()«»\"'-—")
        if len(w) > 2 and w not in _NON_TOPIC and w not in _DATE_ONLY_WORDS:
            out.add(w)
    return out


def nothing_running_for(goal: str, running_goals) -> bool:
    """True when NOTHING among the live errands is about `goal` — so a promise about it has nothing behind it.

    The escalation backstop was gated on «is anything running?», and the question that decides is «is anything
    running FOR THIS?». Measured twice, in two different cases:

      · `book-hotel-night-known__es` (2026-08-20): «Resérvame una noche en el Hotel Palacio de la Merced» →
        «Me pongo con ello» → nothing escalated, because a worker from the PREVIOUS errand was still alive. The
        mechanism showed `status=cancelled url=ticketmaster.es` while zaelar said «la reserva sigue en marcha»
        for four turns. The judge called it «divergencia crítica de dominio».
      · `restaurant-tonight-madrid` (2026-08-19): the same shape from the other side — the operator asked about
        Casa Lucio and got answered about El Rey León.

    The gate's own reasoning was right and incomplete: with a live task «sigo con ello» IS honest and
    re-escalating WOULD run the same work twice — but only if the live task is about what was asked.

    CONSERVATIVE ON PURPOSE, in the direction the gate was protecting: this answers True only when it can tell,
    and «cannot tell» means False (behave exactly as before). So a goal too thin to judge, or any overlap at all
    with something already running, keeps today's conduct. Running one errand twice is a defect the operator pays
    for; being told «sigo con ello» about somebody else's errand is one he cannot even see.
    """
    mine = _topic_words(goal)
    if len(mine) < 2:
        return False               # too thin to judge → do not act on a guess
    for other in (running_goals or []):
        theirs = _topic_words(str(other or ""))
        if not theirs or (mine & theirs):
            return False           # an unreadable goal, or any real overlap → assume it is this one
    return True


def clause_is_only_a_date(clause: str) -> bool:
    """True when the «commitment» clause says nothing except WHEN — so there is no event for a notice to precede.

    Found while fixing the measured case, one line away from it: «El martes recuérdame lo del seguro» leaves
    `commitment_clause` with just «El martes», because the clause is cut at the ask verb and the date sits before
    it. `reminder_before` then reads that as the event day, sees the notice is not earlier than the event, walks
    back a week into the past and falls through to «fire promptly» — so a reminder asked for Tuesday goes off
    THIS SECOND. `reminder_before` is right about its own rule; what was wrong was being handed a date and told
    it was a commitment.

    A date with nothing around it is not a commitment. When that is what we have, the constraint simply does not
    apply and the moment the operator named stands.
    """
    return not (_content_words(clause) - _DATE_ONLY_WORDS)




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


# ── V2-167 · un aviso llega ANTES de aquello de lo que avisa ──────────────────────────────────────────────
#
# The operator's OWN ask, which is not the same vocabulary as the agent's promise (`_REMIND_VERB_RE`, above):
# he says «recuérdamelo», the agent says «te aviso». Both halves live in the same sentence and telling them
# apart is what lets the commitment be read separately from the notice.
# V2-167 ronda 12 (2026-08-20 12:39) — el operador pidió el aviso en SUBJUNTIVO: «Que me AVISES el miércoles
# 26 por la mañana». Este patrón sólo conocía el indicativo (`me avisas`), así que no reconoció la petición, el
# día del aviso no se pudo leer por posición, la frase entera se fue a `parse_when` —que ve «jueves 27» y
# «miércoles 26» y se niega, con razón— y `scheduled_jobs.created` salió VACÍO mientras zaelar decía «lo dejo
# apuntado y programo el aviso» y remataba con «Ya lo tienes todo listo».
#
# Es EXACTAMENTE el fallo que este módulo ya se comió en V2-151 y que dejó escrito ahí arriba: la primera forma
# del patrón deletreaba una variante concreta y la corrida real dijo la de al lado. Por eso esto se ensancha por
# MORFOLOGÍA (la raíz del verbo + su terminación) y no añadiendo la frase de hoy a una lista: pedir un aviso
# tras «que» pide subjuntivo en español, y eso no es una variante rara sino la forma natural de pedirlo.
#
# El pronombre opcional (`me lo avises` / `me la recuerdes`) va dentro por lo mismo. La raíz sigue emparejada
# con su terminación en vez de un `\w*` suelto, para que una NEGACIÓN («no me avises») no arrastre el patrón.
_REMIND_ASK_RE = _re.compile(
    r"\b(recuerdame\w*|recuerdalo|avisame\w*|"
    r"me\s+(?:lo\s+|la\s+)?(?:avis|recuerd)[ae]s|"
    r"me\s+(?:lo\s+)?mand[ae]s\s+(?:el|un)\s+(?:recordatorio|aviso)|"
    r"remind\s+me|let\s+me\s+know)\b", _re.I)


def _asked_reminder_moment(operator_text: str) -> str:
    """The moment the OPERATOR attached to his own reminder REQUEST, read by position — or "".

    Sibling of the positional read on the reply: «…y recuérdamelo el miércoles» names the notice day right after
    the ask, exactly as «te avisaré el miércoles» does. Reading the sentence whole instead makes a two-weekday
    turn look ambiguous when it is not, which is what left `remember-and-remind-deadline` promising a notice it
    never scheduled.

    Deliberately positional and nothing more: a date BEFORE the ask verb («el martes recuérdame lo del seguro»)
    resolves nothing here and falls through to the whole-sentence read, same as today. Guessing at word order is
    how a backstop starts scheduling things nobody asked for.
    """
    n = _norm_txt(operator_text)
    m = _REMIND_ASK_RE.search(n)
    if not m:
        return ""
    try:
        from nucleo import scheduler as _sched
    except Exception:
        return ""
    return _sched.parse_when(n[m.end():]) or ""


def commitment_clause(operator_text: str) -> str:
    """The part of the operator's turn that states the COMMITMENT, with his reminder request cut off.

    «Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles» carries two days
    and two different obligations. `parse_when` refuses an ambiguous pair on purpose, so position is what tells
    them apart — the same trick `promises_a_dated_reminder` already uses on the reply, applied to the request.
    Returns the ORIGINAL text (not the normalised one) so anything built from it is readable out loud.
    """
    text = operator_text or ""
    n = _norm_txt(text)
    m = _REMIND_ASK_RE.search(n)
    if not m:
        return text.strip()
    end = m.start() if len(n) == len(text) else None
    head = text[:end] if end is not None else n[:m.start()]
    return head.strip(" ,.;:y")


def holding_line(window, lang=None) -> str:
    """The never-mute filler for a turn whose only content is «the task is still running» — one that does NOT
    repeat itself.

    `data_acks` has had this treatment since V2-038, because two «Hecho.» in a row tripped the loop detector.
    The waiting filler never got it, and it is said far more often. Measured on `cheapest-monitor`
    (2026-08-20 01:21): «Vale, dame un momento que lo miro.» FOUR times, word for word, with the operator
    answering «vale, quedo atento» each time; and on `restaurant-tonight-madrid`, five turns of the same. The
    judge marked it grave in both, and it is not the model doing it — the line is emitted here, by us, as a
    backstop for a turn that came back mute.

    Escalates instead of repeating: a fresh variant while there is one, and from the third consecutive wait the
    ONE honest fact available — how long it has been — plus a way out. It never states a step: that is the line
    V2-133 drew («el arreglo no puede ser quitarlos; tiene que ser que el relleno no afirme una fase»), and
    minutes elapsed are not a step.
    """
    try:
        from voice.engine.core import langs as _langs
        lang = lang or _langs.current_language()
    except Exception:
        return "Sigo con ello."
    lines = tuple(getattr(lang, "holding_lines", ()) or (getattr(lang, "filler_holding", "Sigo con ello."),))
    said = [str((m or {}).get("content") or "").strip()
            for m in (window or []) if (m or {}).get("role") == "assistant"]
    recent = [t for t in said[-3:] if t]
    waits = sum(1 for t in recent if t in lines)
    if waits >= 2:
        mins = _longest_pending_min()
        if mins >= 1:
            waited = str(getattr(lang, "filler_waited", "") or lines[-1]).format(min=mins)
            # En la práctica los minutos crecen, así que dos esperas seguidas no salen idénticas; pero si el
            # reloj no ha pasado de minuto, se rota en vez de repetir palabra por palabra — que es justo el
            # defecto que esto arregla, y no vale reintroducirlo por la puerta de atrás.
            if not recent or waited != recent[-1]:
                return waited
    for line in lines:                      # agota las variantes ANTES de reutilizar ninguna
        if line not in recent:
            return line
    for line in lines:                      # y si ya se dijeron todas, al menos no la de justo antes
        if not recent or line != recent[-1]:
            return line
    return lines[-1]


def _longest_pending_min() -> int:
    """Minutes of the longest-running background task, or 0 when that cannot be read. A FACT, not a step."""
    try:
        from nucleo import dispatch as _d
        return max((int(t.get("secs") or 0) for t in _d.pending_summaries()), default=0) // 60
    except Exception:
        return 0


def commitment_from_window(window, current_text: str = "", max_back: int = 6) -> str:
    """The clause that says WHAT the commitment is, which is not always in the turn that fixes its DATE.

    Same shape of failure `escalate_goal_from_window` already fixed for escalation (V2-132), measured here on
    `remember-and-remind-deadline`, run of 2026-08-20 01:01. The operator states the obligation once and then
    spends two turns correcting the date; by the turn that finally settles it, the subject is gone:

        t1  «Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles»
        t3  «El jueves de esta semana tengo que renovar el seguro del coche. Apúntalo y recuérdamelo…»
        t4  «Sí, perdona, me he liado con las fechas. Me refiero al jueves que viene, 27. Recuérdamelo…»

    Reading t4 alone, `commitment_clause` returns «Sí, perdona, me he liado con las fechas. Me refiero al
    jueves que viene, 27» — and that went in as the reminder's own text, so the job that fires on Wednesday
    reads the operator his own apology back. The judge called it «un aviso programado inútil», which is exactly
    right.

    The rule: the SUBJECT is what he asked for the FIRST time, the DATE is whatever this turn settles on. It
    only looks back when an earlier turn also asked for a reminder or a note — that is what makes this turn a
    CONTINUATION of that request rather than a new one, and it is the guard that keeps a genuinely new errand
    later in the same conversation from inheriting an old subject.

    Known edge, stated rather than hidden: a SECOND reminder about something else, asked in a conversation that
    already had one, will pick up the first subject if this turn names nothing. Telling those apart needs the
    turn to be understood and not matched, which is V2-075's ground (a model judges meaning) and wants its own
    measurement — not a list of apology phrases, which is the treadmill V2-151 already paid for.
    """
    current = commitment_clause(current_text) if current_text else ""
    turns = [str((m or {}).get("content") or "").strip()
             for m in (window or []) if (m or {}).get("role") == "user"]
    turns = [t for t in turns if t][-max_back:]
    asked_before = [t for t in turns[:-1] if _REMIND_ASK_RE.search(_norm_txt(t))
                    or _NOTE_ASK_RE.search(_norm_txt(t))]
    if not asked_before:
        return current
    first = commitment_clause(asked_before[0])
    return first or current


def note_asked_in_window(window, current_text: str = "", max_back: int = 6) -> bool:
    """Did the operator ask for this to be written down — in THIS turn or in an earlier one?

    The other half of the same run: the agenda entry never happened (`n_after: 1`, only the reminder job)
    because the «apúntalo» was in turn 3 and the turn that settled the date was turn 4. An obligation does not
    expire because the operator needed another turn to get the date right.
    """
    if current_text and _NOTE_ASK_RE.search(_norm_txt(current_text)):
        return True
    turns = [str((m or {}).get("content") or "") for m in (window or []) if (m or {}).get("role") == "user"]
    return any(_NOTE_ASK_RE.search(_norm_txt(t)) for t in turns[-max_back:] if t)


# The operator's own «write this down» ask. Sibling of `_REMIND_ASK_RE`, and the counterpart to the agent-side
# `_NOTE_VERB_RE`: the obligation is defined by what HE asked for, which is far more stable than how the model
# happens to word its confirmation — V2-159 matched «te apunto», the next run said «la cita está en tu agenda»,
# and the backstop went quiet. Chasing the model's phrasing is the treadmill V2-151 already paid for.
_NOTE_ASK_RE = _re.compile(
    r"\b(apuntame|apuntalo|apunta\s+que|anotame|anotalo|anota\s+que|"
    r"me\s+(?:lo\s+)?apuntas|ponme\s+(?:en|a)\s+(?:la|mi)\s+agenda|"
    r"note\s+(?:this|that)\s+down|put\s+(?:this|that)\s+in\s+my\s+calendar)\b", _re.I)

def strip_note_lead(text: str) -> str:
    """`text` without the operator's leading «apúntame que…» — what remains is the commitment itself.

    Shared by the agenda title and the reminder prompt so the two cannot disagree about where the commitment
    starts; both were getting «apúntame que» as the thing to file or announce.
    """
    body = (text or "").strip()
    n = _norm_txt(body)
    m = _NOTE_ASK_RE.search(n)
    if not m or m.start() != 0:
        return body
    body = (body[m.end():] if len(n) == len(body) else n[m.end():]).strip(" ,.;:")
    for lead_in in ("que ", "tengo que ", "he de ", "debo "):
        if body.lower().startswith(lead_in):
            return body[len(lead_in):]
    return body


_PROMPT_S = 300          # how soon a reminder fires when the day the operator named has already gone by


def reminder_before(when: str, commitment: str, now=None) -> str:
    """`when` corrected so the notice lands BEFORE the thing it reminds of. Pure; `now` injectable.

    V2-167, measured on `remember-and-remind-deadline`: «Apúntame que el JUEVES… y recuérdamelo el MIÉRCOLES»,
    asked ON a Wednesday. `parse_when("el miercoles")` answers the COMING Wednesday — correct in isolation, and
    the reason it is wrong here is not the parser: it is that a reminder has exactly one constraint the parser
    cannot know about, which is that it must fall before the event. The job went in for 2026-08-26, six days
    after the Thursday it was reminding about.

    So the correction lives here, where both dates are in hand, and NOT in `scheduler.parse_when` — a shared
    date parser with no notion of what it is dating would be the wrong place to teach this.

    Rules, in order: already earlier → untouched; not earlier → the previous occurrence of that same weekday;
    that one already past → fire PROMPTLY, because the day he named is today (or gone) and reminding him now is
    the useful reading of what he asked. Never the silent useless date.
    """
    if not when or not commitment:
        return when
    import datetime as _dt
    if now is None:
        # ONE clock. Every date around this function comes from `scheduler.parse_when`, which reads
        # `scheduler.time.time()`; taking «now» from `datetime.now()` instead meant the correction was computed
        # against a different clock than the dates it was correcting. Invisible in production and lethal in a
        # test: pinning the scheduler's clock moved the inputs and left this one on the wall clock, so the
        # "fire promptly" branch answered with the REAL time and the assertions drifted by hours.
        try:
            from nucleo import scheduler as _sched_clock
            now = _dt.datetime.fromtimestamp(_sched_clock.time.time())
        except Exception:
            now = _dt.datetime.now()
    try:
        w = _dt.datetime.strptime(when.strip(), "%Y-%m-%d %H:%M")
        c = _dt.datetime.strptime(commitment.strip(), "%Y-%m-%d %H:%M")
    except Exception:
        return when
    if w.date() < c.date():
        return when
    w -= _dt.timedelta(days=7)
    if w <= now:
        return (now + _dt.timedelta(seconds=_PROMPT_S)).strftime("%Y-%m-%d %H:%M")
    return w.strftime("%Y-%m-%d %H:%M")


def dated_reminder_backstop(reply: str, operator_text: str = "", window=None) -> dict | None:
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
    # V2-167 · (1) the notice must land BEFORE the thing it announces, and (2) what fires must be the REMINDER,
    # not the request that produced it. The measured job carried the operator's raw turn as its prompt, so on
    # firing the agent would have been asked to SCHEDULE the reminder all over again — the «se pierde el QUÉ»
    # this case has been dragging since V2-134, finally visible in the field that causes it.
    # V2-176: el QUÉ puede haberse dicho tres turnos antes y este turno solo fijar la FECHA. Sin ventana se
    # comporta exactamente como antes, así que ningún llamante viejo cambia de conducta.
    clause = commitment_from_window(window, operator_text) if window else commitment_clause(operator_text)
    try:
        from nucleo import scheduler as _sched
    except Exception:
        return {"schedule": when, "prompt": _reminder_prompt(clause, operator_text), "name": "aviso"}
    # A clause that is nothing but a date states no event, so there is nothing for the notice to precede
    # (see `clause_is_only_a_date`). Passing it on would make `reminder_before` fire the notice at once.
    clause_when = "" if clause_is_only_a_date(clause) else (_sched.parse_when(clause) or "")
    when = reminder_before(when, clause_when)
    if not when:
        return None
    try:
        jobs = list(_sched.list_jobs(active_only=True))
    except Exception:
        jobs = []     # cannot read the schedule → still better to back the promise than to drop it
    for job in jobs:
        if str(job.get("schedule") or "").strip() == when:
            return None
    # V2-153 deduplicated on the exact INSTANT, and that stopped being enough once the instant can be corrected
    # (above): the turn that CARRIES the commitment gets a corrected moment, the one that merely reaffirms it
    # («gracias, así no se me pasa») has no commitment to correct against and would keep the uncorrected one —
    # two different instants for one request, which is exactly the double alert V2-153 exists to prevent. A turn
    # that neither dates a commitment nor ASKS for anything adds no new obligation, so a live notice covers it —
    # while «recuérdame lo del taller», which also carries no date, is a new request and still gets its own.
    asked_now = bool(_REMIND_ASK_RE.search(_norm_txt(operator_text)) or _NOTE_ASK_RE.search(_norm_txt(operator_text)))
    if not clause_now_or_ask(clause_when, asked_now) and any(str(j.get("name") or "") == "aviso" for j in jobs):
        return None
    return {"schedule": when, "prompt": _reminder_prompt(clause, operator_text), "name": "aviso"}


def clause_now_or_ask(clause_when: str, asked_now: bool) -> bool:
    """Does THIS turn create a new obligation? Only if it dates a commitment or asks for something."""
    return bool(clause_when) or bool(asked_now)


def _reminder_prompt(clause: str, operator_text: str) -> str:
    """What the agent is handed when the job fires: an instruction to NOTIFY, carrying the commitment.

    The lead-in («apúntame que…») is stripped because the cron's reader is the agent at a later moment: leaving
    it in asks it to file something, which is precisely the loop this fixes.
    """
    body = strip_note_lead(clause or operator_text or "")
    return f"AVISA al operador, es el recordatorio que te pidió: {body}"[:300]


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


# ── OPENING A CARD IS NOT DELIVERING A RESULT (V2-209) ────────────────────────────────────────────────────────
def nothing_to_show(widget_id: str) -> bool:
    """Does the surface we just opened have NOTHING in it?

    `_surface_is_empty` (voice provider, 2026-08-17) already answered this for the saved state of a widget and
    only STAMPED it on the observability row — the ack itself kept saying «Aquí lo tienes» over a blank sheet, and
    that was the deliberate scope then. It has a measured cost now: on `book-hotel-night-known__es`
    (2026-08-20 13:49) turn 2 opened the browser card and said «Aquí lo tienes» with the task still working and
    nothing found, and the judge scored it «alucinación de éxito». The phrase is OURS, not the model's — same
    class as the «Hecho.» of V2-176 front 1, and the second time a canned ack has been the thing that lied.

    A BROWSER card is the case the generic check cannot answer: its saved state is not empty (it holds the task),
    so «is the state empty» says «there is something to show» while what it holds is work in progress. With a live
    task, a card is a window on something unfinished — never a delivery. Once nothing is live, the saved state IS
    the answer again.

    Fail-open to False: never claim a surface is empty when we cannot tell (an ack that under-promises on a real
    result is its own kind of wrong).
    """
    wid = (widget_id or "").strip().lower()
    if wid.startswith("navegador"):
        try:
            from widgets.navegador import tasks as _nt
            if _nt.active_progress(limit=6):
                return True
        except Exception:
            return False
    try:
        from widgets import store as _store
        data = _store.load(wid.split("::")[0]) or {}
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    return not any(isinstance(v, (list, tuple, dict)) and len(v) > 0 for v in data.values())


def show_ack(lang, widget_id: str = "", window=None) -> str:
    """The ack for a turn whose only act was opening a surface. Shared so the two channels cannot drift apart:
    this exact phrase failing is what V2-176 measured, and it failed in the channel nobody was looking at."""
    if widget_id and nothing_to_show(widget_id):
        return getattr(lang, "show_ack_empty", None) or lang.show_ack
    return lang.show_ack


# ── A FACT ABOUT THE WORLD, ANSWERED WITH NO SOURCE (V2-210) ──────────────────────────────────────────────────
# Measured on `quick-fact-opening-hours` (2026-08-20 15:08), the cleanest failure on the board because there is
# nothing else in it — no wall, no worker, no network error:
#
#     TESTER  ¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?
#     ZAELAR  Mañana abre a las 10:00 y la entrada general cuesta 15 €.
#
# Zero tools. Families: flash, memory, system — no `search`. The numbers are roughly right, which is WHY this is
# dangerous: the model is confident, so it never reaches for `web_search`, and a confident wrong price reads
# exactly like a confident right one. V2-022's whole point is that this class of question is answered IN THE
# TURN from a real source; V2-135 already fixed the composing half of this same case. What was missing is the
# trigger for the turn where the model does not ask.
#
# NARROW ON PURPOSE, and both halves are required:
#   · the QUESTION has to be about the opening hours / price / address / phone of something out there, and not
#     about the operator's own things («¿a qué hora es mi cita?» is the agenda, and answering it from memory is
#     correct);
#   · the ANSWER has to state a concrete FIGURE. «Suele abrir por la mañana» claims nothing checkable and
#     forcing a search on it would spend a second on every vague sentence.
# A false «go and search» costs latency on every turn it fires on, so the cost of being wide is paid by turns
# that were fine. A false negative costs one invented fact, which is the failure being fixed — hence a rule that
# fires on the shape actually measured and says so.
_EXTERNAL_FACT_RE = _re.compile(
    r"\b(a\s+qu[eé]\s+hora\s+(abre|abren|cierra|cierran|empieza|empiezan)|"
    r"abre[nu]?\b|abierto\b|cierra[nu]?\b|horario\b|horarios\b|"
    r"cu[aá]nto\s+(cuesta|vale|valen|cuestan)|precio\b|tarifa\b|entrada\s+general\b|"
    r"direcci[oó]n\b|tel[eé]fono\b|"
    r"what\s+time\s+(does|do)\b|opening\s+hours\b|how\s+much\s+(is|are|does)\b)", _re.I)

# The operator's OWN things: their agenda, their car, their subscription. Those are answered from memory or from
# their account, never from a search engine, and «mi» is what marks them.
_OWN_THING_RE = _re.compile(r"\b(mi|mis|m[ií]o|m[ií]a|nuestr[oa]s?)\b", _re.I)

# A checkable figure: a time, an amount, a price. Bare digits are NOT enough — «te lo digo en 2 minutos» is not
# a claim about the world.
_FIGURE_RE = _re.compile(
    r"(\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}\s*h\b|\b\d{1,4}([.,]\d{1,2})?\s*(€|euros?|dollars?|usd|\$)|"
    r"(€|\$)\s*\d|\b\d{1,2}\s*(de\s+la\s+ma[ñn]ana|de\s+la\s+tarde|am|pm)\b)", _re.I)


def answer_needs_a_source(operator_text: str, reply: str) -> bool:
    """Did this turn state a checkable fact about the world without consulting anything?

    Only the caller knows whether a tool ran, so this answers the OTHER half: whether the pair
    (question, answer) is the shape that must never be improvised.
    """
    q, a = (operator_text or ""), (reply or "")
    if not q or not a:
        return False
    if _OWN_THING_RE.search(q):
        return False
    return bool(_EXTERNAL_FACT_RE.search(q) and _FIGURE_RE.search(a))


# ── WHAT THE CRON HANDS BACK TO THE AGENT (V2-214) ────────────────────────────────────────────────────────────
# `_reminder_prompt` composes a safe instruction, and only the BACKSTOP goes through it. When the model emits the
# `cron.create` tag itself, its `prompt` is whatever it wrote — and measured on `remember-and-remind-deadline`
# (2026-08-20 15:49) what it wrote was the operator's own sentence: «el jueves tengo que renovar el seguro del
# coche». The job exists, fires on the right day, and hands the agent a first-person obligation, which reads as
# «file this», not «tell him». So the alert is created and its CONTENT is broken — the judge called it exactly
# that, and it is the loop `_reminder_prompt`'s own docstring already warned about, reached by the other door.
#
# NARROW: only a FIRST-PERSON obligation is rewritten. A cron the operator set up deliberately («cada lunes dame
# el resumen») is already an instruction to the agent, and wrapping it would break a feature to fix a defect.
_FIRST_PERSON_DUTY_RE = _re.compile(
    r"\b(tengo\s+que|he\s+de|debo|me\s+toca|tengo\s+pendiente|"
    r"i\s+have\s+to|i\s+need\s+to|i\s+must|i\s+should)\b", _re.I)

# Already addressed TO the agent: leave it exactly as it is.
_AGENT_IMPERATIVE_RE = _re.compile(
    r"^\s*(avisa|av[ií]same|recu[eé]rda|recuerdame|dime|d[ií]|notif[ií]|remind|tell|notify|let\s+me\s+know)",
    _re.I)


def safe_reminder_prompt(prompt: str) -> str:
    """What the agent is handed when this job fires. Returns `prompt` untouched unless it is the OPERATOR's own
    words about their own obligation, in which case it is wrapped into an instruction to NOTIFY.

    Lives here, next to `_reminder_prompt`, so both doors into the scheduler say the same thing — the backstop
    already did and the model's own tag did not.
    """
    p = (prompt or "").strip()
    if not p or _AGENT_IMPERATIVE_RE.search(p) or not _FIRST_PERSON_DUTY_RE.search(p):
        return p
    return _reminder_prompt(p, p)


# ── EL BACKSTOP DE ENTREGA (V2-305) ──────────────────────────────────────────────────────────────────────────
# Medido en la ronda 34 de `search-buy-guitar__es` (2026-08-25 01:56): la nota del navegador llegó como texto
# del turno, la cara del estado llevaba las filas, y el modelo contestó «Vale, te aviso en cuanto tenga
# novedades» — y así CINCO turnos, con delivery_lag_s = 98,9 s. El imperativo del prompt pierde contra el
# reflejo de espera una ronda de cada tres, y esa varianza es la diferencia entre pasar y fallar el caso.
# Misma familia que el nunca-mudo (V2-132) y el holding_line de arriba: cuando la conducta correcta es
# DETERMINISTA —hay filas con nombre delante y el turno solo dice «espera»— la garantiza el código, no la
# temperatura del modelo.
_WAITING_REPLY_RE = _re.compile(
    r"(te aviso|te lo digo|te lo cuento|te aviso en cuanto|en cuanto (tenga|salga|encuentre|aparezca|lo tenga)|"
    r"sigo con ello|sigo dandole|sigo en ello|sigo pendiente|sigo buscando|sigo trabajando|dame un momento|"
    r"sin novedades|sigue en marcha|todavia no|aun no|quedamos así|me quedo a la espera)")


def sheet_delivery_backstop(reply: str, rows, said_before: str = "", errand: str = "") -> str:
    """La frase que se AÑADE a una respuesta de pura espera cuando la hoja ya tiene filas con nombre que la
    conversación no ha dicho. "" si no toca.

    Estrecho a propósito, por los dos lados: solo dispara sobre una respuesta CORTA que es una frase de espera
    (una respuesta larga ya está contando algo, y pisarla sería peor); y solo con filas cuyo contenido no haya
    aparecido en lo que zaelar YA dijo — re-anunciar lo entregado es el disco rayado de V2-189. La frase afirma
    solo HECHOS: las filas vienen de la hoja (escritas por `intake.push`), así que «en la hoja» es verdad — la
    frontera de V2-278 (nunca afirmar la pantalla EN VUELO) no aplica a una escritura que ya ocurrió.
    """
    r = _norm_txt(str(reply or ""))
    if not r or len(str(reply or "")) > 300:
        return ""
    if not _WAITING_REPLY_RE.search(r):
        return ""
    said = _norm_txt(str(said_before or "")) + " " + r
    fresh: list[str] = []
    for row in rows or []:
        row = str(row or "").strip()
        if not row:
            continue
        # «Ya dicha» por TOKEN SIGNIFICATIVO, no por prefijo literal: zaelar dice «la Fender CD-60», nunca el
        # título entero del anuncio («Guitarra Acústica Fender CD-60»), y exigir el prefijo re-anunciaba lo
        # entregado (la misma identidad que el reloj de entrega pagó en la ronda 33). Significativo = trae
        # dígito (un código de modelo) o es una palabra distintiva de ≥5 letras — y NUNCA una palabra que ya
        # esté en el ENCARGO: la categoría («guitarra», «hotel», «monitor») está en la petición por
        # definición, así que suena en cada turno y marcaría TODAS las filas como dichas. Excluir los tokens
        # del encargo es agnóstico del dominio — una lista de genéricos por sector sería adaptarse al caso de
        # uso, que es justo lo que la doctrina prohíbe. Con UN token distintivo ya sonado, la fila cuenta
        # como dicha: el backstop dispara de menos, nunca de más.
        _errand_toks = set(_norm_txt(str(errand or "")).split())
        title = _norm_txt(row.split(" — ")[0])
        toks = [w for w in title.split()
                if (any(c.isdigit() for c in w) or len(w) >= 5) and w not in _errand_toks]
        if toks and not any(t in said for t in toks):
            fresh.append(row)
        if len(fresh) >= 3:
            break
    if not fresh:
        return ""
    if _looks_like_an_unfiltered_feed(rows):
        return ""
    return ("Bueno, de hecho ya hay candidatos en la hoja de resultados: "
            + "; ".join(f"«{f}»" for f in fresh)
            + ". Dime si alguno te encaja o sigo afinando.")


def _looks_like_an_unfiltered_feed(rows) -> bool:
    """¿Estas filas son el FEED de la página en vez de los resultados de la búsqueda? (V2-305, corregido)

    La ronda 35 (2026-08-25 02:20) llenó la hoja de Beyblades, cosmética, velas y un Ford Fiesta: el worker
    falló el tecleo, la página devolvió su portada sin filtrar, y anunciar eso como candidatos habría sido
    peor que la espera que corrige. La primera puerta que puse contra eso exigía compartir palabra con el
    ENCARGO — y eso está adaptado a UN dominio: en un marketplace el título repite la categoría («Guitarra
    Acústica Fender»), pero un hotel se llama «La Banda Living Hostel» y un vuelo «Ryanair directo». Medido en
    la tanda de las 10:04: con 36 filas legítimas de hoteles en la hoja, el backstop no disparó NI UNA vez y
    el juez volvió a fichar «retención de 202 s».

    La señal que sí separa los dos casos sin mirar el sector: la COHERENCIA ENTRE LAS FILAS. Unos resultados
    de búsqueda comparten algo entre sí («Guitarra» en todas, «Hostel» en tres de tres); un feed sin filtrar
    no comparte nada (Beyblade · Paula's Choice · Velas · Carta Nico Williams · Ford Fiesta). Con menos de
    tres filas no se juzga: dos cosas distintas no son un feed, y callar por ahí sería el error de ayer.

    Lado conservador asumido: un encargo legítimamente heterogéneo («cosas para el piso nuevo») se lee como
    feed y el backstop calla — se pierde una ayuda, no se dice una falsedad.
    """
    titles = [_norm_txt(str(r or "").split(" — ")[0]) for r in (rows or [])]
    titles = [t for t in titles if t]
    if len(titles) < 3:
        return False
    counts: dict[str, int] = {}
    for t in titles:
        for w in set(t.split()):
            if len(w) >= 4:
                counts[w] = counts.get(w, 0) + 1
    return not any(n >= 2 for n in counts.values())
