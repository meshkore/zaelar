"""V2-756 — «ponme el vídeo número tres» · «bórrame los tres últimos» · «Para el vídeo», otra vez.

MEASURED, live session 74be8e9a (2026-09-23, 13:5x, engine 3.33+07bbe20a — the V2-755 build). What
V2-755 fixed held: «Vuelve al catálogo» → `show_tab` 0.96, obeyed; the errand harness opened a goal
and CLOSED it («✅ arnés: objetivo conseguido») instead of declaring the card empty forever. Five new
defects, each a different layer, each pinned below.

    +27.7  🗣  «Ahora quiero que me pongas el vídeo número tres»
           jev screen_action → youtube:play_result 0.95
           the model called play_video(action=list) — a fresh SEARCH of the same query
    +39.5  🗣  «Bueno, ponme el vídeo dos, QUE LOS HAS CAMBIADO.»     ← the band had renumbered
    +51.3  🗣  «¿Puedes, por favor, reproducir el video número dos?»   ← searched a third time
    +78.0  🗣  «Para el vídeo»
           jev screen_action → youtube:pause 0.95 · request_type answer 0.49 / comment 0.39
           nothing fired; the reply said «Ahí lo tienes reproduciéndose, Paco.»
    +90.4  🗣  «He dicho que pares el vídeo. Que no me has oído.»
    +128.6 🗣  «Pausa el vídeo. Vuelve al catálogo.»
           the model called widget_data(youtube, show_tab) with an EMPTY payload → `unknown_tab`
    +138.6 🗣  «¿Has ignorado la orden que te he dado?»
    +188.3 🗣  «Bórrame los tres últimos de la cola.»
           jev screen_action → youtube:remove 0.95 · the model sent item:"6" and ONE row went
           the reply said «quito el 4, el 5 y el 6 … y te dejo los tres primeros»
    +201.6 🗣  «Pero solo he visto que has borrado el número seis.»
    +241.0 🗣  «Eso es absurdo, no estás entendiendo la tarea.»

## 1 · A SEARCH is a question, and asking it twice must not change the answer

The band is what his numbers refer to. Re-running the same query re-fetched and renumbered it under
him — «que los has cambiado» is him reading the defect out loud. The same question over the same band
is now ANSWERED, not re-run: nothing renumbers, nothing is re-fetched, and the call says `unchanged`
so a channel can tell a real search from one that did nothing.

## 2 · «los tres últimos» had no way to be said

`remove` took one `item`. Its mirror `add_results` has taken «1,3» since V2-632; this one never did,
and one action per turn is the rule — so the model understood perfectly, said «quito el 4, el 5 y el
6», and deleted one row. Worse, the paid verdict with nothing better to reach for answered
`clear_list` at 0.56 over a *different* candidate set — the action that empties the WHOLE queue
(V2-742's pattern exactly). Measured with the failing turn's own 50 candidates, after declaring the
plural: «Bórrame los tres últimos de la cola» → `remove` **0.98**, «quita el cuatro y el cinco» →
`remove` **1.00**, and «vacía la cola entera» stays `clear_list` **0.94**.

## 3 · A number he SAID is not an invention

V2-741 refuses to invent a payload, and it is right. But «el vídeo número tres» over a numbered band
is not an invention, it is a reading — the same class as V2-754's declared alias, and it is what lets
the verdict complete a turn the model left empty on an action whose one key is an index.

## 4 · The model left a declared key empty and the widget threw the order away

`show_tab` with no `tab` → `unknown_tab`, over a sentence that names the face («al catálogo» IS
`inicio`, declared in the manifest). `fill_missing` only ever ADDS a key the call left empty, and only
from an alias or a said number. And one alias had to go: `player` was declared as «reproductor, el
vídeo» — on a VIDEO card «el vídeo» matches nearly every sentence, so it disambiguated nothing and
made «Pausa el vídeo. Vuelve al catálogo.» name two faces at once.

## 5 · An unsure reader was vetoing a near-certain one

The request-type gate required a confident `order`/`answer`. «Para el vídeo» is an order, and its
request type measured comment 0.45 — unsure — while the screen question answered `pause` 0.95. The
gate is now a REFUSAL list, and the measurement that chose it is in `NOT_AIMED_AT_THE_SCREEN`: every
ambient remark tested answers `none` 0.87-0.99 on the screen question, so the guard that matters was
never this one.

Run: .venv/bin/pytest tests/voice/unit/test_a_number_he_said_is_not_an_invention.py
"""
from __future__ import annotations

import json
import pathlib
import threading

import pytest

from nucleo.flash import direct_action as _da
from nucleo.flash import turn_brief as _tb
from voice import observer as _obs
from widgets import store
from widgets.youtube import data as yt

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_MANIFEST = _ENGINE / "widgets/youtube/manifest.json"

