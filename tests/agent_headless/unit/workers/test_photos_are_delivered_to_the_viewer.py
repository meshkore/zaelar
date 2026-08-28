"""V2-457 — un worker que CURA fotos las entrega en el visor, no en la hoja.

La otra mitad de la frontera. `show_images` resuelve la petición ligera («enséñame una foto de X») en el turno,
pero el escalado sigue existiendo para CURAR — «las oficiales verificadas, y dime de qué fuente sale cada una».
Ese worker tenía una sola receta de entrega y decía, con esas letras, que **una foto** va a la hoja como un item
más. O sea que la ruta rápida enseñaba las fotos en un visor y la lenta las volvía a volcar en una tabla: la
misma petición con dos respuestas distintas según por dónde entrara.

La frontera NO es «¿hay imágenes de por medio?» sino **qué es la respuesta**: «enséñame fotos de X» se responde
con las fotos; «búscame un hotel» se responde con hoteles, y ahí la foto es una columna de la ficha. Las dos
mitades tienen su caso aquí, porque arreglar solo la primera mandaría al visor las fotos de los hoteles.
"""
from __future__ import annotations

from nucleo import dispatch_prompts as DP


def _recipe() -> str:
    return DP._METHOD_BLOCK


def test_la_receta_nombra_el_visor_y_como_llegar_a_el():
    r = _recipe()
    assert "imagenes" in r, "un destino que no se nombra no existe para el worker (V2-219)"
    assert "widget_cli data imagenes show" in r, (
        "nombrar el destino sin decir el comando deja al worker descubriéndolo a golpes")


def test_dice_la_FORMA_del_payload_o_el_worker_la_adivina():
    """Un worker que no sabe qué campos lleva una foto entrega una lista de URL sueltas y el visor queda sin
    fuente — que es justo lo que el operador pidió ver."""
    r = _recipe()
    for campo in ("url", "thumb", "title", "site", "page"):
        assert campo in r, campo


def test_y_NO_se_lleva_por_delante_la_hoja():
    """La mitad que sostiene la regla. Sin esto, «las fotos al visor» acabaría mandando allí las fotos de los
    hoteles y dejando la hoja —que es donde se comparan cosas— sin su columna de imagen."""
    r = _recipe()
    assert "widget_cli data results present" in r, "la hoja sigue siendo el sitio de una LISTA que comparar"
    assert "results detail" in r, "…y de UNA ficha con sus datos"
    assert "su `image`" in r, "una ficha de la hoja sigue pudiendo llevar foto"


def test_la_frontera_esta_dicha_por_lo_que_ES_la_respuesta_no_por_si_hay_imagenes():
    """La regla que el modelo tiene que poder aplicar a un encargo que nadie ha escrito todavía: se decide por
    qué se está respondiendo, no por una lista de temas."""
    r = _recipe()
    assert "enséñame fotos" in r and "búscame un hotel" in r, (
        "los dos lados de la frontera se enseñan con un ejemplo de cada uno, o solo se entiende uno")


def test_una_foto_sola_ya_no_se_manda_a_la_hoja_como_un_item_mas():
    """El literal que había y era el defecto: la receta listaba «una foto» junto a un informe o un resumen."""
    r = _recipe()
    assert "un informe, una foto, un resumen" not in r
