"""Las tres decisiones del cerebro que hundieron la sesión del 2026-08-02 (búsqueda + informe en pantalla).

Cada bloque fija una regresión observada en la traza real (`.meshkore/logs/timeline-latest.jsonl`, 12:51→13:08):

  · `_classify_kind`   — «reflejando el cambio en el widget de informes» se despachó al GENERADOR DE CÓDIGO, que
                         pasó 3,5 min reescribiendo `widget.js` para algo que era una data-op. Llenar ≠ programar.
  · `danger`           — «(proyecto compra y venta de motos)» disparó el confirm-gate de acción irreversible sobre
                         una tarea de INVESTIGACIÓN, que quedó parada pidiendo un OK sin sentido.
  · `dialog.push_user` — el STT partió la petición en 6 trozos; cada turno pisaba al anterior y el `raise` del
                         CancelledError se llevaba la frase del operador → el cerebro nunca vio la palabra "piscina".
"""
import pytest as _pytest

from nucleo import danger
from nucleo.dispatch import _classify_kind
from nucleo.flash import dialog


# ── llenar un widget con datos NO es reescribir su código ─────────────────────────────────────────────────
def test_filling_a_widget_with_data_is_not_code_work():
    # el brief EXACTO que el Susurro escaló y acabó en el generador
    assert _classify_kind(
        "finaliza y muestra inmediatamente el informe con los resultados de la búsqueda ampliada de piscinas, "
        "reflejando el cambio en el widget de informes para que el operador pueda verlo") != "code"
    for req in (
        "rellena el widget de resultados con las piscinas encontradas",
        "actualiza la lista del widget de resultados y muéstrala",
        "puebla el widget results con los coches y sus fotos",
    ):
        assert _classify_kind(req) != "code", req


def test_real_code_work_still_routes_to_the_generator():
    for req in (
        "modifica el widget de meteo para que muestre la humedad",
        "añade una columna al widget de agenda",
        "rediseña el panel de resultados con otro layout",
    ):
        assert _classify_kind(req) == "code", req


# ── el confirm-gate es para ÓRDENES irreversibles, no para temas mencionados de pasada ────────────────────
def test_research_task_is_not_gated_as_irreversible():
    assert not danger.is_dangerous(
        "Termina la búsqueda ampliada del operador (proyecto compra y venta de motos): completa el informe con "
        "los resultados y puebla el widget results con lo encontrado")
    assert not danger.is_dangerous("busca opciones de compra y venta de motos y ponme un informe")
    assert not danger.is_dangerous("prepara una lista de sitios de compraventa de coches")


def test_a_real_irreversible_order_still_asks_for_ok():
    assert danger.is_dangerous("compra la moto que te he dicho")
    assert danger.is_dangerous("paga la factura de la luz")
    assert danger.is_dangerous("publica el anuncio en Wallapop")
    assert danger.is_dangerous("borra la cuenta")
    # y el contexto entre paréntesis no puede TAPAR una orden real que sí está en el texto principal
    assert danger.is_dangerous("compra el billete (viaje de trabajo, proyecto compra y venta)")


# ── lo que el operador dijo no se pierde porque su turno se pisara ────────────────────────────────────────
def test_overlapped_turns_keep_what_the_operator_said():
    """La secuencia REAL: 6 trozos de STT, 5 turnos cancelados. Antes del fix solo el último llegaba al modelo."""
    window: list[dict] = []
    for chunk in (
        "Estamos buscando una piscina Tarragona,",
        "Estamos buscando una piscina Tarragona, que sea especial.",          # el STT reemite acumulando
        "Pero que sea pública, o de pago, pero que podamos entrar hoy domingo",
        "sin ser socios, que sea chula, muy grande, con toboganes",
        "me da igual si está en un hotel, en un camping",
        "Dime a ver qué encuentras cerca de Tarragona.",
    ):
        dialog.push_user(window, chunk)

    said = " ".join(m["content"] for m in window if m["role"] == "user").lower()
    for must in ("piscina", "toboganes", "camping", "domingo"):
        assert must in said, f"«{must}» se perdió: el cerebro decidiría sin ese contexto"