#: His sentences, verbatim from the transcript. A paraphrase would be a test of a test.
HIS_THIRD = "Ahora quiero que me pongas el vídeo número tres"
HIS_LAST_THREE = "Bórrame los tres últimos de la cola."
HIS_CATALOG = "Pausa el vídeo. Vuelve al catálogo."


def _acts() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))["actions"]


@pytest.fixture
def card(monkeypatch, tmp_path):
    """His state: six numbered results and six rows queued. NEVER the operator's real card."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store.save(yt.WID, {
        "videoId": "", "pos": -1,
        "list": [{"videoId": f"V{i}", "title": f"vid {i}"} for i in range(1, 7)],
        "search_results": [{"videoId": f"R{i}", "title": f"res {i}"} for i in range(1, 7)],
        "search_query": "Apolo 11 documental"})


def _band(): return [r["title"] for r in (store.load(yt.WID) or {}).get("search_results") or []]
def _queue(): return [r["title"] for r in (store.load(yt.WID) or {}).get("list") or []]


# ── 1 · THE SAME QUESTION OVER THE SAME BAND DOES NOT MOVE HIS NUMBERS ────────────────────────────

def test_re_running_the_same_search_changes_nothing(card, monkeypatch):
    """«que los has cambiado». A search that re-fetches must never be reachable from a repeat."""
    monkeypatch.setattr(yt, "_search_many", lambda *a, **k: pytest.fail("it went to the network again"))
    r = yt.apply_action("search", {"query": "Apolo 11 documental"})
    assert r["ok"] and r["unchanged"] is True and r["count"] == 6
    assert _band() == [f"res {i}" for i in range(1, 7)], "the numbers he is reading stayed put"


def test_the_same_question_survives_punctuation_and_case(card, monkeypatch):
    monkeypatch.setattr(yt, "_search_many", lambda *a, **k: pytest.fail("it went to the network again"))
    assert yt.apply_action("search", {"query": "  APOLO 11 DOCUMENTAL "})["unchanged"] is True


def test_a_DIFFERENT_search_still_replaces_the_band(card, monkeypatch):
    """The bound: results are a view of the LAST question (V2-402), not an archive. A new question
    gets a new answer — this only refuses to re-ask the one already on screen."""
    monkeypatch.setattr(yt, "_search_many",
                        lambda q, n: [{"videoId": "Z1", "title": "Boeing 747", "channel": "", "published": ""}])
    r = yt.apply_action("search", {"query": "Boeing 747"})
    assert r["ok"] and not r.get("unchanged") and _band() == ["Boeing 747"]


def test_an_unchanged_search_SAYS_so_so_a_channel_can_tell(card, monkeypatch):
    """A call that changed nothing has to be distinguishable from one that did — otherwise the turn
    looks acted-upon and the operator is looking at a screen that never moved."""
    monkeypatch.setattr(yt, "_search_many", lambda *a, **k: [])
    assert yt.apply_action("search", {"query": "Apolo 11 documental"}).get("unchanged") is True


# ── 2 · «BÓRRAME LOS TRES ÚLTIMOS» ────────────────────────────────────────────────────────────────

def test_remove_takes_several_and_deletes_every_one_of_them(card):
    r = yt.apply_action("remove", {"items": "4,5,6"})
    assert r["ok"] and r["count"] == 3
    assert _queue() == ["vid 1", "vid 2", "vid 3"], "he asked for three and three went"
    assert r["removed"] == ["vid 4", "vid 5", "vid 6"], "…and the ack names each one, in his order"


def test_removing_several_does_not_eat_the_wrong_rows(card):
    """Popping ascending shifts every later index by one — the classic. Highest first, or «4,5,6»
    silently deletes 4, 6 and whatever slid into place."""
    yt.apply_action("remove", {"items": "1,3,5"})
    assert _queue() == ["vid 2", "vid 4", "vid 6"]


def test_removing_several_keeps_what_is_playing_pointing_at_itself(card):
    store.save(yt.WID, {**(store.load(yt.WID) or {}), "videoId": "V5", "pos": 4})
    assert yt.apply_action("remove", {"items": "1,2"})["count"] == 4, "the two rows went"
    assert _queue()[(store.load(yt.WID) or {})["pos"]] == "vid 5", "«last played» still means vid 5"


def test_removing_ONE_is_untouched(card):
    """Today's path, bit for bit: `item` by number or by title still works."""
    assert yt.apply_action("remove", {"item": "2"})["ok"]
    assert _queue() == ["vid 1", "vid 3", "vid 4", "vid 5", "vid 6"]
    assert yt.apply_action("remove", {"item": "vid 4"})["ok"]
    assert _queue() == ["vid 1", "vid 3", "vid 5", "vid 6"]


