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


def _norm_txt(text: str) -> str:
    import unicodedata as _ud
    n = _ud.normalize("NFKD", text or "")
    return "".join(c for c in n if not _ud.combining(c)).lower()


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


def is_pure_show_request(text: str) -> bool:
    """True if the turn is purely about OPENING/SHOWING a widget (with no intent to CHANGE data). Execution GUARD
    for widget_data: "abre/muéstrame el widget X" must NEVER execute a data-op (the model sometimes slips in an
    invented 'unhide' action or HALLUCINATES an add_meeting) → redirect it to showing the card. Deterministic, Spanish."""
    n = _norm_txt(text)
    return bool(_SHOW_VERB_RE.search(n)) and not _CHANGE_VERB_RE.search(n)


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


# V2-534's open item #1 (2026-09-01): a NEGATED clause is not a promise. Measured over every firing of the
# promise gate in the operator's sessions (2026-08-17 -> 2026-09-01): four of ten were «ahora mismo NO tengo
# ninguna tarea corriendo» and siblings — the time adverb matched and the negation sitting right next to it
# was ignored. The rule is STRUCTURAL (a negator inside the SAME clause as the matched span), never a phrase
# list (V2-095 measured what hand-tuning those lists costs). Clause-bounded on purpose, in both directions:
# «No, ahora mismo lo miro» still promises (the «no» answers the PREVIOUS clause), and «me pongo con ello,
# no te preocupes» is not un-promised by its neighbour. `nada` is deliberately NOT a negator here: «en nada
# te lo miro» is a promise, and losing one is the expensive direction (six measured minutes of silence).
_NEGATOR_RE = _re.compile(r"\b(no|ni|tampoco|nunca|jamas|ningun\w*)\b")
_CLAUSE_BREAKS = ".,;:!?¿¡()\n"


def clause_negated(normalized: str, start: int, end: int) -> bool:
    """True if the clause containing [start:end) of an already-normalized text carries a negator."""
    lo = max([normalized.rfind(c, 0, start) for c in _CLAUSE_BREAKS] + [-1]) + 1
    his = [i for i in (normalized.find(c, end) for c in _CLAUSE_BREAKS) if i != -1]
    hi = min(his) if his else len(normalized)
    return bool(_NEGATOR_RE.search(normalized[lo:hi]))


def unnegated_match(rx, normalized: str) -> bool:
    """Any match of `rx` whose own clause is NOT negated. The shared mechanic for the promise gates —
    `promises_action` here and `promise_backstop.committed` in the voice provider read the same rule, because
    two copies of this decision is how the last one drifted (V2-252's lesson, applied before it repeats)."""
    return any(not clause_negated(normalized, m.start(), m.end()) for m in rx.finditer(normalized))


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


# PROMISE OF A DATED NOTICE (V2-146). «apúntame que el jueves… y recuérdamelo el miércoles» ended with
# `scheduled_jobs.created` EMPTY: the model promised in prose —«te avisaré el miércoles»— and emitted no tag.
# The cron runner works (V2-134), and the prompt asks explicitly; the backstop was missing.
#
# The boundary separating it from the V2-132/V2-143 family: «te aviso EN CUANTO lo tenga» is a worker finishing,
# not a scheduled notice. This case is distinguished by a resolvable MOMENT — and `scheduler.parse_when` decides
# whether one exists, returning "" for any expression that is not unambiguous.
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
    # and the notice half resolved to nothing. The verdict read "confirmed an action it never performed," and the
    # ambiguity it tripped over is not one a person would perceive: the day belongs to whichever verb it follows.
    # So the operator's own turn gets read positionally too, and only then whole (which is what preserves every
    # case that already worked — one date anywhere still resolves exactly as before).
    return (_sched.parse_when(n[m.end():])
            or _asked_reminder_moment(operator_text)
            or _sched.parse_when(operator_text))


