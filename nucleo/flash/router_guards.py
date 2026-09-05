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

# TASK verbs (es/en, stems) that imply DOING something on the web beyond merely logging in. Deterministic
# (LLM-agnostic): a PURE login ("conéctame a Wallapop", "inicia sesión en Gmail") contains none; "entra
# en mi Gmail y BÓRRAME los correos" does → it is a TASK. Without accents (input is normalized before comparison).
import re as _re
import time as _time

# V2-356 — at MODULE LEVEL, not inside the function: the hidden-coupling ratchet is explicit
# ("more imports inside functions = more hidden cycles; fix it by EXTRACTING, not importing later") and
# there is no cycle to hide here — `nucleo.scheduler` imports nothing from `flash`. The other six lazy imports in
# this file predate this and remain as they were: reducing the debt belongs to whoever touches it, not whoever passes by.
from nucleo import scheduler as _sched
# Re-exported so `router.asks_for_missing_detail` keeps working: it lives apart because it is the one guard
# that must NOT normalize its input (see its own module).
from nucleo.flash.clarifying import asks_for_missing_detail  # noqa: F401 — re-export
# The shared text normalisation both halves of the old file need (2026-09-02 split). It lives apart so that
# neither half has to import the other back — a cycle papered over with a function-local import is exactly
# the hidden coupling this file's ratchet counts. Re-exported: `delivery.py` imports `_norm_txt` from here.
from .text_norm import (  # noqa: F401 — re-export
    _CLAUSE_SPLIT_RE, _DATE_ONLY_WORDS, _STOPWORDS, _content_words, _norm_txt, clause_is_only_a_date,
)

_TASK_VERB_RE = _re.compile(
    r"\b("
    r"borr|elimin|mand|envi|escrib|respond|contest|reenvi|gestion|revis|lee|leer|mira|mir[ae]|orden|compr|"
    r"public|descarg|reserv|anad|agreg|cambi|actualiz|sub[ae]|archiv|marca|mueve|rellen|apunt|"
    # `anul` alongside `cancel` (V2-138, 2026-08-19): they are exact synonyms here and only one was present, so
    # «cancela la suscripción de Spotify» counted as a web task while «ANULA la suscripción de Spotify» did not — the
    # same command, routed to a worker with or without a browser depending on which verb the person chose.
    r"puj|pag|cancel|anul|confirm|solicit|vot|inscrib|contrat|licit|acept|rechaz|"
    # `de baja` / `suscrib` (V2-126, 2026-08-18): «date de baja de Netflix» is THE way to ask for this in
    # Spanish and contained none of the verbs in the list, so it did not count as a web task. Include the full
    # phrase, never standalone «baja» — «estoy de baja» is not an instruction to anyone.
    r"de\s+baja|suscrib|unsubscrib|"
    r"delete|remove|send|write|reply|forward|manage|check|read|buy|post|download|book|add|update|fill|move|"
    r"bid|pay|apply|vote|order|subscribe|purchase|checkout"
    r")", _re.I)


def looks_like_web_task(text: str) -> bool:
    """True if the turn asks to DO a task on a website (not merely log in). Deterministic, LLM-agnostic.
    Used to reclassify an erroneous call to `authenticate_web` (login) → escalate to the browser when there is
    actually a task ("entra en mi Gmail y BÓRRAME los correos")."""
    return bool(_TASK_VERB_RE.search(_norm_txt(text)))


# PURE LOGIN intent ("conéctame a Wallapop", "inicia sesión en mi Gmail", "vincula mi LinkedIn") — with no task
# verb afterward. Deterministic. Mirror of `looks_like_web_task`: guarantees login routing even when the small model
# gets distracted and does not trigger the tool (observed jitter).
# NB (bug 2026-07-23): `conect(?!ad|or)` matched EVERY conjugation of "conectar" except "conectado"/"conector"
# — "¿tienes capacidad para conectarte al cluster?" (a question) or "el agente se conectaba ahí" (third-person
# narration) matched as well and opened a browser login nobody requested (to wallapop.com via the unknown-site
# fallback; see `nucleo.py::_start_web_auth`). It must trigger only the first-person form DIRECTED at zaelar
# ("conéctame"/"conectarme"/"conecta mi cuenta"/"conecta a mi cuenta"), never a reflexive/third-person conjugation
# or a question about capability. The same criterion applies to English and to "vincula"/"vincular".
_LOGIN_INTENT_RE = _re.compile(
    r"\b(conectame|conectarme|conect(?:a|ar)\s+mi\b|conect(?:a|ar)\s+a\s+mi\b|"
    r"inicia(?:r)?\s*sesion|loguea(?:te)?|logue(?:ate)?|vincul[ae](?:me)?\s+mi\b|"
    r"accede a mi|entra en mi|log ?in|sign ?in|connect\s+(?:me|my)\b|autenti[cf])", _re.I)
