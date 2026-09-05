"""PROGRESSIVE tool selection — V2-096 Phase 2, node 3.10.

Operator request: «when someone says "hello, how are you?" we are not going to send them every widget, every
tool… gradually steer the direction».

What these tests protect, in order of importance:
  1. **That trimming does not leave a turn with no way forward.** Measured across the 14 cases from node 2.13: zero
     cases are left without any acceptable tool, and the catalog drops by 51.4% of its characters.
  2. **That the escape hatch exists.** Recovery is not understanding: when trimming occurs, the model must be able to
     request the missing family (`need_capability`) and trigger ONE measurable second trip. Without it, an incorrect
     recovery is a capability silently denied — the failure that truly breaks a conversation.
  3. **That essential families are never touched**: `core`, `web`, and `memory` serve turns that are announced
     neither by the state nor by the words («how much does the ticket cost?»).
"""
from __future__ import annotations

import json

import pytest

from nucleo.flash import router, tool_selection as ts
from tests.agent_headless.e2e.prompt_cost.bench_fast_model import CASES

FULL = router.TOOLS


def _names(tools):
    return {(t.get("function") or {}).get("name") for t in tools}


def test_ningun_caso_real_se_queda_sin_tool_aceptable():
    """The invariant that determines whether this can be deployed. Test-bank semantics: it is enough for ANY of the
    accepted tools to remain (and if the case expects none, none is needed)."""
    malos = []
    for name, text, expect, _forbid in CASES:
        got = _names(ts.select(FULL, turn_text=text)[0])
        if expect and not (expect & got):
            malos.append((name, sorted(expect), sorted(got)))
    assert not malos, f"casos sin ninguna tool aceptable tras recortar: {malos}"


def test_el_recorte_ahorra_de_verdad():
    """If it does not save anything, all this risk is not worth taking. Measured: −51.4% across the 14 cases."""
    antes = sum(len(json.dumps(FULL)) for _ in CASES)
    despues = sum(len(json.dumps(ts.select(FULL, turn_text=t)[0])) for _, t, _, _ in CASES)
    ahorro = (antes - despues) / antes
    assert ahorro > 0.30, f"solo ahorra {ahorro:.1%} — no compensa el riesgo de enrutado"


@pytest.mark.parametrize("fam", sorted(ts.ALWAYS))
def test_las_familias_imprescindibles_nunca_se_recortan(fam):
    got = _names(ts.select(FULL, turn_text="hola qué tal")[0])
    for n in router.FAMILIES[fam]:
        if n in _names(FULL):
            assert n in got, f"{n} ({fam}) se recortó en un turno de charla"


def test_charla_no_arrastra_widgets_ni_media():
    """The operator's literal case."""
    sel, rep = ts.select(FULL, turn_text="hola, ¿qué tal todo?")
    got = _names(sel)
    assert "widget_data" not in got and "play_music" not in got
    assert len(sel) < len(FULL) and rep["omitted"]


def test_la_escotilla_aparece_SOLO_si_se_recorto():
    sel, _ = ts.select(FULL, turn_text="hola")
    assert "need_capability" in _names(sel), "se recortó y no se ofreció salida"
    sel2, _ = ts.select(FULL, turn_text="hola",
                        force={"widgets", "media", "workers", "cluster", "messaging"})
    assert "need_capability" not in _names(sel2), "sin recorte no hay nada que pedir"
    assert len(sel2) == len(FULL)


def test_lo_que_el_operador_tiene_DELANTE_entra_sin_mirar_palabras():
    """STATE layer (V2-085): with an open widget, its family is included even if the turn does not name it."""
    got = _names(ts.select(FULL, turn_text="y eso qué es", open_widgets=["agenda"])[0])
    assert "widget_data" in got and "show_widget" in got


def test_la_familia_reciente_mantiene_el_hilo():
    """A conversation that was already about music should not lose it because the next turn does not name it
    («the next one», «louder»)."""
    got = _names(ts.select(FULL, turn_text="la siguiente", recent_families=["media"])[0])
    assert "play_music" in got


def test_una_orden_de_parar_conserva_las_tools_de_worker():
    """«stop» with a live worker means STOP A WORKER (V2-038 precedence). If trimming removed
    `stop_worker`, the operator would not be able to stop what they launched."""
    got = _names(ts.select(FULL, turn_text="para eso")[0])
    assert "stop_worker" in got


def test_el_kill_switch_devuelve_el_catalogo_entero(monkeypatch):
    """A change that affects ROUTING must be able to be switched off without deploying code."""
    monkeypatch.setenv("ZAELAR_TOOL_SELECTION", "0")
    sel, rep = ts.select(FULL, turn_text="hola")
    assert len(sel) == len(FULL) and rep["selection"] == "off"


def test_families_used_alimenta_la_capa_reciente():
    assert ts.families_used(["play_music"]) == {"media"}
    assert ts.families_used(["widget_data", "show_widget"]) == {"widgets"}
    assert ts.families_used(["no_existe"]) == set()


