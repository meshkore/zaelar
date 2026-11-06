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


def test_REANUDAR_tambien_es_arrancar():
    """Resuming playback is the same order as starting it — without `reanud` this sentence read as a pure show
    and the correct `play_item` was discarded, fault A with a different verb."""
    assert is_pure_show_request("Muéstrame el vídeo y reanúdalo") is False


def test_pero_el_RESUMEN_sigue_siendo_un_show():
    """`resum` is deliberately NOT in the activation list, same reasoning as `inici`: «el resumen» and «la
    versión resumida» are nouns that ride along with genuine show orders."""
    assert is_pure_show_request("Muéstrame el resumen") is True
    assert is_pure_show_request("Enséñame la versión resumida") is True


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


def test_ninguna_otra_accion_del_catalogo_cambia_de_respuesta():
    """The measurement that made this safe to ship: 133 actions in the catalog, 3 change, and the 3 are the ones
    that were broken. Reimplementing the OLD heuristic here is the point — it is the baseline being compared
    against, not a copy of the code under test.

    V2-708 added FIVE more, and they are the whole blast radius of that batch: the agenda actions that act on
    a meeting that already exists. Every one of them declared `title` (no key ends in `id`) and answered
    None, so the resolver threw away the item the model named and dispatched an empty payload — five
    `cancel_meeting {}` in one session over an index that held the appointment. No other widget moves:
    `contactos` already names its key `contactId`, and the rest declare `ref` explicitly. That is what this
    list is for — if a name ever appears here without a batch that explains it, somebody widened the reach
    of the resolver without saying so. `dedupe_meetings` joined them in V2-710: «simplify to one» is a sixth
    action on a meeting that already exists.

    V2-744 added FIVE more, and they are one batch again: the agenda's TASKS section. A task is named by
    its number in a list («la 2 de la compra») or by its title, and a LIST by its number or its name, so
    neither selector can be a key ending in `id` — they declare `ref` for exactly the reason the meeting
    actions above did. `done` is deliberately NOT among them: it keeps `taskId` and the V2-026 suffix
    convention, because `refs` has been resolving «márcame hecha la del daemon» into that key since the
    convention existed, and there was nothing there to fix.

    V2-764 added ONE: `archivos:torrent_download`. A catalogue row is named by its number or its title («la
    segunda», «la de 720p»), so it declares `ref: item` — and a live download keeps `id`, a different field, so
    «la segunda» of the catalogue can never cancel the second download.

    The demo week added SEVEN, each in its own batch (V2-778 F6-43 wrote them down): `agenda:open_meeting`
    (V2-770, a meeting named by its title, like its siblings above); `imagenes:select` and `map:select`
    (6be74d91, a picture or a place named by its position or title); `documento:goto` (761f5e2a, a passage
    named by its text); and `mensajeria:open` / `unread` / `forward` (7ba9f2f1, 5f6d2a81, a message named by
    its sender or subject — «the mail from Inworld»)."""
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
    assert sorted(cambian) == [
        ("agenda", "cancel_meeting"), ("agenda", "clear_list"), ("agenda", "dedupe_meetings"),
        ("agenda", "delete_list"), ("agenda", "delete_task"), ("agenda", "move_meeting"),
        ("agenda", "open_meeting"), ("agenda", "rename_list"), ("agenda", "rsvp_meeting"),
        ("agenda", "set_reminder"), ("agenda", "update_meeting"), ("agenda", "update_task"),
        ("archivos", "torrent_download"),
        ("documento", "goto"),
        ("imagenes", "select"),
        ("map", "select"),
        ("mensajeria", "forward"), ("mensajeria", "open"), ("mensajeria", "unread"),
        ("youtube", "move"), ("youtube", "play_item"), ("youtube", "remove"),
    ], cambian


# ── the two reference shapes that could not resolve for ANY widget ─────────────────────────────────────────

def _idx(n: int) -> list[dict]:
    titulos = ["Colonización Lunar", "Astronautas de Artemis II", "Programa Artemis explicado",
               "La NASA cambió el plan", "Cuatro astronautas a la Luna"]
    return [{"id": str(i + 1), "label": titulos[i], "field": "item"} for i in range(n)]


def test_una_fila_sin_label_no_rompe_la_promesa_de_no_lanzar(monkeypatch):
    """`resolve` promises it NEVER raises. A widget publishing a row without `label` used to be able to break
    that (KeyError in the exact-title pass and in every candidates list) — such a row is unusable by every
    consumer, so the index filters it out."""
    import sys
    import types
    mod = types.ModuleType("widgets.fakew.data")
    mod.ref_index = lambda: [{"id": "1", "field": "item"},                       # no label → filtered
                             {"id": "2", "field": "item", "label": "Bueno"}]
    monkeypatch.setitem(sys.modules, "widgets.fakew", types.ModuleType("widgets.fakew"))
    monkeypatch.setitem(sys.modules, "widgets.fakew.data", mod)
    assert refs._ref_index("fakew") == [{"id": "2", "field": "item", "label": "Bueno"}]
    monkeypatch.setattr(refs.runtime, "get",
                        lambda wid: {"actions": {"x": {"payload": {"item": "..."}, "ref": "item"}}})
    r = refs.resolve("fakew", "x", "el primero", {})
    assert r.ok and r.payload == {"item": "2"}   # the only referable row IS row one of the published list


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


# ── demo pass 2026-09-28, I3 — his SENTENCE is the reference, verb included ────────────────────────────────

def test_a_widget_that_resolves_its_own_references_gets_his_words(monkeypatch):
    """F2 (demo pass 2026-09-28): «go to the part about the complaints against the king» → `goto {}` → «no
    encuentro ese pasaje». The document publishes no row index — it matches passages itself — so his words fill
    the empty reference key and its matcher finds «The Grievances Against the King»."""
    r = refs.resolve("documento", "goto", "", {}, order="go to the part about the complaints against the king")
    assert r.ok and r.payload == {"text": "go to the part about the complaints against the king"}
    r2 = refs.resolve("documento", "goto", "", {"text": "Grievances"}, order="whatever he said")
    assert r2.payload == {"text": "Grievances"}, "a key the model filled is never overwritten"