# Known sites → domain (for the production fallback that opens login without the tool argument).
_KNOWN_SITES = {
    "wallapop": "wallapop.com", "gmail": "google.com", "google": "google.com", "linkedin": "linkedin.com",
    "amazon": "amazon.es", "ebay": "ebay.es", "twitter": "twitter.com", "instagram": "instagram.com",
    "facebook": "facebook.com", "outlook": "outlook.com", "github": "github.com", "idealista": "idealista.com",
    "milanuncios": "milanuncios.com", "netflix": "netflix.com", "spotify": "spotify.com",
}


def looks_like_login_request(text: str) -> bool:
    """True if the turn asks ONLY to log in/connect an account (with no subsequent task) → authenticate_web."""
    return bool(_LOGIN_INTENT_RE.search(_norm_txt(text))) and not looks_like_web_task(text)


# MUSIC streaming services: they connect from the `musica` widget (in-app OAuth), NEVER through a browser login.
# "amazon music"/"apple music"/"youtube music" include the word 'music' so they do NOT override the Amazon
# marketplace or YouTube video (which do use a browser login / are something else).
_MUSIC_SERVICES = ("spotify", "apple music", "youtube music", "tidal", "deezer", "amazon music")
# MESSAGING services that are LINKED INSIDE the `mensajeria` widget (WhatsApp/Telegram by QR, email by app
# password), NEVER through a browser login. Includes email (V2-051): 'conéctame a Gmail/mi correo/Outlook' →
# the mensajeria widget (its connection card), not Chromium.
_MESSAGING_SERVICES = ("whatsapp", "wasap", "telegram", "email", "e-mail", "correo", "gmail", "outlook", "hotmail",
                       "icloud", "imap")


_SHOW_VERB_RE = _re.compile(r"\b(muestra|muestrame|ensena|ensename|abre|abreme|abrir|mostrar|ensenar|ver|"
                            r"visualiza|saca|pon(?:me)? en pantalla)\b")
# Match by STEM (without a final \b): 'anad' covers añade/añadir, 'apunt' covers apunta/apuntar, etc. (after
# accent-stripping by _norm_txt).
_CHANGE_VERB_RE = _re.compile(r"\b(anad|apunt|agreg|marca|quita|borr|elimin|cambi|aplaz|silenci|crea|edit|modific|"
                              r"met[ae]|programa|reserv|pon(?!(?:me|nos|te)?\s*en\s*pantalla)|añad)")
# Verbs that set something RUNNING. Neither showing nor changing data, so `_CHANGE_VERB_RE` never covered them —
# and it should not: nothing here mutates a record. Kept SHORT and stem-based on purpose (`inici` is out: it also
# matches the noun «el inicio», and a false positive here disarms a guard that exists to catch a hallucinated
# `add_meeting`). `pon`/`ponlo` already belong to the change list, with its «en pantalla» carve-out.
_ACTIVATE_VERB_RE = _re.compile(r"\b(arranc|reproduc|empiez|empez|play|start)")


def is_pure_show_request(text: str) -> bool:
    """True if the turn is purely about OPENING/SHOWING a widget (with no intent to CHANGE data or to SET
    something RUNNING). Execution GUARD for widget_data: "abre/muéstrame el widget X" must NEVER execute a
    data-op (the model sometimes slips in an invented 'unhide' action or HALLUCINATES an add_meeting) →
    redirect it to showing the card. Deterministic, Spanish.

    The third class is the fix (V2-595): «muéstrame el primero, ARRÁNCALO» carries a show verb and no *change*
    verb — nothing in this list is about changing data, correctly — so it read as a pure show and the guard
    discarded the `play_item` the model had chosen right. Measured live in session `abe9942b`: the card stayed
    on «No hay ningún vídeo cargado» while the turn said «Aquí lo tienes». Starting playback is neither showing
    a card nor mutating a record: it is ACTIVATION, and an order that names it is not a pure show.
    """
    n = _norm_txt(text)
    if not _SHOW_VERB_RE.search(n):
        return False
    return not (_CHANGE_VERB_RE.search(n) or _ACTIVATE_VERB_RE.search(n))