def test_remove_DECLARES_the_plural_so_a_reader_can_find_it(card):
    """The repair lives in the widget's own declaration (V2-726 §4-bis) — with `clear_list` the only
    declared way to touch several rows, the verdict reached for the one that empties everything."""
    remove = _acts()["remove"]
    assert "items" in (remove.get("payload") or {}), "the plural has to be DECLARED, not just accepted"
    assert "varios" in remove["desc"].lower() and "clear_list" in remove["desc"], (
        "…and it has to name its neighbour, which is the action that empties the whole queue")
    assert len(remove["desc"]) <= _tb.MAX_DESC_CHARS, "a declaration that does not fit decides nothing"


# ── 3 · A NUMBER HE SAID ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said,want", [
    (HIS_THIRD, 3),
    ("Bueno, ponme el vídeo dos, que los has cambiado.", 2),
    ("¿Puedes, por favor, reproducir el video número dos?", 2),
    ("ponme el 6", 6),
    ("reproduce el primero", 1),
])
def test_a_number_he_said_fills_an_index_key(said, want):
    assert _da.number_fill("youtube", "play_result", said) == {"item": want}


@pytest.mark.parametrize("said,why", [
    ("el dos y el tres", "two different numbers is «which one?», not a fill"),
    ("ponme uno de esos", "«uno» as an article names nothing"),
    ("pon un vídeo del Apolo 11", "no index at all"),
])
def test_what_is_NOT_a_number_he_said(said, why):
    got = _da.number_fill("youtube", "play_result", said)
    assert got == {} or list(got.values()) == [1], why


def test_a_number_never_fills_a_key_that_is_not_an_INDEX():
    """V2-741's refusal, intact: `load` takes a query and «ponme el tres» is not one."""
    assert _da.number_fill("youtube", "load", "ponme el tres") == {}
    assert _da.number_fill("youtube", "search", "búscame tres vídeos") == {}


# ── 4 · THE KEY THE MODEL LEFT EMPTY ──────────────────────────────────────────────────────────────

def test_the_model_leaving_the_face_out_is_repaired_from_his_own_sentence():
    assert _da.fill_missing("youtube", "show_tab", {}, HIS_CATALOG) == {"tab": "inicio"}
    assert _da.fill_missing("youtube", "show_tab", {}, "enséñame la cola") == {"tab": "cola"}


def test_a_call_that_CARRIES_its_key_is_never_edited():
    """It repairs an omission; it never overrules a decision (V2-754's rule, unmoved)."""
    assert _da.fill_missing("youtube", "show_tab", {"tab": "cola"}, "vuelve al catálogo") == {}


def test_nothing_is_filled_when_his_words_name_two_faces_or_none():
    assert _da.fill_missing("youtube", "show_tab", {}, "no sé, lo que quieras") == {}
    assert _da.fill_missing("youtube", "show_tab", {}, "del reproductor a la cola") == {}


def test_an_action_with_no_key_and_one_with_only_optional_keys_are_left_alone():
    assert _da.fill_missing("youtube", "pause", {}, "para el vídeo") == {}
    assert _da.fill_missing("youtube", "load", {}, "ponme algo de jazz") == {}


def test_the_alias_that_matched_EVERY_sentence_is_gone():
    """`player` was «reproductor, el vídeo». On a video card «el vídeo» is in almost every sentence, so
    it disambiguated nothing and made his order name two faces at once."""
    tab = _acts()["show_tab"]["payload"]["tab"]
    assert "reproductor" in tab, "the face keeps the word that actually names it"
    assert "(reproductor, el vídeo)" not in tab


def test_the_provider_asks_for_the_repair_before_the_widget_refuses():
    body = (_ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "_direct_action.fill_missing(_cd[\"card\"], action_name, res.payload," in body
    assert body.index("_direct_action.fill_missing") < body.index(
        '_apply_widget_data(_cd["card"], action_name, res.payload, ref)'), \
        "a key filled AFTER the call is applied repairs nothing"


# ── 5 · THE GATE THAT LET AN UNSURE READER VETO A NEAR-CERTAIN ONE ────────────────────────────────

def _brief(answers: dict, *, open_ids=("youtube",)):
    ev = threading.Event(); ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


@pytest.fixture
def on_screen(monkeypatch):
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)


def _fire(brief, said):
    seen = []
    done = _da.complete(brief, operator_text=said, emit=lambda *a, **k: None,
                        present=lambda *a, **k: None,
                        apply_widget_data=lambda w, a, p: seen.append((w, a, p)))
    return done, seen


def test_an_UNSURE_request_type_no_longer_vetoes_a_near_certain_screen_verdict(on_screen):
    """His «Para el vídeo»: pause 0.95 on the screen question, comment 0.45 on the other one."""
    brief = _brief({_tb.TARGET_KEY: ("youtube:pause", 0.95), _tb.REQUEST_KEY: ("comment", 0.45)})
    done, seen = _fire(brief, "Para el vídeo")
    assert done == "pause" and seen == [("youtube", "pause", {})]