# DATED NOTE (V2-159). Sibling of the notice backstop, for the OTHER half of the same request. The prompt says so
# explicitly —"if the commitment has a date, also add it to the agenda… these are two different things, the entry
# and the notice, and the operator asks for both"— yet the run ended with the cron set and NO appointment: «Te apunto la
# renovación del seguro del coche para el jueves» with no data-op behind it.
_NOTE_VERB_RE = _re.compile(
    r"\b(te\s+(?:lo\s+|la\s+)?apunto|apunto|te\s+(?:lo\s+|la\s+)?anoto|anoto|"
    r"queda\s+(?:apuntad|anotad)[oa]|lo\s+apunto|lo\s+anoto|"
    r"(?:anado|pongo|meto)\w*\s+(?:a|en)\s+tu\s+agenda|i'?ll\s+note\s+(?:it|that)\s+down)\b", _re.I)
# Where the date STARTS within the sentence — used both to cut the title before it and avoid dragging it into the
# appointment text.
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
        # V2-176: the request to write it down does not EXPIRE because the operator needed another turn to get
        # the date right. Measured: «Apúntalo» was in turn 3, turn 4 only corrected the day, and the agenda stayed
    # empty (`n_after: 1`, only the notice) while zaelar said "I've added it to your agenda."
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


# ── V2-167 · a notice arrives BEFORE the event it announces ───────────────────────────────────────────────
#
# The operator's OWN ask, which is not the same vocabulary as the agent's promise (`_REMIND_VERB_RE`, above):
# he says «recuérdamelo», the agent says «te aviso». Both halves live in the same sentence and telling them
# apart is what lets the commitment be read separately from the notice.
# V2-167 round 12 (2026-08-20 12:39) — the operator requested the notice in the SUBJUNCTIVE: «Que me AVISES el
# miércoles 26 por la mañana». This pattern knew only the indicative (`me avisas`), so it missed the request; the
# notice day could not be read positionally, and the whole sentence went to `parse_when` —which sees «jueves 27»
# and «miércoles 26» and rightly refuses— leaving `scheduled_jobs.created` EMPTY while zaelar said «lo dejo
# apuntado y programo el aviso» and finished with «Ya lo tienes todo listo».
#
# This is EXACTLY the failure this module already suffered in V2-151 and documented above: the first pattern
# spelled out one specific variant, while the real run used the neighboring one. Therefore this is broadened by
# MORPHOLOGY (verb stem + ending), not by adding today's phrase to a list: requesting a notice after «que» calls
# for the Spanish subjunctive; it is the natural form, not an unusual variant.
#
# The optional pronoun (`me lo avises` / `me la recuerdes`) is included for the same reason. The stem remains
# paired with its ending instead of a loose `\w*`, so NEGATION («no me avises») does not pull in the pattern.
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
    V2-133 drew ("the fix cannot be to remove them; the filler must avoid claiming a stage"), and
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
            # In practice the minute count increases, so two consecutive waits are not identical; but if the
            # clock has not advanced a minute, rotate instead of repeating word for word — exactly the defect
            # this fixes, and one that must not be reintroduced through the back door.
            if not recent or waited != recent[-1]:
                return waited
    for line in lines:                      # exhaust the variants BEFORE reusing any of them
        if line not in recent:
            return line
    for line in lines:                      # and if all have already been said, at least not the immediately previous one
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
    reads the operator his own apology back. The judge called it "a useless scheduled notice," which is exactly
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
    # firing the agent would have been asked to SCHEDULE the reminder all over again — the "WHAT gets lost"
    # this case has been dragging since V2-134, finally visible in the field that causes it.
    # V2-176: the WHAT may have been said three turns earlier while this turn only fixes the DATE. Without a
    # window it behaves exactly as before, so no existing caller changes behavior.
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