# Words that ride along with EVERY «abre la mensajería» and name no object of their own: articles,
# possessives, clitics, prepositions and courtesy. They are dropped before asking WHAT the show verb points at.
def show_request_blocks_data_action(text: str, wid: str, action: str) -> bool:
    """True when a PURE show order must be answered by showing the CARD instead of running the data-op the
    model chose (V2-545).

    `is_pure_show_request` says «this is a show order with no intent to change anything». It cannot say what
    the show order POINTS AT, and it never could: «ábreme la mensajería» (the card), «ábreme el Telegram» (a
    lens inside it) and «abre el mensaje de Francisco» (an element inside it) are the same shape. The first
    attempt (V2-544) tried to read the object out of the words, matching them against the widget's manifest
    aliases — and mensajeria's aliases ARE its lens names, so «ábreme el Telegram» classified as the card and
    the card, already on screen, did nothing (measured live 2026-09-01).

    So the question moved off the text and onto the ACTION: the widget declares which of its actions are
    display-only (`"view": true`, see `widgets/actions.py::is_view`). A pure show order may run one of those
    and nothing else. Any other data-op on a pure show is the failure this guard was written for — «abre la
    agenda» hallucinating an `add_meeting` — and still gets redirected to showing the card.

    The caller does not choose between showing and applying: on a view action it does BOTH (bring the card up,
    then apply the view), which is what «ábreme el Telegram» means and dissolves the card-vs-inside ambiguity
    instead of guessing it.

    Fails CLOSED (True = only show) if the catalog cannot be read: a show that does nothing is a smaller
    failure than an invented mutation.
    """
    if not is_pure_show_request(text):
        return False
    try:
        from widgets import runtime as _rt
        if _rt.get(wid) is None:
            return False                      # not a known widget — this guard has nothing to say about it
        from nucleo.flash import frontend as _fe
        return not _fe.action_is_view(wid, action)
    except Exception:  # noqa: BLE001
        return True


def is_music_service(site: str = "", text: str = "") -> bool:
    """True if the requested login is for a MUSIC SERVICE (Spotify…). EXECUTION GUARD for authenticate_web: music
    connects in the `musica` widget (its card), not through the browser → guarantees the invariant EVEN IF model
    routing chooses authenticate_web (the persistent 'conéctame a mi cuenta de Spotify' pattern)."""
    blob = f"{site} {text}".lower()
    return any(s in blob for s in _MUSIC_SERVICES)


_CLOSE_VERB_RE = _re.compile(r"\b(cierr\w*|cerr\w*|ocult\w*|escond\w*|apag\w*|quit\w*|close|hide|turn\s+off)\b")
_DELETE_VERB_RE = _re.compile(r"\b(borr|elimin|delete|remove|deshaz)\w*")
# Negated close: "no cierres / no lo cierres / don't close" — must not count as close (prevents doing the opposite).
_NO_CLOSE_RE = _re.compile(r"\bno\s+(?:me\s+|lo\s+|la\s+|los\s+|las\s+)?(?:cierr\w*|ocult\w*|escond\w*)\b|\bdon'?t\s+close\b")


def looks_like_close(text: str) -> bool:
    """True if the turn asks to CLOSE (hide) a widget, NOT delete it. EXECUTION GUARD for delete_widget (V2-045,
    V2-017 invariant 'cerrar ≠ borrar'): the non-reasoning model sometimes chooses delete_widget for 'cierra el
    widget de X'; deletion is FOREVER and closing is reversible → with a close verb and NO delete verb, it is a
    close. Deterministic and accent-free (the input is normalized). Ignores NEGATION ('no cierres')."""
    n = _norm_txt(text)
    return (bool(_CLOSE_VERB_RE.search(n)) and not _DELETE_VERB_RE.search(n)
            and not _NO_CLOSE_RE.search(n))


# A CLOSE order answered with an OPEN is not obedience (V2-567). Measured live 2026-09-03 19:02:35:
# «Cierra los contactos» → the model called `show_widget(mensajeria)`; contactos only closed because the close
# backstop rescued it, so ONE order produced TWO mutations — a spurious open landing beside the ordered close.
# The probe channel had already written the rule down («un canvas:show ESPURIO en un turno de cerrar SÍ debe
# corregirse a close») and the voice channel never applied it: the show executed anyway. This is GRAMMAR, not
# intent (V2-095): with a close verb and no un-negated open verb anywhere in the turn, a show_widget call
# contradicts the very words that produced it. A compound «cierra X y enséñame Y» keeps its show — the open
# verb licenses it — and «no abras nada, cierra los contactos» does not: a negated open licenses nothing.
_OPEN_VERB_RE = _re.compile(r"\b(abr\w*|muestr\w*|ensen\w*|desplieg\w*|saca\w*|pon\w*|vuelv\w*|open|show|display|bring\s+up)\b")
_NO_OPEN_RE = _re.compile(r"\bno\s+(?:me\s+|lo\s+|la\s+|los\s+|las\s+)?(?:abr\w*|muestr\w*|ensen\w*|saqu\w*|pong\w*)\b"
                          r"|\bdon'?t\s+(?:open|show|display)\b")