def test_accumulating_stt_chunks_do_not_duplicate_the_phrase():
    window: list[dict] = []
    dialog.push_user(window, "Estamos buscando una piscina")
    dialog.push_user(window, "Estamos buscando una piscina en Tarragona")
    dialog.push_user(window, "Estamos buscando una piscina en Tarragona, que sea especial")
    # una sola entrada, la COMPLETA — repetir el prefijo N veces es justo lo que degrada al modelo pequeño (V2-032)
    assert len(window) == 1
    assert window[0]["content"] == "Estamos buscando una piscina en Tarragona, que sea especial"


def test_shorter_rechunk_does_not_truncate_what_we_already_have():
    window: list[dict] = []
    dialog.push_user(window, "busca piscinas en Tarragona con toboganes")
    dialog.push_user(window, "busca piscinas")                 # trozo tardío, más corto
    assert window[0]["content"] == "busca piscinas en Tarragona con toboganes"


def test_a_new_sentence_is_a_new_turn():
    window: list[dict] = []
    dialog.push_user(window, "busca piscinas cerca de Tarragona")
    dialog.push_user(window, "y ponme el informe en pantalla")
    assert len(window) == 2


def test_empty_input_is_not_recorded():
    window: list[dict] = []
    dialog.push_user(window, "   ")
    assert window == []


# ── investigar ≠ conducir un navegador ────────────────────────────────────────────────────────────────────
def test_research_does_not_drive_a_browser():
    """«en internet»/«en la web» dicen DÓNDE vive el dato, no que haya que abrir Chromium.

    Observado en vivo el 2026-08-02 con la narración del worker ya visible: «Investiga EN INTERNET y prepárame un
    informe» casaba `_WEB_RE` → el worker se pasó 7 min clicando por coordenadas para esquivar el banner de
    cookies de aquopolis.es, sacando un precio que `web_search`+`fetch` habían dado en segundos en la corrida
    anterior."""
    for req in (
        "Investiga en internet y prepárame un informe con 3 parques acuáticos cerca de Tarragona",
        "busca en la web cuánto cuesta la entrada y ponme el informe en pantalla",
        "prepara una lista de cuentos infantiles de código abierto",
    ):
        assert _classify_kind(req) == "generic", req


def test_entering_a_real_site_still_goes_to_the_browser():
    """La modalidad 2 sigue intacta: cuando hay que ENTRAR y operar un sitio, navegador."""
    for req in (
        "busca motos naked de segunda mano en Wallapop",
        "abre la web del ayuntamiento y descarga el formulario",
        "inicia sesión en LinkedIn y mira los mensajes",
        "automatiza la reserva en el sitio de la ITV",
    ):
        assert _classify_kind(req) == "web", req


# ── UN WIDGET COMO DESTINO NO ES UN WIDGET QUE PROGRAMAR (2026-08-13) ─────────────────────────────────────────
@_pytest.mark.parametrize("text,is_create", [
    # DESTINO de la entrega → NO es código. La primera es el caso REAL que hundió una investigación entera.
    ("Entrega el resultado montado en el widget results con las 3 secciones claras y los enlaces", False),
    ("pon los hoteles en el widget de resultados", False),
    ("muestra el informe en el panel de resultados", False),
    ("deliver the result into the widget results", False),
    # …y el MISMO caso con artículo INDETERMINADO (2026-08-18). La lista de artículos solo llevaba los
    # determinados, así que estas cuatro se colaban al generador. La primera es literal de producción.
    ("Monta el resultado en un widget del canvas para que el operador pueda VERLO en pantalla", False),
    ("presenta los datos en una tarjeta", False),
    ("vuelca el informe en unos paneles", False),
    ("render the findings into a widget", False),
    # OJO: «añade una columna al widget de agenda» NO se lista aquí. No es un create (y `looks_like_create_widget`
    # dice False), pero SÍ es código: cambiar las columnas de un widget es modificar su UI, y `_classify_kind` lo
    # manda al generador por `_MODIFY_CODE_RE`, que es lo correcto. Se comprueba aparte, abajo.
    # CREATE de verdad → sí es código
    ("créame un widget del tiempo de Soria", True),
    ("hazme un panel con la cotización del bitcoin", True),
    ("monta un widget nuevo para las mareas", True),
    ("build me a widget that tracks my steps", True),          # ojo: «a widget» ≠ preposición castellana «a»
    ("create a new panel for the tides", True),
    ("créame un panel de mareas y entrégalo en el widget results", True),   # las DOS: gana el create real
])
def test_a_widget_named_as_a_destination_is_not_code(text, is_create):
    """Una investigación de viaje (ferry+hotel+restaurante) acabó en el GENERADOR DE WIDGETS, escribiendo el código
    de un widget nuevo `prepara-ricart-viaje` en vez de buscar nada. Causa única: la escalada terminaba en «Entrega
    el resultado MONTADO en el widget results», y `mont\\w*` es verbo de crear con `widget` a nueve caracteres.

    O sea que pedir la entrega EN LA HOJA DE RESULTADOS desviaba la tarea al generador — y la hoja de resultados es
    justo la superficie de entrega de toda investigación: el fallo vivía en el camino más transitado del producto.

    La distinción no es una lista de excepciones: es GRAMÁTICA. Detrás de una preposición de destino («en el
    widget», «al panel», «into the widget») el widget es el SITIO donde va el resultado, no la cosa que se
    construye. Misma familia que V2-081 (mostrar→construir) y que «proyecto» a secas (2026-08-12)."""
    from nucleo.flash import router as _router
    assert _router.looks_like_create_widget(text) is is_create
    if not is_create:
        # y la consecuencia que importa: el dispatcher NO lo manda al backend del generador
        assert _classify_kind(text) != "code"


