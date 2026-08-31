"""nucleo/errand_kind.py — QUÉ CLASE DE ENCARGO es esto, and how is calls mientras corre.

Extraido of `nucleo/dispatch.py` the 2026-08-24 because the trinquete of arquitectura pidio a module in vez of a
cap mas alto, and the corte estaba dado: todo it of here es a funcion PURA sobre the TEXTO of the request — no
mira the record of sessions, no touches the pool, no writes nothing. `dispatch` is queda with it suyo, that es what do
with the response.

Lo that gobierna this module es a frontera that ha costado varias rondas medirla, and by eso the regex llevan su
evidencia pegada: «rellena the widget with the results» es DATOS and no CÓDIGO, «pon a informe in pantalla» es
a research and no a operation web, and a site conocido in the frase no convierte in navegacion it that era a
question. Cada a of esas lineas nacio of a worker that is fue a do it that no era.
"""
from __future__ import annotations

import re


_WEB_RE = re.compile(
    r"\b(en\s+wallapop|wallapop|en\s+amazon|amazon|navegador|abre\s+la\s+web|abre\s+la\s+p[áa]gina|"
    r"en\s+linkedin|linkedin|en\s+el\s+sitio|en\s+la\s+p[áa]gina|automatiza|"
    r"in[ií]ciame?\s+sesi[óo]n|log[ui]n)\b", re.I)
# El generador (kind="code") SOLO construye/modifica the CÓDIGO of a widget. Antes `_CODE_RE` matcheaba the palabra
# «widget/tarjeta/panel» A SECAS → CUALQUIER task that the mencionara (p.ej. «opens and shows the mensaje… is reflective
# in the widget of mensajeria») caia in the generador and CONSTRUÍA a widget basura (incidente 2026-08-01, clase of the
# 25/07). Fix V2-081: exige a VERBO of crear/modificar CÓDIGO junto al name — coherente with the guard of the router
# (`looks_like_create_widget`, that also usa verbo+name); create is reuses of there (source only), here only
# is adds the lado MODIFICAR-code. Mostrar/open/read/gestionar a widget existente NO es code → kind="generic"
# (a worker general that, if does missing, OPERA the widget via hbwidget — never it regenera).
_MODIFY_CODE_RE = re.compile(
    r"\b(modific\w*|cambi\w*|edit\w*|reescrib\w*|refactor\w*|redise[nñ]\w*|actualiz\w+ el c[oó]digo|"
    r"a[ñn]ad\w*\s+(?:una?\s+)?columna|modify|redesign|rewrite)\b[^.!?]{0,45}\b(widget|tarjeta|panel|componente)\b",
    re.I)
# …and it MISMO with «proyecto», that estaba A SECAS a linea debajo of the comentario that it prohibe (incidente
# 2026-08-12, auditando a search of veleros of punta a punta). El criterion that dio the own operator era
# «listo for navegar, no a PROYECTO for restaurar» — in the compraventa of barcos «a proyecto» es the termino
# corriente for a barco a medio reformar. Esa palabra sola mando su BÚSQUEDA al `kind="code"`, or sea al backend
# of the GENERADOR of widgets (`registry.get_backend` elige by `spec.kind`): a buscador despachado al site that
# writes code. Es the same clase exacta that V2-081, without arreglar in this rama.
# `architect` is queda A SECAS a purpose: es the name of nuestro conector, nadie it says of pasada. «Proyecto»
# es a palabra of the castellano of all the dias, so that exige —como the lado MODIFICAR-code— a VERBO of
# work of proyecto delante, or a palabra of repositorio detras.
_ARCHITECT_RE = re.compile(
    r"\barchitect\b"
    r"|\b(crea\w*|monta\w*|arranca\w*|planifica\w*|retoma\w*|abre|cierra|a[ñn]ad\w*|actualiz\w*|"
    r"create|start|plan)\b[^.!?]{0,45}\bproyecto\b"
    r"|\bproyecto\b[^.!?]{0,45}\b(repo\w*|rama\w*|commit\w*|c[oó]digo|tarea\w*|meshkore|daemon)\b",
    re.I)
# …and the contrapeso: LLENAR a widget with datos NO es touch su code (incidente 2026-08-02). El brief «finaliza and
# shows the informe … REFLEJANDO EL CAMBIO in the widget of informes» casaba `cambi\w*` + `widget` inside of the
# ventana of 45 chars → is despacho al GENERADOR, that is paso 3,5 min REESCRIBIENDO widget.js for a caso that only
# necesitaba a data-op, and the operator siguio without ver nothing. Un verbo of DATOS/PRESENTACIÓN in the same frase gana:
# the request es «pon estos datos there», no «cambiame the componente». (Crear a widget new continues mandando: eso it
# decide `looks_like_create_widget` with verbo+name and no pasa by here.)
_DATA_NOT_CODE_RE = re.compile(
    r"\b(refleja\w*|rellena\w*|llena\w*|puebla\w*|presenta\w*|muestra\w*|mostrar|ense[nñ]a\w*|pinta\w*|vuelca\w*|"
    r"pon(?:er|ga|gas)?\b[^.!?]{0,30}\b(?:datos|resultados|informe|lista|items)|fill|populate|render|display)\b",
    re.I)

