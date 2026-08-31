"""V2-461 — a NUANCE about a photo sharpens the search; it does not turn viewing a photo into an errand.

Measured live on 2026-08-28, first run of `show-real-photo-of-a-new-car__es` against the ES agent:

  turn 1  «enséñame una foto del Ferrari Amalfi»          → show_images · 12 photos in the viewer · ✅
  turn 3  «una de esas, la que mejor se vea. Pero que      → NO tool. It promised and did nothing.
          sea el Amalfi, no otro Ferrari»
  turn 4  (the model insists on «verificada»)             → escalate → Brain Worker → Results sheet

And the defect was WRITTEN in the description of the tool itself, added that same day:

    «Escala solo si hay que CURAR: … o mejores si las que ya enseñaste NO LE VALEN.»

«Que sea el Amalfi y no otro Ferrari» is exactly «las que enseñaste no me valen», so the model did
what it was told. The generic sheet the operator saw was not chosen by the worker: ESCALATION opens it,
because that card is the task record. In other words, the delivery destination was not the problem — the
problem was escalating.

The operator's rule, in their words: «en realidad sólo estamos pidiendo una imagen». A nuance sharpens the
QUERY. And if the photos are already in the viewer, choosing one of them is a widget action, not another
search or a worker.
"""
from __future__ import annotations

import json

from nucleo.flash import router


def _desc(name: str) -> str:
    for t in router.TOOLS:
        if t.get("function", {}).get("name") == name:
            return t["function"]["description"]
    raise AssertionError(f"no existe la tool {name}")


# ── what was removed ────────────────────────────────────────────────────────────────────────────────────
def test_ya_no_invita_a_escalar_porque_las_de_antes_no_valgan():
    """The literal that caused the run. The INVITATION is checked, not the word «escala»: the tool still
    names a legitimate escalation (a specific website), so searching for «escala» would pass with the bug
    in place."""
    d = _desc("show_images")
    assert "no le valen" not in d
    assert "CURAR" not in d, "«curar» era el nombre que se le daba a re-buscar, y re-buscar es esta tool"


# ── what was added ───────────────────────────────────────────────────────────────────────────────────────
def test_un_matiz_afina_la_consulta_y_se_vuelve_a_llamar():
    d = _desc("show_images")
    assert "MATIZ" in d and "`query`" in d
    assert "vuelves a llamar" in d, "sin decir QUÉ hacer con el matiz, el modelo vuelve a improvisar"


def test_elegir_una_de_las_que_YA_estan_en_pantalla_es_del_widget():
    """The missing half that explains the SILENT turn 3: the model was not told where «una de esas» goes,
    so it called nothing. The mechanism already existed (`widget_data` on the viewer's declared actions);
    what did not exist was the sentence connecting it."""
    d = _desc("show_images")
    assert "widget_data" in d and "imagenes" in d


def test_la_escalada_que_queda_es_una_WEB_CONCRETA_y_se_dice():
    """Without any escalation path, «sácalas de la web oficial de Ferrari» —which an image index cannot
    resolve— would have nowhere to go. The boundary is a named SITE, not a quality requirement, which is
    what was being confused."""
    d = _desc("show_images")
    assert "web concreta" in d


# ── the other half, without which this would not be enough ──────────────────────────────────────────────
def test_el_NO_list_de_escalate_sigue_nombrando_las_fotos():
    """Two surfaces make the same decision, and wiring only one fails SILENTLY: even though `show_images` no
    longer invites escalation, `escalate_to_slowbrain` remains the «when in doubt» tool and would take the turn."""
    e = _desc("escalate_to_slowbrain")
    assert "show_images" in e
    assert "enseñar FOTOS" in e


def test_sigue_sin_confundirse_con_las_otras_dos_hermanas():
    """`play_video` and `web_search` are the two wrong destinations that have already cost one round each."""
    d = _desc("show_images")
    assert "web_search" in d and "play_video" in d


def test_habla_en_PRESENTE_porque_tarda_segundos():
    """A rule learned in V2-380/383 that still holds here: saying it in the past tense («te las he puesto»)
    before they exist is the fifth version of the same lie about an empty box."""
    assert "Presente" in _desc("show_images")     # compactado en V2-463: «Presente (…), nunca pasado»


# ── the cost ─────────────────────────────────────────────────────────────────────────────────────────────
def test_que_sea_de_verdad_es_un_matiz_no_un_encargo():
    """Round 6 (2026-08-28): «busca algo que se note que es el Amalfi de verdad» escalated to a 4-minute
    worker with the official answer already on screen. Both surfaces now say so: the tool names those
    nuances, and escalate's NO-list adds «aunque las pida verificadas o de verdad»."""
    d = _desc("show_images")
    assert "de verdad" in d and "que se note que es X" in d
    assert "nunca un worker" in d
    e = _desc("escalate_to_slowbrain")
    assert "verificadas/de verdad" in e


def test_el_catalogo_no_ha_crecido_por_explicarlo_mejor():
    """The ceiling is paid on EVERY voice turn. This wording was added by compacting the tool itself three
    times instead of raising it, as required by the ratchet in `test_router.py`."""
    from tests.agent_headless.unit.flash.test_router import MAX_CATALOG_CHARS
    assert len(json.dumps(router.TOOLS, ensure_ascii=False)) <= MAX_CATALOG_CHARS