def show_contradicts_the_order(text: str) -> bool:
    """True when the turn is a CLOSE order that licenses no open — so a `show_widget` call must be discarded
    (the close backstop still does the closing; nothing is lost, one mutation happens instead of two)."""
    if not looks_like_close(text):
        return False
    n = _norm_txt(text)
    return not (_OPEN_VERB_RE.search(n) and not _NO_OPEN_RE.search(n))


# show_widget execution GUARD (2026-07-17): CREATING a NEW widget is ESCALATED to the generator (code), NOT
# "shown". After the show_widget tool was added, the non-reasoning model chose it for 'créame un widget de X',
# and `identify` returned the wrong EXISTING widget (loose fuzzy match: 'conversor de divisas'→'results').
# Deterministic backstop (the same class as looks_like_close/stop): CREATE verb + 'widget', or 'NEW widget' →
# it is a CREATE, not a show. Natural SYNONYMS for "widget" used by the operator (testing sea, 2026-07-21:
# "créame un PANEL/GADGET" was not detected → the promise backstop did not escalate). ALWAYS gated by a create
# verb → safe (does not capture "el panel de control del coche"). "tarjeta/cuadro/contador" require a preceding
# create verb.
_WIDGET_SYN = r"(?:widget|panel|gadget|tablero|contador|cuadro de mando|mini[- ]?app|tarjeta)"
_CREATE_WIDGET_RE = _re.compile(
    r"(\b(cre[ae]\w*|cr[eé][aá]me\w*|haz\w*|h[aá]zme\w*|hac[eé]\w*|hacer|hag\w*|gener\w*|mont\w*|dise[nñ]\w*|"
    r"constru\w*|prepar\w*|program\w*|make|build|create)\b[^.!?]{0,45}\b" + _WIDGET_SYN + r"\b)"
    r"|(\b" + _WIDGET_SYN + r"\b[^.!?]{0,25}\bnuev[oa]\b)|(\bnuev[oa]\b[^.!?]{0,12}\b" + _WIDGET_SYN + r"\b)", _re.I)


# A WIDGET NAMED AS A DESTINATION IS NOT A WIDGET THAT MUST BE PROGRAMMED (2026-08-13).
#
# Motivating incident: travel research (ferry + hotel + restaurant) ended up in the WIDGET GENERATOR, which
# started writing code for a new widget called `prepara-ricart-viaje` instead of searching. Sole cause: the last
# escalation sentence was «Entrega el resultado MONTADO en el widget results…». `mont\w*` is a create verb and
# `widget` was nine characters away → CREATE. In other words, **asking for the result to be delivered in the
# results sheet diverted the task to the generator**, while that sheet is PRECISELY the delivery surface for all
# research: the failure was on the product's busiest path.
#
# The distinction is not an exception list ([[feedback_no_hardcoded_understand]]) but GRAMMAR: when the widget
# follows a destination preposition («en el widget», «al panel», «dentro de la tarjeta», «into the widget»), it is
# WHERE the result goes, not the thing being built. The preceding verb describes what is placed there. These
# mentions are neutralized BEFORE looking for the create pattern, so a sentence containing BOTH things
# («créame un panel y entrégalo en el widget results») still detects the genuine create.
# Beware the STANDALONE Spanish preposition «a»: it collides with the English article «a» and neutralized
# «build me A WIDGET that tracks my steps», a textbook create. Keep `al` (the contraction actually used:
# «al widget»); «a el widget» is not Spanish.
#
# THE INDEFINITE ARTICLE WAS THE GAP (2026-08-18, the same incident again). The article list contained only
# DEFINITE articles, so «monta el resultado en UN widget del canvas» —the NATURAL way to say «ponlo en una
# tarjeta», and what FlashBrain itself wrote when rephrasing the escalation— was not neutralized and fell into
# the generator again. Grammar does not change with the article: «en un widget» is still WHERE the result goes.
# A genuine create has no preceding destination preposition («créame un widget», «build me a widget»), so
# expanding the list takes nothing away from the create side.
# The ONLY exception is real: «en un widget NUEVO» does request a new one — the destination preposition and
# create coexist, and create wins. A lookahead excludes it from neutralization so `_CREATE_WIDGET_RE` can still
# see its `SYN … nuevo` pattern.
_WIDGET_DEST_RE = _re.compile(
    r"\b(?:en|al|sobre|dentro\s+de|dentro\s+del|hacia)\s+"
    r"(?:el\s+|la\s+|los\s+|las\s+|un\s+|una\s+|unos\s+|unas\s+)?" + _WIDGET_SYN + r"\b(?!\s+nuev[oa]\b)"
    r"|\b(?:into|in|on)\s+(?:the\s+|a\s+|an\s+)?" + _WIDGET_SYN + r"\b(?!\s+nuev[oa]\b)", _re.I)


