"""V2-457 — a worker that CURATES photos delivers them to the viewer, not the sheet.

The other half of the boundary. `show_images` handles the lightweight request («show me a photo of X») in the turn,
but scaling still exists for CURATING — «the verified official ones, and tell me which source each one comes from».
That worker had a single delivery recipe and explicitly said that **a photo** goes to the sheet as one more item.
In other words, the fast path showed the photos in a viewer and the slow path dumped them back into a table: the
same request with two different responses depending on which path it came through.

The boundary is NOT «are there images involved?» but **what the response is**: «show me photos of X» is answered
with the photos; «find me a hotel» is answered with hotels, and there the photo is a column in the record. Both
halves have their case here, because fixing only the first would send hotel photos to the viewer.
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
    """A worker that does not know which fields a photo contains delivers a list of bare URLs and leaves the viewer
    without a source — which is exactly what the operator asked to see."""
    r = _recipe()
    for campo in ("url", "thumb", "title", "site", "page"):
        assert campo in r, campo


def test_y_NO_se_lleva_por_delante_la_hoja():
    """The half that upholds the rule. Without this, «photos to the viewer» would end up sending hotel photos there
    and leaving the sheet —where things are compared— without its image column."""
    r = _recipe()
    assert "widget_cli data results present" in r, "la hoja sigue siendo el sitio de una LISTA que comparar"
    assert "results detail" in r, "…y de UNA ficha con sus datos"
    assert "su `image`" in r, "una ficha de la hoja sigue pudiendo llevar foto"


def test_la_frontera_esta_dicha_por_lo_que_ES_la_respuesta_no_por_si_hay_imagenes():
    """The rule the model must be able to apply to a task that no one has written yet: it is decided by
    what is being answered, not by a list of topics."""
    r = _recipe()
    assert "enséñame fotos" in r and "búscame un hotel" in r, (
        "los dos lados de la frontera se enseñan con un ejemplo de cada uno, o solo se entiende uno")


def test_una_foto_sola_ya_no_se_manda_a_la_hoja_como_un_item_mas():
    """The literal that was there and was the defect: the recipe listed «a photo» alongside a report or a summary."""
    r = _recipe()
    assert "un informe, una foto, un resumen" not in r
