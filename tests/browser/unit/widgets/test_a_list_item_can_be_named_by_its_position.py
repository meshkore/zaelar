"""V2-595 — the reference resolver was BLIND to the widget that publishes the most items.

Measured live, session `abe9942b` (2026-09-05). Five Artemis videos in the youtube list, and:

    17:01:10  operator  «Vale, veo que me has puesto ahí una pequeña lista con cinco. Muéstrame el primero, arráncalo.»
    17:01:14  brain     🪟 'abrir/mostrar' puro → show · youtube (descartada play_item)      ← FAULT A
    17:01:14  voice     «Aquí lo tienes.»                       (card still «No hay ningún vídeo cargado»)
    17:01:28  operator  «No se está reproduciendo el primer vídeo de la lista.»
    17:01:33  widget    data:play_item → action_failed · item_not_found · «No encuentro ese vídeo en la lista.»  ← FAULT B
    17:01:33  voice     «Hecho.»

TWO independent faults, and either one alone is enough to make playback impossible:

A. `is_pure_show_request` classified the sentence as a PURE show. It carries a show verb («muéstrame») and no
   *change* verb — and correctly so, because nothing in `_CHANGE_VERB_RE` mutates a record. «Arráncalo» is a
   third class: ACTIVATION. So the guard of V2-545 did its job on a sentence it should never have judged, and
   threw the right action away.

B. `refs.id_field_for_action` found the item key by NAME SUFFIX («…id»). `youtube` declares `play_item`,
   `remove` and `move` with the key `item`, so the function answered None, `resolve()` replied «nothing to
   resolve» and handed the widget an EMPTY payload whatever the operator had said. V2-465 built `ref_index()`
   for this widget precisely so «play the third one» could resolve — it has been publishing its rows since, and
   nobody read them. Measured across the catalog: 3 of 133 actions, all three of them here.

And underneath B, two reference shapes that could not resolve for ANY widget: a bare INDEX («1»), which is the
primary interface every manifest documents, dropped by `_score`'s three-character floor; and an ORDINAL («el
primero»), the operator's own words, which matches no title.
"""
from __future__ import annotations

import pytest

from nucleo.flash.router_guards import is_pure_show_request
from widgets import refs


# ── FAULT A · an activation order is not a pure show ────────────────────────────────────────────────────────

def test_la_frase_MEDIDA_ya_no_se_lee_como_un_show_puro():
    assert is_pure_show_request("Muéstrame el primero, arráncalo.") is False


@pytest.mark.parametrize("frase", [
    "Enséñame la lista y reprodúcela",
    "Ábreme el vídeo y dale al play",
    "show me the first one and play it",
    "Muéstrame la playlist y empieza",
])
def test_otras_formas_de_ARRANCAR_tampoco(frase):
    assert is_pure_show_request(frase) is False


@pytest.mark.parametrize("frase", [
    "Muéstrame la agenda",
    "Ábreme el Telegram",
    "Enséñame las fotos",
    "Muéstrame el mensaje de Francisco",
])
def test_un_show_de_VERDAD_sigue_siendo_un_show(frase):
    """The other direction, and it is the half that keeps the guard alive: this predicate exists because «abre
    la agenda» once executed an invented `add_meeting`. Widening it until nothing is a pure show would «fix»
    this session by reopening that one."""
    assert is_pure_show_request(frase) is True


def test_un_verbo_de_CAMBIO_sigue_ganando():
    assert is_pure_show_request("Abre la agenda y apunta una cita") is False


def test_el_INICIO_no_es_iniciar():
    """`inici` is deliberately NOT in the activation list: it also matches the noun «el inicio», and a false
    positive here disarms the guard for a sentence that really is a pure show."""
    assert is_pure_show_request("Muéstrame el inicio de la lista") is True


# ── FAULT B · the widget publishes its index and the resolver reads it ──────────────────────────────────────

@pytest.mark.parametrize("action", ["play_item", "remove", "move"])
def test_las_tres_acciones_de_youtube_ya_tienen_campo(action):
    assert refs.id_field_for_action("youtube", action) == "item"


def test_una_accion_que_CREA_sigue_sin_tener_nada_que_resolver():
    """`add` takes a url and `play` takes nothing: inventing a field for them would send every reference into a
    payload key the widget does not read."""
    assert refs.id_field_for_action("youtube", "add") is None
    assert refs.id_field_for_action("youtube", "play") is None