def looks_like_create_widget(text: str) -> bool:
    """True if the turn asks to CREATE/GENERATE a NEW widget (→ escalate to the generator), rather than show an
    existing one or DELIVER something inside one. show_widget execution GUARD: if the model chooses show_widget
    for a CREATE, redirect it to escalation."""
    t = _WIDGET_DEST_RE.sub(" <destino> ", _norm_txt(text))
    return bool(_CREATE_WIDGET_RE.search(t))


# PROMISE WITHOUT ACTION (2026-07-19, testing sea): faced with POLITE/indirect/subjunctive phrasing
# ('¿podrías…?', 'deberías…', 'sería genial que…', 'me haría falta…'), the non-reasoning model CHATS a promise
# ('voy a…', 'aquí lo tienes', 'me pongo con ello', 'ahora te lo abro') WITHOUT calling the tool. This is the #1
# cause of "says it does it but does not," and patching verb by verb does NOT fix it (each conjugation is another
# case). UNIFIED backstop gated by the promise in zaelar's REPLY (it committed) → re-derive intent with the
# deterministic classifiers.
_PROMISE_RE = _re.compile(
    r"\b(voy a|te lo|te la|te los|te las|aqui (?:lo|la|los|las) tienes|aqui tienes|ahora (?:mismo|te|lo|la)|"
    r"me pongo con|me pongo a|lo hago|la hago|enseguida|en un momento|un momento|dame un momento|lo abro|"
    # V2-132 — measured on the `find-theatre-tickets` transcript: «Me pongo a buscarte las dos entradas» and
    # «Todavía estoy con ello» returned False, so the promise backstop was never even considered. They are the
    # PLAINest ways to say «estoy en ello», and exactly what appears when no task is actually running.
    r"estoy con ello|sigo con ello|sigo buscando|sigo con la busqueda|estoy en ello|"
    r"te aviso en cuanto|te lo confirmo en cuanto|en cuanto (?:lo|la) tenga|"
    # First-person action with or WITHOUT a clitic: «te muestro el reloj» / «te abro X» / «te enseño X» /
    # «te saco X» (testing-sea bug 2026-07-21: the gate required «te LO muestro» → «te muestro el reloj» slipped
    # through and the show was not re-derived).
    r"te (?:(?:lo|la|los|las) )?(?:abr|muestr|ense[nñ]|ensen|sac)\w*|"
    r"voy a (?:abrir|mostrar|crear|poner|buscar)|"
    r"estoy (?:abriendo|creando|poniendo|buscando))\b")
# MUSIC promise in the reply ('voy a poner algo de rock', 'te pongo música') → the backstop plays it.
_PROMISE_MUSIC_RE = _re.compile(r"\b(poner|pongo|pondre|reproduc\w*)\b[^.!?]{0,20}\b(m[uú]sica|canci|rock|jazz|algo de)\b|"
                                r"\b(m[uú]sica|canci|rock|jazz)\b[^.!?]{0,15}\b(ahora|para ti|un momento)\b")


def promises_music(reply: str) -> bool:
    return bool(_PROMISE_MUSIC_RE.search(_norm_txt(reply)))
# STRICT SHOW verbs for the promise backstop: ONLY unambiguous ones (without 'pon'/'sube'/'ver' → they collide
# with 'pon música'/'va a poner el tiempo'/'a ver si…'). Covers 'abrir/mostrar/enseñar/sacar' in any conjugation.
_SHOW_STRICT_RE = _re.compile(r"\b(abr\w*|muestr\w*|ensen\w*|ense[nñ]\w*|saca\w*)\b")


# V2-534's open item #1 (2026-09-01): a NEGATED clause is not a promise. The rule and its clause arithmetic
# live in `nucleo/flash/negation.py` (the architecture ratchet asked for a module, not a taller ceiling) and
# are re-exported here so both promise gates keep one import path.
from nucleo.flash.negation import clause_negated, unnegated_match  # noqa: F401 — re-export


def promises_action(reply: str) -> bool:
    """True if zaelar's REPLY promises a first-person action (it committed to doing something)."""
    return unnegated_match(_PROMISE_RE, _norm_txt(reply))



