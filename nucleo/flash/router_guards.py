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
    r"puj|pag|cancel|confirm|solicit|vot|inscrib|contrat|licit|acept|rechaz|"
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
_WIDGET_DEST_RE = _re.compile(
    r"\b(?:en|al|sobre|dentro\s+de|dentro\s+del|hacia)\s+(?:el\s+|la\s+|los\s+|las\s+)?" + _WIDGET_SYN + r"\b"
    r"|\b(?:into|in|on)\s+(?:the\s+)?" + _WIDGET_SYN + r"\b", _re.I)


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
    r"me pongo con|lo hago|la hago|enseguida|en un momento|un momento|dame un momento|lo abro|"
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
    """True si el TEXTO describe una gestión que exige worker/navegador (marketplace nombrado o informe/investigación
    a fondo). Úsalo SOLO tras confirmar una promesa en la respuesta (gate del backstop) — no como router primario."""
    n = _norm_txt(text)
    return bool(_MARKETPLACE_RE.search(n) or _REPORT_RE.search(n))


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
