"""Las tres decisiones del cerebro que hundieron la sesión del 2026-08-02 (búsqueda + informe en pantalla).

Cada bloque fija una regresión observada en la traza real (`.meshkore/logs/timeline-latest.jsonl`, 12:51→13:08):

  · `_classify_kind`   — «reflejando el cambio en el widget de informes» se despachó al GENERADOR DE CÓDIGO, que
                         pasó 3,5 min reescribiendo `widget.js` para algo que era una data-op. Llenar ≠ programar.
  · `danger`           — «(proyecto compra y venta de motos)» disparó el confirm-gate de acción irreversible sobre
                         una tarea de INVESTIGACIÓN, que quedó parada pidiendo un OK sin sentido.
  · `dialog.push_user` — el STT partió la petición en 6 trozos; cada turno pisaba al anterior y el `raise` del
                         CancelledError se llevaba la frase del operador → el cerebro nunca vio la palabra "piscina".
"""
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