def classify_kind(request: str) -> str:
    r = request or ""
    if _WEB_RE.search(r):
        return "web"
    # …and also when the operator NO nombra the site but the task es a GESTIÓN that only exists inside of uno
    # (V2-119, 2026-08-18). `_WEB_RE` es a lista of sites nombrados: sirve for «buscalo in Wallapop» and dejaba
    # outside «reservame mesa for 2 in Casa Lucio», that caia in `generic` — a worker without the catalogo of sites of
    # confianza and without the path of the browser. El caso of uso `restaurant-tonight-madrid` it midio: the corrida
    # termino without UN SOLO intento of reservation, with the model inventandose the politica of the restaurante.
    # Only the categorias TRANSACCIONALES (reserve mesa/habitacion/vuelo) promocionan: the clasificados of
    # second mano NO, because comparten fraseo with a research and esa has su own embudo from
    # `generic`. El porque completo, and the taxonomia, in `site_catalog.TRANSACTIONAL_CATEGORIES`.
    try:
        from nucleo.flash import site_catalog as _sc
        if _sc.category_of(r) in _sc.TRANSACTIONAL_CATEGORIES:
            return "web"
    except Exception:
        pass
    # …and when the operator SÍ nombra a site, but uno that `_WEB_RE` no conoce (V2-126, 2026-08-18).
    #
    # Habia DOS inventarios of sites conocidos and llevaban time desincronizados: `_WEB_RE` (here: wallapop,
    # amazon, linkedin, «opens the web»…) and `router_guards._KNOWN_SITES` (quince, the that the motor sabe open for
    # a login). DOCE estaban only in the second — netflix, spotify, gmail, google, ebay, twitter, instagram,
    # facebook, outlook, github, idealista, milanuncios. Medido in the caso `cancel-subscription-before-charge`:
    # «Cancela mi suscripcion a Netflix» → `generic`, or sea a worker SIN browser. Y ese es the dano real, no the
    # missing of a cuenta of Netflix: without browser the task no can arrive al muro of login, so that no can
    # PEDIRLE al operator that entre ni say «no puedo acceder a tu cuenta» — the sistema is queda without the only
    # response honest that tenia, and the turn rellena the hueco narrando.
    #
    # Se exige NOMBRE DE SITIO + VERBO DE TAREA, never the verbo suelto: `looks_like_web_task` by si only es
    # wide (`reads|mira|revis|compr`) and su own docstring says that exists como DISPARADOR, no como clasificador
    # — enrutar of mas already costo a vez two tarjetas of browser that nadie pidio (ver `_MODIFY_CODE_RE` arriba).
    # Musica and mensajeria quedan FUERA although nombren su site: esas cuentas is vinculan DENTRO of su widget
    # (OAuth/QR), never by the Chromium, and sus two guards existen justo for sostener ese invariante.
    try:
        from nucleo.flash import router_guards as _rg
        _site = _rg.login_site(r)
        # V2-138: those two guards exist because CONNECTING one of those accounts happens inside its own widget
        # (OAuth/QR), never through the Chromium — a real invariant. But they were excluding the site for ANY
        # request, and ending a PAID commitment with that provider has nothing to do with linking it: «anula the
        # suscripcion of Spotify» happens on spotify.com like any other cancellation. Measured: it classified as
        # `generic`, i.e. a worker with NO browser, so it could not even reach the login wall to tell the
        # operator what it needed. The carve-out is narrow on purpose — `ends_a_commitment` is False for «quita
        # the musica of Spotify» and for «conecta mi Spotify».
        from nucleo import danger as _danger_cls
        _linking_guard = (_rg.is_music_service(_site, r) or _rg.is_messaging_service(_site, r))
        if _site and _rg.looks_like_web_task(r) and (not _linking_guard or _danger_cls.ends_a_commitment(r)):
            return "web"
    except Exception:
        pass
    # …and a operation of DINERO or of COMPROMISO ocurre in a WEB, although the proveedor no este in ninguna lista
    # (V2-148, 2026-08-19). Medido sobre the frases of the own caso: «paga the factura of the luz», «paga the
    # factura of Endesa», «paga the factura of the luz in the web of Endesa» — the three a `generic`, or sea a
    # worker SIN browser, incluso after of that the operator nombrara the proveedor and dijera where the paga.
    #
    # Lo habia dejado abierto DOS veces (V2-141, V2-144) anotando that «the destino of a pago es the web of the
    # proveedor CONCRETO, no a site of confianza comun, so that no es the same solucion that a categoria of the
    # catalogo». Era cierto and era the conclusion wrong: no needs entrada of catalogo NINGUNA, needs
    # NAVEGADOR — the destino es the proveedor that name the operator, and encontrarlo es work of the worker.
    #
    # Va DESPUÉS of the ramas anteriores for no pisarlas (a site nombrado or a categoria transaccional already
    # resolvieron), and the dano that repara no es «no paga» —imposible without cuenta real, and the caso no it penaliza—
    # sino that without browser the task no can arrive al muro of login: the sistema pierde the only response
    # honest that tenia and the turn rellena the hueco narrando (the argumento of V2-126 for Netflix, another vez).
    try:
        from nucleo.flash import router_guards as _rg_money
        if _rg_money.money_work_needs_a_browser(r):
            return "web"
    except Exception:
        pass
    # CÓDIGO of widget = CREAR (reusa the deteccion of the router, verbo+name) or MODIFICAR-code, or architect.
    # NUNCA by mencionar «widget» a secas (V2-081): open/show/gestionar uno existente NO es code.
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