def test_pedir_una_FOTO_conserva_la_tool_que_ensena_fotos():
    """V2-548 — la petición que el operador dio por rota, en un solo test.

    Medido en su motor el 2026-09-01, tres turnos, dos idiomas:

        23:21:43  «Enséñame la foto de un Ferrari F cuarenta.»   → tools sin `show_images`
        23:22:04  (la repite tras corregir)                       → tools sin `show_images`
        23:53:52  «show me a ferrari f40 picture»                 → tools sin `show_images`
                  → «Te lo abro, aunque de momento está vacío.»

    Las FOTOS viven en la familia `media` (`show_images`, V2-457 — el tercer hermano de música y vídeo), y esta
    línea de pistas solo tenía palabras de música y de vídeo. Así que «enséñame» recuperaba `widgets` y nadie
    recuperaba `media`: la única tool que pone una foto en pantalla se podaba **justo en los turnos que pedían
    una**. Pedir MÚSICA la conservaba; pedir una FOTO no.

    Y la escotilla no pudo absorberlo, que es lo que hay que recordar: `need_capability` funciona cuando el
    modelo NOTA que le falta algo, y aquí le quedaban `show_widget` y `widget_data` sobre la tarjeta `imagenes`
    —tools que PARECEN hacer el trabajo—. Las usó, abrió el visor vacío y dijo «Aquí lo tienes». Un fallo de
    recuperación es invisible precisamente cuando sobrevive al recorte un vecino plausible."""
    for phrase in ("Enséñame la foto de un Ferrari F cuarenta.", "show me a ferrari f40 picture",
                   "muéstrame fotos de Roma", "enséñame una imagen del Everest",
                   "ábreme las imágenes que tengo guardadas"):
        kept, report = ts.select(FULL, turn_text=phrase)
        assert "show_images" in _names(kept), \
            f"«{phrase}» pierde la única tool que enseña fotos — el visor se abre vacío: {report}"


def test_buscar_VIDEOS_en_plural_conserva_la_tool_del_reproductor():
    """V2-586 — la mitad de V2-402 que nunca llegó a la voz, medida en la sesión 0e3a42d6 (2026-09-05).

    «Enséñame una lista de vídeos» enseñó el reproductor VACÍO y luego escaló a un Brain Worker que tardó
    9+ minutos en redescubrir la data-op `search` del propio widget. La causa no era el carril de V2-402
    (intacto): era ESTA capa — una búsqueda de LISTA es plural por definición, y las semillas de `media`
    tenían `video` y `podcast` solo en singular, así que las frases del propio caso de uso recuperaban
    `[]` o `[widgets]` y `play_video` se podaba. Las fotos ya llevaban los dos números porque V2-548 pagó
    este incidente exacto para ellas; música y vídeo no. El canal probe no recorta tools, así que ningún
    caso de uso podía verlo — solo la voz en vivo."""
    for phrase in ("Enséñame una lista de vídeos de Artemis",
                   "búscame vídeos de recetas de paella",           # el ejemplo del propio doc de V2-402
                   "qué documentales hay sobre la luna",            # citado verbatim en la descripción de la tool
                   "búscame podcasts de historia"):
        kept, report = ts.select(FULL, turn_text=phrase)
        assert "play_video" in _names(kept), \
            f"«{phrase}» pierde play_video — la búsqueda de vídeos vuelve a escalar a un worker: {report}"


def test_y_la_charla_sigue_sin_arrastrar_la_familia_de_fotos():
    """Arreglar una recuperación no es dejar de recuperar. Las palabras nuevas son SEMILLAS, no un clasificador
    de intención: un turno que no habla de imágenes sigue sin cargar `media`."""
    for phrase in ("hola, ¿qué tal?", "¿qué tiempo hace mañana?", "apunta cena con Ana el jueves"):
        kept, report = ts.select(FULL, turn_text=phrase)
        assert "show_images" not in _names(kept), f"«{phrase}» no debería arrastrar media: {report}"
        assert "media" in report["omitted"], report


def test_una_tool_NUEVA_no_puede_entrar_en_una_familia_que_no_sabe_nombrarla():
    """El trinquete de la CLASE entera, no del caso (V2-548).

    Lo que pasó de verdad: la familia `media` GANÓ una tool —`show_images` (V2-457)— y las pistas de esa
    familia se quedaron con el vocabulario de música y vídeo de antes. Nadie tocó nada roto; simplemente la
    lista de semillas dejó de cubrir a uno de sus miembros, y ese miembro solo se podía recuperar por estado o
    por familia reciente. Un mes después el operador pidió una foto y el visor se abrió vacío.

    La comprobación es barata y no clasifica intención: las palabras del NOMBRE de la tool tienen que aparecer
    en las pistas de su familia. Es el mínimo — que la familia sepa nombrar a lo que contiene— y basta para que
    añadir una tool sin su semilla sea rojo en el mismo commit. Encontró un segundo agujero al escribirla:
    `reply_message` con pistas solo en castellano, perdido por «reply to the message from Claudia».
    """
    import re
    import unicodedata

    def _norm(x):
        n = unicodedata.normalize("NFKD", x or "")
        return "".join(c for c in n if not unicodedata.combining(c)).lower()

    huerfanas = []
    for fam, names in router.FAMILIES.items():
        if fam in ts.ALWAYS:
            continue                                   # nunca se recortan: no necesitan que nadie las recupere
        hints = set(ts._HINTS.get(fam) or ())
        assert hints, f"la familia «{fam}» es recortable y no tiene NINGUNA pista: solo entra por estado"
        for name in names:
            words = {w for w in re.split(r"[^a-z0-9]+", _norm(name)) if len(w) > 2}
            if not (words & hints):
                huerfanas.append((fam, name, sorted(words)))
    assert not huerfanas, (
        "tools que su propia familia no sabe recuperar — se podarán justo en los turnos que las piden: "
        f"{huerfanas}")


def test_toda_tool_del_catalogo_tiene_familia():
    """A tool without a family would ALWAYS slip through (the selector lets it pass by default, which is the safe
    side) and could never be trimmed. It is silent debt: better for it to be caught here."""
    huerfanas = _names(FULL) - set(ts._family_of)
    assert not huerfanas, f"tools sin familia en router.FAMILIES: {sorted(huerfanas)}"
