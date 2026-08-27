"""widgets/navegador/walls.py — QUÉ ES UN MURO, definido una vez y leído por sus tres testigos (V2-358).

Extraído de `tasks.py` el 2026-08-27 al pagar el trinquete de arquitectura (V2-358 añadía el tercer hermano
—el status— y el fichero cruzó el umbral de nacimiento de la tabla). Es un concern cohesivo y PURO: tres
clasificadores (URL / cuerpo / status HTTP) con sus agujas medidas, sin una gota de estado del registro de
tareas. `tasks.py` conserva re-exports con los nombres históricos: los llamantes (`act_api`, `owner`, los
tests) siguen nombrándolos desde allí, y la historia de los muros golpeados (`t["walls"]`) sigue siendo del
registro, que es de quien es.
"""
from __future__ import annotations


_WALL_URL_NEEDLES = (
    ("chrome-error://", "la página no llegó a cargar"),
    ("/sorry/index", "el buscador pidió verificación anti-robot"),
    ("/recaptcha/", "la página pidió resolver un captcha"),
    ("chal_t=", "el sitio interpuso una verificación anti-robot"),
    ("__cf_chl", "el sitio interpuso una verificación anti-robot"),
)

# The site's OWN error landing page — a wall too, and one the browser reports as a perfectly successful
# navigation, because it IS one: status 200, real host, page renders. Measured on
# `cancel-subscription-before-charge__es` (V2-176 round 3): the task ended on
# `https://www.netflix.com/NotFound?prev=…` and zaelar told the operator, twice, that «la página no se ha
# abierto del todo» and then that the login page was ready for him to type his credentials into. The judge
# called it gaslighting; it was not — nothing in the state said the page was an error, so «still loading» was
# the most reasonable thing left to say.
#
# Matched as a whole PATH SEGMENT, never as a substring: «/notfound» is an error page and
# «/articles/404-ways-to-cook-eggs» is not. Query strings are excluded on purpose — the measured URL carries
# `?prev=https://www.netflix.com/es-es/ContactUs`, so a substring match over the whole URL would fire on the
# perfectly good page it came FROM.
_ERROR_PATH_SEGMENTS = frozenset({"notfound", "not-found", "404", "page-not-found", "pagenotfound",
                                  "errorpage", "error-404", "404.html", "not_found"})

# A wall served in the BODY, with a perfectly ordinary URL and a 200 status. V2-167 left this half open on purpose
# after measuring it on a REAL run of the theatre case: `entradas.com` answered the event page with an Akamai
# «Access Denied» bot-detection page. The URL said nothing, `wall_reason()` saw nothing, the card never opened and
# the operator was never told — the worker read it off the snapshot and re-routed by itself, which is why the task
# did not get stuck and why the hole stayed invisible.
#
# This is a SECOND predicate over a DIFFERENT input, not a widening of the first one — `wall_reason` still answers
# only about URLs. The caller decides which inputs it holds; the owner's tab holds both.
#
# The fragility the initiative warned about is «declaring a wall on any page that happens to mention the word», and
# the guard against it is LENGTH, not a longer needle list: a bot wall is a nearly empty page (Akamai's is ~200
# chars, Cloudflare's interstitial ~400), while an article that talks about access being denied is thousands. So a
# needle only counts inside a page too short to be content. Measured on the run above: the wall page was 214 chars.
_WALL_BODY_MAX_CHARS = 1200