def test_gather_and_show_never_reaches_the_widget_generator():
    """EL CASO REAL, verbatim de producción (sesión 82e2ba11, 2026-08-18). El operador pidió por voz «muéstrame una
    ficha técnica y una foto» de un coche; el FlashBrain reformuló la escalada terminándola en «Monta el resultado
    en UN widget del canvas…» y eso volvió a caer en el GENERADOR: tres minutos escribiendo un widget
    `investiga-ferrari-f80` de un solo uso, en vez de buscar y entregar en la hoja de resultados.

    Es la MISMA avería del 2026-08-13 (arriba) con el artículo cambiado: la lista de la neutralización llevaba
    `el|la|los|las` y no `un|una|unos|unas`. La gramática no depende del artículo — «en un widget» sigue siendo el
    SITIO donde va el resultado. Y la frase la escribe el propio modelo, así que el operador no puede evitarla."""
    from nucleo.flash import router as _router
    req = ("Investiga el Ferrari F80 (último modelo de Ferrari lanzado al mercado) y prepara una FICHA TÉCNICA "
           "completa (motor, potencia, 0-100, velocidad máxima, prestaciones, precio) junto con una FOTO REAL del "
           "coche. Monta el resultado en un widget del canvas para que el operador pueda VERLO en pantalla: la "
           "ficha técnica con los datos y al menos una fotografía del Ferrari F80. El operador quiere ver cómo es "
           "el coche.")
    assert _router.looks_like_create_widget(req) is False
    assert _classify_kind(req) != "code"          # → generic → brief de investigación → hoja `results`


@_pytest.mark.parametrize("text", [
    "monta esto en un widget nuevo",
    "pon el informe en una tarjeta nueva",
])
def test_an_explicit_new_widget_survives_the_destination_rule(text):
    """La ÚNICA excepción real de la regla del destino, y hay que conservarla: «en un widget NUEVO» sí pide uno
    nuevo. Ahí la preposición de destino y el create coexisten en la misma frase y manda el create — si la
    neutralización se lo tragara, ampliar la lista de artículos habría cambiado un falso positivo por un falso
    negativo."""
    from nucleo.flash import router as _router
    assert _router.looks_like_create_widget(text) is True
    assert _classify_kind(text) == "code"


def test_modifying_a_widgets_ui_is_still_code():
    """La otra cara: el arreglo del DESTINO no puede tragarse una modificación de verdad. Cambiar las columnas de un
    widget es tocar su UI, o sea código, aunque la frase lleve «al widget» — lo enruta `_MODIFY_CODE_RE`, no el
    detector de create."""
    from nucleo.flash import router as _router
    t = "añade una columna al widget de agenda"
    assert _router.looks_like_create_widget(t) is False       # no es CREAR
    assert _classify_kind(t) == "code"                        # pero sí es CÓDIGO