def looks_like_show_strict(text: str) -> bool:
    """Unambiguous SHOW verb (abrir/mostrar/enseñar/sacar), NOT create, NOT close — for the promise backstop."""
    n = _norm_txt(text)
    return (bool(_SHOW_STRICT_RE.search(n)) and not looks_like_create_widget(text)
            and not looks_like_close(text))


# TASK that REQUIRES a browser/worker (real marketplace or in-depth report/research). ONLY for the promise
# backstop (testing sea 2026-07-21: «voy a buscar el sofá en Milanuncios» / «te preparo el informe» stayed in
# chat). Gated by the reply's promise → safe. Site names = strong NAVIGATION signal (not a one-off web_search).
_MARKETPLACE_RE = _re.compile(
    r"\b(idealista|coches\.?net|autoscout|wallapop|milanuncios|fotocasa|vibbo|amazon|ebay|"
    r"segundamano|habitaclia|pisos\.com)\b", _re.I)
_REPORT_RE = _re.compile(r"\b(informe|estudio|comparativa|investig\w*)\b[^.!?]{0,40}\b(a fondo|compar\w*|detallad\w*|"
                         r"mejor\w*|opcion\w*)\b|\b(compar\w*|investig\w*)\b[^.!?]{0,30}\b(a fondo|entre|los|las)\b", _re.I)


def looks_like_escalate_task(text: str) -> bool:
    """True if the TEXT describes an errand requiring a worker/browser (named marketplace, in-depth report/research,
    or a TRANSACTIONAL category from the site catalog). Use it ONLY after confirming a promise in the reply
    (the backstop gate) — not as the primary router.

    V2-132: the third branch is not a new verb list but the SAME source that already decides the task `kind` in
    `dispatch._classify_kind` (`site_catalog.TRANSACTIONAL_CATEGORIES`). Booking a table, hotel night, flight,
    or tickets requires entering a real site; this guard not knowing that while the `kind` classifier did is
    exactly how two components deciding the same thing end up disagreeing."""
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


# SEARCH/NAVIGATION verbs for the marketplace guard (busca/mira/enséñame/encuentra/ver/ojea). A NAMED resale
# site + one of these = ENTER and browse the catalog (not a one-off fact, not an "I can't").
_MKT_VERB_RE = _re.compile(
    r"\b(busc\w*|b[uú]scame|mir[ae]\w*|ense[nñ]\w*|ens[eé][nñ]\w*|muestr\w*|encuentr\w*|encu[eé]ntr\w*|"
    r"ojea\w*|vistazo|quiero ver|ver si|encontrar)\b", _re.I)


def looks_like_marketplace_nav(text: str) -> bool:
    """True if the turn asks to BROWSE a named marketplace (site + search/view verb). High-precision deterministic
    guard: a passing mention ('me encanta comprar en Amazon') does not trigger it — search intent is required.
    → escalate to the browser even if the model chose web_search / chat / show."""
    n = _norm_txt(text)
    return bool(_MARKETPLACE_RE.search(n) and _MKT_VERB_RE.search(n))


# MODIFYING a widget's CODE/appearance = generator work (escalate), NOT a data-op or an "I can't". RELIABLE
# non-reasoning failure mode (testing sea 2026-07-21, modify 1-7/8 depending on run: declines, performs
# widget_data, or shows). High-precision deterministic guard: change verb + CODE/style/structure property + the
# word widget (or synonym). Does not capture a VALUE data-op (mark done, change a title/value) — only
# color/background/style/design/column/field/section/button/size…, which are CODE.
_MODIFY_VERB_RE = _re.compile(
    r"\b(cambi\w*|modific\w*|edit\w*|a[nñ]ad\w*|agreg\w*|incorpor\w*|met\w*|pon\w*|p[oó]n\w*|quit\w*|"
    r"actualiz\w*|redise[nñ]\w*|reestructur\w*|reorganiz\w*)\b", _re.I)
_CODE_PROP_RE = _re.compile(
    r"\b(color\w*|fondo|estilo\w*|dise[nñ]o|apariencia|columna\w*|campo\w*|secci[oó]n\w*|tama[nñ]o|"
    r"bot[oó]n\w*|layout|formato|encabezad\w*|fuente|tipograf\w*|borde\w*|margen\w*|tema)\b", _re.I)
_WIDGET_SYN_RE = _re.compile(r"\b" + _WIDGET_SYN + r"\b", _re.I)


def looks_like_modify_widget(text: str) -> bool:
    """True if the turn asks to CHANGE a widget's CODE/appearance (color/column/style… + 'widget') → escalate to
    the generator. It is not a data-op (mark/move an item) or an 'I can't'. High-precision deterministic guard."""
    n = _norm_txt(text)
    return bool(_MODIFY_VERB_RE.search(n) and _CODE_PROP_RE.search(n) and _WIDGET_SYN_RE.search(n)
                and not looks_like_create_widget(text))