# How much text a caller must read before asking. It is deliberately LARGER than the gate above, and single-sourced
# here because getting it wrong is silent and inverts the guard: read exactly 1200 chars of a 50k-char article and
# the text arrives «short», so the length gate — the whole defence against false positives — passes every page.
WALL_BODY_PEEK_CHARS = _WALL_BODY_MAX_CHARS + 400
_WALL_BODY_NEEDLES = (
    ("access denied", "el sitio bloqueó el acceso (te tomó por un robot)"),
    # V2-352 — the DataDome-style Spanish block, measured live on coches.net (2026-08-27): HTTP 403, SAME url,
    # body «Algo en tu navegador nos hizo pensar que eres un bot». None of the needles below covered that
    # phrasing, so the wall was eaten in silence: round 14 burned 7 navigations and 189 s before the worker
    # DEDUCED the block from screenshots (~14 s per look), and the sheet ended with 0 items.
    ("eres un bot", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("acceso denegado", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("permission to access", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("you have been blocked", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("request blocked", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("unusual traffic", "el sitio pidió verificación anti-robot"),
    ("tráfico inusual", "el sitio pidió verificación anti-robot"),
    ("trafico inusual", "el sitio pidió verificación anti-robot"),
    ("are you a robot", "el sitio pidió verificación anti-robot"),
    ("not a robot", "el sitio pidió verificación anti-robot"),
    ("no soy un robot", "el sitio pidió verificación anti-robot"),
    ("verify you are human", "el sitio pidió verificación anti-robot"),
    ("verifica que eres humano", "el sitio pidió verificación anti-robot"),
    ("checking your browser", "el sitio pidió verificación anti-robot"),
    ("captcha", "la página pidió resolver un captcha"),
    ("enable javascript and cookies", "el sitio exigió javascript y cookies para dejarnos pasar"),
    ("too many requests", "el sitio cortó por exceso de peticiones"),
    ("demasiadas peticiones", "el sitio cortó por exceso de peticiones"),
)


def body_wall_reason(text: str) -> str:
    """Short, operator-facing reason why this PAGE TEXT is a WALL, or '' when it is an ordinary page.

    Sibling of `wall_reason()`, never a replacement: that one answers about a URL, this one about the text the tab
    is showing. Only pages too short to be content are considered at all (see `_WALL_BODY_MAX_CHARS`) — the needles
    alone would fire on any article that discusses bot detection.
    """
    t = " ".join((text or "").split()).lower()
    if not t or len(t) > _WALL_BODY_MAX_CHARS:
        return ""
    for needle, reason in _WALL_BODY_NEEDLES:
        if needle in t:
            return reason
    return ""


def status_wall_reason(status: int) -> str:
    """Short, operator-facing reason why this HTTP STATUS is a WALL, or '' for an ordinary page.

    Third sibling (V2-358), and the one no needle can miss: the block travels in the response code even when
    the site changes the words. Measured on coches.net (2026-08-27): the same 403 arrives with two different
    bodies — «…nos hizo pensar que eres un bot» (caught by V2-352's needle) and a bare «Ups! Parece que algo
    no va bien…» (caught by nothing) — and in round 08:03 the worker re-tried the identical URL four times
    with no wall and no alternatives, ending the round with 0 candidates. Only the two anti-bot codes count:
    a 404 is the error-path segments' business, and a 500 is the site failing, not the site refusing us."""
    if status == 403:
        return "el sitio nos ha bloqueado el acceso (respuesta 403)"
    if status == 429:
        return "el sitio cortó por exceso de peticiones (respuesta 429)"
    return ""


def host_of(url: str) -> str:
    """Host of a URL, without `www.` — what the operator recognises. Never the full URL: a query string read out
    loud is noise, and the site is the part he can act on («pues mira en otra web»)."""
    try:
        from urllib.parse import urlparse
        h = (urlparse((url or "").strip()).netloc or "").lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def wall_reason(url: str) -> str:
    """Short, operator-facing reason why this URL is a WALL, or '' when it is an ordinary page.

    Deliberately mechanical: this recognises a SIGNAL in a URL, it does not judge what the page means. The phrasing
    is what the operator hears, so it says what happened ("el sitio interpuso una verificación anti-robot"), never
    an internal token.
    """
    u = (url or "").strip().lower()
    if not u:
        return ""
    for needle, reason in _WALL_URL_NEEDLES:
        if needle in u:
            return reason
    try:
        from urllib.parse import urlparse
        path = urlparse(u).path or ""
    except Exception:
        return ""
    if any(seg.strip().lower() in _ERROR_PATH_SEGMENTS for seg in path.split("/") if seg.strip()):
        return "el sitio devolvió una página de error (no existe esa página)"
    return ""