def safe_reminder_schedule(schedule: str, reply: str, operator_text: str = "") -> str:
    """WHEN the model tag's notice fires — corrected if it says TODAY while the conversation requested another day.

    Sibling of `safe_reminder_prompt`, for the other field of the same tag and for the same reason: V2-214
    protected the `prompt` because "the backstop already composed the safe form, while the model's tag came in raw
    through the other door," but left `schedule` entering just as raw.

    Measured in `remember-and-remind-deadline` (2026-08-27): the operator said «el jueves tengo que renovar el
    seguro… recuérdamelo el miércoles»; the turn prompt included the dated list of upcoming days —«wednesday
    2026-09-02»— yet the job had `schedule "2026-08-27 08:08"`: **TODAY, five minutes after the conversation**,
    six days before the event. A notice that fires on the next turn is noise, not a reminder; and a misdated
    notice is not noticed until the day it fails to ring (V2-121).

    Neither parser nor backstop failed — both resolve «el miércoles» to `2026-09-02 09:00`, as verified. The model
    wrote the date despite having the correct one in front of it, and this is where code answers that rather than
    more prompting: when correct behavior is deterministic, code guarantees it (V2-305).

    THE SCOPE IS DELIBERATELY NARROW because the evidence is one case: correction occurs only when **both** are
    true — the tag fires TODAY, and the deterministic resolver has an UNAMBIGUOUS answer on another day. A future
    date is left untouched even if it differs from the resolver's belief: the model may understand the request
    better than a rule, and `parse_when` already stays silent on ambiguity. What cannot be right is «ahora mismo»
    when the person named a day.
    """
    spec = (schedule or "").strip()
    if not spec:
        return spec
    try:
        # With the REPLY available, position wins («lo que va después de "te avisaré"»). Without it —the provider
        # path executes the tag while generation is still underway— use the OPERATOR's turn, which is the
        # authority anyway: the operator said «recuérdamelo el miércoles».
        pedido = (promises_a_dated_reminder(reply or "", operator_text or "")
                  if (reply or "").strip() else _asked_reminder_moment(operator_text or ""))
        if not pedido:
            return spec                       # without an unambiguous answer, correct nothing
        # NORMALIZE first: `scheduler.create` understands only MACHINE forms, so a spoken expression that does
        # resolve («el próximo miércoles por la tarde») is translated here — as the worker path already does
        # (`worker_api`, chaining both parsers); omitting this left the notice uncreated.
        mio = _sched.parse_schedule(spec)
        if not mio:
            _hablado = _sched.parse_when(spec) or ""
            if _hablado and _sched.parse_schedule(_hablado):
                spec, mio = _hablado, _sched.parse_schedule(_hablado)
        suyo = _sched.parse_schedule(pedido)
        if not suyo:
            return spec
        if not mio:
            # The model's date does NOT parse, or has passed (`parse_schedule` rejects the past). Without a
            # correction no job is created and the notice does not exist, so the resolver competes with nothing.
            return pedido
        if str(mio.get("type") or "") != "once":
            # A RECURRING schedule («every 30m», «0 9 * * 3») naturally fires today; that is not the defect:
            # the model specified a cadence, not a date. Correcting it would turn a weekly notice into a one-off.
            return spec
        # ONE CLOCK. `localtime()` without an argument reads the system clock underneath and does NOT pass through
        # `time.time()`, so this function read two clocks: one to parse the date and another to decide what today
        # is. They coincide in production, changing nothing; what breaks is MEASUREMENT — on 2026-08-28 its two
        # tests failed at midnight, having passed until then by calendar coincidence rather than a frozen clock.
        # Passing the instant makes it measurable from one place.
        hoy = _time.strftime("%Y-%m-%d", _time.localtime(_time.time()))
        if _time.strftime("%Y-%m-%d", _time.localtime(mio.get("next_run") or 0)) != hoy:
            return spec                       # does not fire today: not the measured defect
        if _time.strftime("%Y-%m-%d", _time.localtime(suyo.get("next_run") or 0)) == hoy:
            return spec                       # the conversation ALSO requested today: the model was right
        return pedido
    except Exception:  # noqa: BLE001
        return spec


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