def test_la_convencion_del_sufijo_sigue_valiendo_sin_declarar_nada():
    """A widget that names its key by the V2-026 convention keeps the answer it already had, byte for byte —
    `ref` is opt-in and the 13 other widgets declare none."""
    assert refs.id_field_for_action("agenda", "done") == "taskId"


def test_un_ref_que_NOMBRA_una_clave_que_la_accion_no_toma_es_ruido(monkeypatch):
    """A declaration is only worth what it points at: `ref: "chatId"` on an action whose payload has no such key
    would write the reference where the widget never reads."""
    monkeypatch.setattr(refs.runtime, "get",
                        lambda wid: {"actions": {"x": {"payload": {"item": "..."}, "ref": "chatId"}}})
    assert refs.id_field_for_action("w", "x") is None


def test_el_campo_NO_depende_de_que_la_lista_tenga_datos(tmp_path, monkeypatch):
    """The defect the first version of this fix had, and its own test caught: reading the answer out of
    `ref_index()` makes it DATA, so an empty list silently goes back to unresolvable."""
    monkeypatch.setattr(refs, "_ref_index", lambda wid: [])
    assert refs.id_field_for_action("youtube", "play_item") == "item"


def test_ninguna_otra_accion_del_catalogo_cambia_de_respuesta():
    """The measurement that made this safe to ship: 133 actions in the catalog, 3 change, and the 3 are the ones
    that were broken. Reimplementing the OLD heuristic here is the point — it is the baseline being compared
    against, not a copy of the code under test."""
    from widgets import runtime

    def sufijo_solo(wid: str, action: str):
        spec = ((runtime.get(wid) or {}).get("actions") or {}).get(action) or {}
        pl = spec.get("payload")
        if not isinstance(pl, dict):
            return None
        return next((k for k in pl if str(k).lower().endswith("id")), None)

    cambian = []
    for w in sorted(x.get("id") for x in runtime.catalog() if isinstance(x, dict) and x.get("id")):
        for a in ((runtime.get(w) or {}).get("actions") or {}):
            if sufijo_solo(w, a) != refs.id_field_for_action(w, a):
                cambian.append((w, a))
    assert sorted(cambian) == [("youtube", "move"), ("youtube", "play_item"), ("youtube", "remove")], cambian


# ── the two reference shapes that could not resolve for ANY widget ─────────────────────────────────────────

def _idx(n: int) -> list[dict]:
    titulos = ["Colonización Lunar", "Astronautas de Artemis II", "Programa Artemis explicado",
               "La NASA cambió el plan", "Cuatro astronautas a la Luna"]
    return [{"id": str(i + 1), "label": titulos[i], "field": "item"} for i in range(n)]


@pytest.mark.parametrize("ref,esperado", [
    ("el primero", "1"), ("la primera", "1"), ("first", "1"),
    ("la tercera", "3"), ("el segundo", "2"),
    ("1", "1"), ("3", "3"), ("5", "5"),
    ("el último", "5"), ("last", "5"),
])
def test_una_referencia_de_POSICION_resuelve(monkeypatch, ref, esperado):
    monkeypatch.setattr(refs, "_ref_index", lambda wid: _idx(5))
    r = refs.resolve("youtube", "play_item", ref, {})
    assert r.ok and r.payload == {"item": esperado}, (ref, r.ok, r.payload, r.needs)


@pytest.mark.parametrize("ref,esperado", [
    ("primer vídeo de la lista", "1"),          # the LIVE shape: what the model actually sends
    ("el primer vídeo", "1"),
    ("la primera canción", "1"),
    ("el último vídeo de la lista", "5"),
    ("el tercer elemento", "3"),
    ("primer resultado", "1"),
])
def test_el_CONTENEDOR_no_cuenta_como_contenido(monkeypatch, ref, esperado):
    """Measured against the running engine: with the card open, the model calls
    `play_item item="primer vídeo de la lista"`. «vídeo» and «lista» name the KIND and the CONTAINER, so the
    reference says nothing but «the first one» — the first version of this rule rejected it and the operator's
    own sentence went on failing after the fix."""
    monkeypatch.setattr(refs, "_ref_index", lambda wid: _idx(5))
    r = refs.resolve("youtube", "play_item", ref, {})
    assert r.ok and r.payload == {"item": esperado}, (ref, r.ok, r.payload, r.needs)