@pytest.mark.parametrize("kind", ["comment", "question", "greeting"])
def test_a_CONFIDENT_remark_still_moves_nothing(on_screen, kind):
    """The measured guard, kept: «¿el siguiente es de la NASA?» reads question 1.00."""
    brief = _brief({_tb.TARGET_KEY: ("youtube:next", 0.99), _tb.REQUEST_KEY: (kind, 0.95)})
    assert _fire(brief, "¿el siguiente es de la NASA?") == ("", [])


@pytest.mark.parametrize("kind", ["order", "answer", "complaint"])
def test_an_order_an_answer_and_a_COMPLAINT_all_pass(on_screen, kind):
    """`complaint` is deliberately not refused: a complaint about what was just done is an order to do
    it properly (V2-750, node 2.70)."""
    brief = _brief({_tb.TARGET_KEY: ("youtube:pause", 0.95), _tb.REQUEST_KEY: (kind, 0.95)})
    assert _fire(brief, "para el vídeo")[0] == "pause"


def test_the_refusal_list_is_a_named_constant_with_its_measurement():
    assert _da.NOT_AIMED_AT_THE_SCREEN == ("comment", "question", "greeting")
    body = (_ENGINE / "nucleo/flash/direct_action.py").read_text(encoding="utf-8")
    assert "none 0.95" in body and "comment  0.45" in body, "the numbers that chose it stay next to it"


def test_the_verdict_can_now_complete_a_turn_with_the_number_he_said(on_screen):
    """T2 of the session, simulated: the model spends its turn elsewhere, the brief says `play_result`
    and his sentence carries the 3."""
    brief = _brief({_tb.TARGET_KEY: ("youtube:play_result", 0.95), _tb.REQUEST_KEY: ("order", 0.98)})
    done, seen = _fire(brief, HIS_THIRD)
    assert done == "play_result" and seen == [("youtube", "play_result", {"item": 3})]


# ── 6 · THE RECORD HAS TO SAY WHAT THE MODEL HAD IN FRONT OF IT ───────────────────────────────────

def test_the_prompt_excerpt_keeps_what_is_ON_SCREEN():
    """Third time this excerpt has cost a diagnosis (V2-195 lost the tail, V2-255 the memory). The
    on-screen band lives in the middle, and answering «did it know?» meant reconstructing the digest by
    hand against a store that had already moved on."""
    screen = ("items ahora (de lo ABIERTO — referéncialos por lenguaje natural):\n"
              "- youtube (contenido en pantalla):\n  1. Apolo 11\n  2. El Viaje a La Luna\n")
    out = _obs._prompt_excerpt("H" * 6000 + "relleno " * 600 + screen + "relleno " * 600 + "T" * 7000)
    assert "2. El Viaje a La Luna" in out, "the record cannot answer «did the model see the band?»"
    assert "OMITIDOS del centro" in out, "…and it still says what it dropped"


def test_a_short_prompt_is_still_returned_whole():
    assert _obs._prompt_excerpt("corto") == "corto"


def test_a_prompt_with_no_screen_block_behaves_exactly_as_before():
    out = _obs._prompt_excerpt("H" * 6000 + "x" * 4000 + "T" * 7000)
    assert "OMITIDOS del centro" in out and out.startswith("H") and out.endswith("T")


def test_the_screen_slice_is_BOUNDED():
    """This is the excerpt, not the prompt: a long screen is cut with its own marker rather than
    swallowing the budget the head and the tail are there to protect."""
    big = "items ahora (de lo ABIERTO" + "z" * 20_000
    out = _obs._prompt_excerpt("H" * 6000 + big + "T" * 7000)
    assert "pantalla recortada" in out and len(out) < 6000 + 7000 + _obs._ON_SCREEN_MAX + 500


# ── 7 · THE DISAGREEMENT THAT LEFT NO TRACE ───────────────────────────────────────────────────────

def test_a_global_tool_that_disagrees_with_the_verdict_is_RECORDED():
    """The model's call still runs (V2-754). But the `⚖️` line only ever lived inside the widget_data
    branch, so three turns of `play_video` against a `play_result` verdict left no trace at all — and
    «who should we believe here?» cannot be answered without one."""
    body = (_ENGINE / "nucleo/flash/video_turn.py").read_text(encoding="utf-8")
    assert '_da.completes(brief, "youtube", model_action=op)' in body
    assert "⚖️ el modelo y el veredicto discrepan" in body
    assert body.index("_da.completes") < body.index('apply_widget_data("youtube", op,'), \
        "recorded before the call runs, so a crash in the emit cannot swallow the action"