_RULE_REMOVAL_RE = _re.compile(
    r"\b(olvida|olvidate|quita|elimina|borra|anula|retira|deja de aplicar|ya no (?:hace falta|quiero|apliques))\b")


def looks_like_rule_removal(text: str) -> bool:
    """True if the turn asks to REMOVE a user rule ('olvida esa regla', 'ya no hace falta que seas tan breve')
    rather than add one. GUARD for the set_style_directive handler (V2-046 A1): the SAME tool adds or removes;
    this deterministic guard decides the direction from the turn text, not the LLM."""
    n = _norm_txt(text)
    return bool(_RULE_REMOVAL_RE.search(n))


# EMPTY item reference or a BARE DEICTIC PRONOUN ("lo", "eso", "esto", "it", "that"…) — with no anchoring noun.
# In a widget data-op this means the model does NOT know which item it targets: the antecedent ("cancélalo") is
# in the CONVERSATION, not the widget. GRAMMATICAL pronoun recognition, NOT a routing-verb table.
_BARE_REF_RE = _re.compile(
    r"^(?:lo|la|le|los|las|les|eso|esto|esa|ese|esas|esos|aquello|aquella|aquel|aquellos|aquellas|"
    r"esta|este|estas|estos|it|that|this|them|those|these)$")


def looks_like_bare_ref(ref: str) -> bool:
    """True if the item reference is EMPTY or a bare deictic pronoun (without a noun). In a data-op this indicates
    the model did not anchor the item — its antecedent is in the recent conversation, not the widget. GUARD for
    the widget_data handler (2026-07-21, case «hay que cancelarlo» after «¿qué día tengo la ITV?»)."""
    n = (ref or "").strip().lower().strip("¿?¡!.,;:")
    return not n or bool(_BARE_REF_RE.match(n))


def is_messaging_service(site: str = "", text: str = "") -> bool:
    """True if the requested 'login' is WhatsApp/Telegram. EXECUTION GUARD for authenticate_web (mirror of
    is_music_service): these accounts are LINKED by QR INSIDE the `mensajeria` widget, NOT via browser login →
    'conéctame a WhatsApp' / 'abre WhatsApp' redirects to [[show:mensajeria]] (where the QR is), not Chromium."""
    blob = f"{site} {text}".lower()
    # is_music_service already captures 'youtube music'/'amazon music'; only pure messaging is handled here.
    return any(s in blob for s in _MESSAGING_SERVICES)


# DETERMINISTIC backstop for STOPPING a worker (§v3·M). Requires a stop verb AND a WORK reference (process/
# widget/search/task/creation/"eso"/"todo"). Used only when live workers EXIST.
# Hardening history (killing is IRREVERSIBLE → strong bias against killing when uncertain):
#  · demo 2026-07-14: ambient conversation ("…necesita PARA poder acceder… CREANDO su memoria…", 500+ chars)
#    killed a worker → length cap (a long paragraph is never an order).
#  · post-P1/P2 test: the cap does NOT save a SHORT sentence with PREPOSITIONAL "para" — "hazme un widget PARA
#    el tiempo", "necesito un widget PARA la agenda" (4/8 false positives). "para" is both a stop verb and the
#    most common preposition. Two new defenses: (a) if the turn STARTS by requesting something (quiero/hazme/
#    crea/abre/muéstrame…), it is NOT a stop; exit immediately; (b) "para" counts as an IMPERATIVE only at the
#    START of the turn with a REAL stop complement (deictic eso/ya/todo, "de <verb>", or article+WORK-word) —
#    never "para <noun phrase>" such as "para el tiempo/la agenda/el finde", nor "para" mid-sentence ("eso ES
#    para la búsqueda de piso"). The other verbs (detén/cancela/deja de/aborta/stop/kill) are unambiguous and unchanged.
_STOP_WORK = (r"eso|ese|esa|esto|proceso|procesos|tarea|tareas|widget|widgets|busqueda|busca|buscar|buscando|"
              r"creacion|crear|creando|modific|navegador|workers?|estudio|investig|"
              r"lo que estas haciendo|lo que haces|todo")
_STOP_WORK_RE = _re.compile(r"\b(" + _STOP_WORK + r")\b")
# UNAMBIGUOUS stop verbs (excluding "para", handled separately because it is ambiguous).
_STOP_VERB_STRONG_RE = _re.compile(r"\b(deten(?:te|lo|la|los|las)?|cancela(?:r|lo|la|los|las)?|"
                                   r"aborta(?:r|lo|la)?|deja de|stop|kill)\b")