def test_un_CONTENEDOR_sin_ordinal_no_resuelve_nada(monkeypatch):
    """The other direction: dropping filler must not turn «vídeo de la lista» into a video."""
    monkeypatch.setattr(refs, "_ref_index", lambda wid: _idx(5))
    assert refs.resolve("youtube", "play_item", "vídeo de la lista", {}).ok is False


def test_un_TITULO_EXACTO_gana_a_cualquier_lectura_de_posicion(monkeypatch):
    """A list whose first row is literally «El primer vídeo» must be reachable by its name."""
    idx = _idx(3)
    idx[2]["label"] = "El primer vídeo"
    monkeypatch.setattr(refs, "_ref_index", lambda wid: idx)
    r = refs.resolve("youtube", "play_item", "El primer vídeo", {})
    assert r.ok and r.payload == {"item": "3"}, (r.ok, r.payload, r.needs)


def test_una_posicion_FUERA_DE_RANGO_no_se_inventa(monkeypatch):
    """Clamping to the last row would play a video the operator never named — the failure this module was
    written to prevent (V2-026: it must ASK instead of acting on the wrong item)."""
    monkeypatch.setattr(refs, "_ref_index", lambda wid: _idx(5))
    r = refs.resolve("youtube", "play_item", "9", {})
    assert not r.ok and r.needs == "no_match"


def test_una_referencia_que_dice_MAS_que_la_posicion_va_al_matcher(monkeypatch):
    """NARROW on purpose: the position word has to be all the reference carries. Otherwise «el primer episodio de
    Artemis» would be answered by row 1 instead of by the title that actually matches."""
    idx = _idx(3)
    idx[2]["label"] = "El primer alunizaje del programa Artemis"
    monkeypatch.setattr(refs, "_ref_index", lambda wid: idx)
    r = refs.resolve("youtube", "play_item", "el primer alunizaje", {})
    assert r.ok and r.payload == {"item": "3"}, (r.ok, r.payload, r.needs)


def test_un_titulo_sigue_resolviendo(monkeypatch):
    monkeypatch.setattr(refs, "_ref_index", lambda wid: _idx(5))
    r = refs.resolve("youtube", "play_item", "La NASA cambió el plan", {})
    assert r.ok and r.payload == {"item": "4"}


def test_SIN_referencia_se_PREGUNTA_en_vez_de_actuar(monkeypatch):
    """The turn that started all this asked for `play_item` with an empty payload. The honest answer is a
    question with the list in it, never a video chosen by us."""
    monkeypatch.setattr(refs, "_ref_index", lambda wid: _idx(5))
    r = refs.resolve("youtube", "play_item", "", {})
    assert not r.ok and r.needs == "ref" and len(r.candidates) == 5


def test_un_payload_que_YA_trae_un_id_valido_no_se_pisa(monkeypatch):
    monkeypatch.setattr(refs, "_ref_index", lambda wid: _idx(5))
    r = refs.resolve("youtube", "play_item", "el primero", {"item": "2"})
    assert r.ok and r.payload == {"item": "2"}


# ── end to end, against the widget's REAL data.py ─────────────────────────────────────────────────────────

def test_el_widget_ACEPTA_lo_que_el_resolvedor_produce(tmp_path, monkeypatch):
    """The two halves have to agree on the id space: `refs` hands over the published id and `_resolve_item`
    reads it. Resolving into a value the widget then rejects is the same `item_not_found` in a new place."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets import store
    import widgets.youtube.data as yt

    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path / "wd"), raising=False)
    lst = [{"videoId": f"v{i}", "title": t, "url": f"https://y/{i}"}
           for i, t in enumerate(["Colonización Lunar", "Astronautas de Artemis II",
                                  "Programa Artemis explicado", "La NASA cambió el plan",
                                  "Cuatro astronautas a la Luna"], start=1)]
    store.save("youtube", {"list": lst, "pos": -1})

    r = refs.resolve("youtube", "play_item", "el tercero", {})
    assert r.ok, (r.needs, r.candidates)
    res = yt.apply_action("play_item", r.payload)
    assert res.get("ok") is True, res
    assert store.load("youtube").get("pos") == 2
