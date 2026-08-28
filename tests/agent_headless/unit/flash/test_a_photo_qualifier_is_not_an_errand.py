"""V2-461 — un MATIZ sobre una foto afina la búsqueda; no convierte ver una foto en un encargo.

Medido en vivo el 2026-08-28, primera corrida de `show-real-photo-of-a-new-car__es` contra el agente ES:

  turno 1  «enséñame una foto del Ferrari Amalfi»          → show_images · 12 fotos en el visor · ✅
  turno 3  «una de esas, la que mejor se vea. Pero que      → NINGUNA tool. Prometió y no hizo nada.
            sea el Amalfi, no otro Ferrari»
  turno 4  (el modelo insiste con «verificada»)             → escalate → Brain Worker → hoja de Resultados

Y el defecto estaba ESCRITO en la descripción de la propia tool, puesta el mismo día:

    «Escala solo si hay que CURAR: … o mejores si las que ya enseñaste NO LE VALEN.»

«Que sea el Amalfi y no otro Ferrari» es exactamente «las que enseñaste no me valen», así que el modelo hizo
lo que se le dijo. La hoja genérica que vio el operador no la eligió el worker: la abre la ESCALADA, porque
esa tarjeta es la ficha de la tarea. O sea que el destino de la entrega no era el problema — el problema era
escalar.

La regla del operador, con sus palabras: «en realidad sólo estamos pidiendo una imagen». Un matiz afina la
CONSULTA. Y si las fotos ya están en el visor, elegir una de ellas es una acción del widget, no otra
búsqueda ni un worker.
"""
from __future__ import annotations

import json

from nucleo.flash import router


def _desc(name: str) -> str:
    for t in router.TOOLS:
        if t.get("function", {}).get("name") == name:
            return t["function"]["description"]
    raise AssertionError(f"no existe la tool {name}")


# ── lo que se quitó ─────────────────────────────────────────────────────────────────────────────────────
def test_ya_no_invita_a_escalar_porque_las_de_antes_no_valgan():
    """El literal que causó la corrida. Se comprueba la INVITACIÓN, no la palabra «escala»: la tool sigue
    nombrando una escalada legítima (una web concreta), así que buscar «escala» pasaría con el defecto
    puesto."""
    d = _desc("show_images")
    assert "no le valen" not in d
    assert "CURAR" not in d, "«curar» era el nombre que se le daba a re-buscar, y re-buscar es esta tool"


# ── lo que se puso ──────────────────────────────────────────────────────────────────────────────────────
def test_un_matiz_afina_la_consulta_y_se_vuelve_a_llamar():
    d = _desc("show_images")
    assert "MATIZ" in d and "`query`" in d
    assert "vuelves a llamar" in d, "sin decir QUÉ hacer con el matiz, el modelo vuelve a improvisar"


def test_elegir_una_de_las_que_YA_estan_en_pantalla_es_del_widget():
    """La mitad que faltaba y que explica el turno 3 MUDO: el modelo no tenía dicho a dónde va «una de esas»,
    así que no llamó a nada. El mecanismo ya existía (`widget_data` sobre las acciones declaradas del visor);
    lo que no existía era la frase que lo conecta."""
    d = _desc("show_images")
    assert "widget_data" in d and "imagenes" in d


def test_la_escalada_que_queda_es_una_WEB_CONCRETA_y_se_dice():
    """Sin ningún camino de escalada, «sácalas de la web oficial de Ferrari» —que un índice de imágenes no
    puede resolver— se quedaría sin sitio a donde ir. La frontera es un SITIO nombrado, no la exigencia de
    calidad, que es lo que se confundía."""
    d = _desc("show_images")
    assert "web concreta" in d


# ── la otra mitad, sin la cual esto no bastaría ─────────────────────────────────────────────────────────
def test_el_NO_list_de_escalate_sigue_nombrando_las_fotos():
    """Dos superficies deciden lo mismo y cablear una sola falla EN SILENCIO: aunque `show_images` ya no
    invite a escalar, `escalate_to_slowbrain` sigue siendo la tool «ante la duda» y se llevaría el turno."""
    e = _desc("escalate_to_slowbrain")
    assert "show_images" in e
    assert "enseñar FOTOS" in e


def test_sigue_sin_confundirse_con_las_otras_dos_hermanas():
    """`play_video` y `web_search` son los dos destinos equivocados que ya costaron una ronda cada uno."""
    d = _desc("show_images")
    assert "web_search" in d and "play_video" in d


def test_habla_en_PRESENTE_porque_tarda_segundos():
    """Regla ganada en V2-380/383 y que aquí sigue viva: decirlo en pasado («te las he puesto») antes de que
    existan es la quinta versión de la misma mentira sobre una caja vacía."""
    assert "presente" in _desc("show_images")


# ── el precio ───────────────────────────────────────────────────────────────────────────────────────────
def test_el_catalogo_no_ha_crecido_por_explicarlo_mejor():
    """El techo se paga en CADA turno de voz. Esta redacción entró compactando la propia tool tres veces en
    vez de subirlo, que es lo que manda el trinquete de `test_router.py`."""
    from tests.agent_headless.unit.flash.test_router import MAX_CATALOG_CHARS
    assert len(json.dumps(router.TOOLS, ensure_ascii=False)) <= MAX_CATALOG_CHARS