# IMPERATIVE "para": at the start of the turn (after punctuation), + deictic / "de <verb>" / article+work-word.
_STOP_PARA_RE = _re.compile(
    r"^[¿¡\s]*para(?:d|lo|la|los|las)?\s+(?:eso|esto|ese|esa|ya|de\s+\w+|"
    # MASS stop: "para todo" / "para todas las tareas" / "para todos los procesos|workers" (2026-07-17: the
    # backstop swallowed "para todas las tareas" and stop failed silently). "tod@s" only when TERMINAL or followed
    # by los/las+work-word → does NOT capture "para todo el mundo es difícil" (pre-existing false positive) or
    # "para toda la comida".
    r"tod[oa]s?(?:\s+l[oa]s\s+(?:" + _STOP_WORK + r"))?(?=[\s.!?]*$)|"
    r"(?:el|la|los|las|ese|esa|este|esta|mi)\s+(?:" + _STOP_WORK + r"))\b")
# REQUEST verbs at the start → the turn REQUESTS something, rather than ordering a stop (defense (a)).
_REQUEST_START_RE = _re.compile(
    r"^[¿¡\s]*(?:me\s+)?(?:puedes|podrias|querria|quiero|quisiera|necesito|hazme|haz\b|hazlo|dame|"
    r"crea|crear|crees|creame|genera|generame|monta|montame|construye|abre|abreme|pon|ponme|prepara|"
    r"preparame|muestra|muestrame|ensename|ensename|busca|buscame|anade|agrega|apunta|programa|"
    r"me\s+gustaria|quiero\s+que|puedes\s+hacerme)\b")
_STOP_MAX_WORDS = 12          # a real stop order easily fits; an explanation/long paragraph is not an order
_STOP_MAX_CHARS = 90


def looks_like_stop_work(text: str) -> bool:
    """True if the turn is an ORDER to stop a background process (not silence TTS). Deterministic, Spanish/English.
    Deliberately CONSERVATIVE (killing is irreversible): only SHORT turns that ORDER a stop. A request
    ("hazme un widget para X") or a long paragraph NEVER triggers it (fine-grained killing remains with stop_worker)."""
    n = _norm_txt(text)
    if len(n) > _STOP_MAX_CHARS or len(n.split()) > _STOP_MAX_WORDS:
        return False
    if _REQUEST_START_RE.match(n):        # (a) the turn starts by REQUESTING something → it is not a stop
        return False
    if _STOP_VERB_STRONG_RE.search(n) and _STOP_WORK_RE.search(n):
        return True                       # detén/cancela/deja de/aborta + work reference (unambiguous)
    return bool(_STOP_PARA_RE.match(n))   # (b) "para <actual stop complement>" AT THE START


def login_site(text: str) -> str:
    """Best effort: extract the domain of the site to log into from the text (for the production login fallback)."""
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


# ── A FACT ABOUT THE WORLD, ANSWERED WITH NO SOURCE (V2-210) — extracted to `answer_guards.py` (ratchet,
# 2026-09-03, V2-567). Historical names stay as ALIASES; the measured story lives with the code.
from nucleo.flash.answer_guards import (  # noqa: F401 — re-export, not a local use
    _EXTERNAL_FACT_RE, _FIGURE_RE, _OWN_THING_RE, a_bare_ack_answers_a_question,
    an_empty_wait_answers_a_question, answer_needs_a_source,
)

# ── the PROMISED-REMINDER guards (moved to reminder_guards.py, 2026-09-02 ratchet pass) ───────────────────────
# 26 guards that form a closed set: they reference each other and the shared text helpers above, and nothing
# that stayed here uses any of them — which is why the dependency runs one way and nothing is imported back.
# Re-exported so every existing call site keeps working unchanged (`router.py` re-exports several of these by
# name from this module, and the tests reach them as `router_guards.X`): the same compatibility contract this
# file's own docstring describes for the split that created it.
from .reminder_guards import (  # noqa: F401 — re-export, not a local use
    _AGENT_IMPERATIVE_RE, _DATE_LEAD_RE, _FIRST_PERSON_DUTY_RE, _NOTE_ASK_RE, _NOTE_VERB_RE, _PROMPT_S,
    _REMIND_ASK_RE, _REMIND_DET, _REMIND_NOUN, _REMIND_VERB_RE, _asked_reminder_moment, _longest_pending_min,
    _reminder_prompt, already_in_agenda, clause_now_or_ask, commitment_clause, commitment_from_window,
    dated_note_backstop, dated_reminder_backstop, holding_line, note_asked_in_window,
    promises_a_dated_reminder, reminder_before, safe_reminder_prompt, safe_reminder_schedule, strip_note_lead,
)
