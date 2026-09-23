"""V2-755 — «Vale, para el vídeo» · «ponme el vídeo número seis» · and a full card declared EMPTY.

MEASURED, live session 665e666a (2026-09-23, 13:0x, engine 3.33+948a49bc — the V2-754 build). The
operator opened the video card, searched Apollo 11, played the second result, and then hit THREE
separate defects in ninety seconds. Each one is a different layer, and each one is pinned below.

    +138.3  🗣    «Vale, para el vídeo.»
            jev  screen_action → none 0.65  (pause 0.05 · close 0.19)
            the model fired NO tool and said «…vale, le doy al pause.»
    +148.9  🗣    «No le estás dando a la pausa.»          ← he had to say it twice
    +156.9  🗣    «Ahora sí, ¿por qué? Lo has hecho a la segunda. … Yo no tengo por qué estar
                  repitiendo las acciones.»
    +168.0  🗣    «Vuelve, por favor, al inicio. Al catálogo inicial.»   → show_tab 0.97 ✓ (V2-754 held)
    +176.3  🗣    «Vale, ahora ponme el vídeo número seis.»
            →    play_result{item: 6} fired, arbiter allowed it, the sixth video swapped in
    +201.4  🗣    «No lo estás poniendo.»                   ← nothing had changed on screen
    +211.8  🗣    «Coge el vídeo número seis y reprodúcelo.»  → play_result{item: 6}, again
    +220.3  🗣    «No lo consigues.»                        ← the third try was eaten as a re-emit
    +222.9  🗣    «Paro aquí y arreglamos.»

## 1 · «para el vídeo» is a PAUSE, and `close` had taken the verb

`pause` was declared in four words — «pausa el vídeo» — while `close`, fattened by V2-753 to win
«Páralo, y vuelve al inicio», opened with «PARA el vídeo de verdad». So the one sentence spelled with
the bare verb belonged to nobody: `para` is also the PREPOSITION, «Vale, para el vídeo.» reads as
«OK, for the video.», and the verdict came back `none` — twice, over a paid question whose whole job
was that sentence. Measured against the real API over the session's own 47 candidates:

    «Vale, para el vídeo.»                   none 0.67  →  youtube:pause    0.98
    «para el vídeo»                          none 0.82  →  youtube:pause    0.60
    «vuelve al inicio del widget de vídeo»  restart 0.69 →  youtube:show_tab 0.94   ← open since V2-754
    «Páralo, y vuelve al al inicio.»        close 0.94  →  youtube:close    0.89   ← V2-753's case, held
    quita/cierra/basta ya → close 0.98-1.00 · «ponlo otra vez desde el principio» → restart 1.00
    play 0.93 · next 0.97 · play_result 0.82 — unmoved

## 2 · …and the third descriptor was still being decapitated

V2-753 raised the cut from 90 to 200 because a beheaded declaration routes nothing. The `show_tab`
descriptor V2-754 then WROTE is 485 characters, so «al inicio del widget de vídeo» — the phrase put
there for exactly this — never reached the question, and his sentence came back `restart` again. The
cut is not the bug; writing past it is. 48 of the 220 declared actions in this house are over it
today, and that number is the ratchet below.

## 3 · A video ARRIVING is not the same as a video SWAPPING, and only one of them was shown

`widget.js` jumps to the player when a video lands on a card that had none (`!st.key.slice(2)`). He
was on the catalog with the second video still loaded, so swapping the sixth in changed no face: the
order ran, twice, invisibly, and the third attempt was correctly deduped as a re-emit of an action
that HAD run. The rule the redesign already states («leaving the dashboard up while it plays
underneath is the confusion this exists to end») now lives in the data layer, where the ORDER is
known, on the same `goto_tab` rail V2-742 built — and the automatic advance at the end of a video
does not write it, because reading the queue while one plays is a thing he does.

## 4 · The harness told the model an empty sheet, for three minutes, over a full card

Every turn of that session carried «OBJETIVO ABIERTO (arnés): «Vale, muéstrame el widget de vídeo» →
la hoja `youtube` sigue VACÍA. No digas que está hecho ni "aquí lo tienes"» — with six numbered
results and a playing video on the card. `harness.verify` returns None for a widget that does not
declare `empty` and the module's own rule is to stay silent then; `prompt_lines` never asked it and
printed every open goal as VACÍA. Both halves are repaired: the prompt only speaks for a goal a
verifier found unmet, and the video card answers the question it was never answering.

Run: .venv/bin/pytest tests/voice/unit/test_an_order_to_play_shows_the_player.py
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from nucleo import harness
from nucleo.flash import turn_brief as _tb
from widgets import store
from widgets.youtube import data as yt

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_MANIFEST = _ENGINE / "widgets/youtube/manifest.json"
_CARD = _ENGINE / "widgets/youtube/widget.js"

#: His sentences, verbatim from the transcript. A paraphrase would be a test of a test.
HIS_PAUSE = "Vale, para el vídeo."
HIS_SIXTH = "Vale, ahora ponme el vídeo número seis."


def _acts() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))["actions"]


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """The widget store in a temp dir. A unit test NEVER touches the operator's real card."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))


@pytest.fixture
def watching_from_the_catalog(sandbox):
    """His exact state: six results on the dashboard, the SECOND one loaded in the player."""
    db = {"videoId": "AAAAAAAAAA2", "title": "Viaje a la Luna", "paused": True, "pos": -1,
          "search_results": [{"videoId": f"VVVVVVVVVV{i}", "title": f"Apolo {i}", "channel": "NASA",
                              "url": f"https://www.youtube.com/watch?v=VVVVVVVVVV{i}"}
                             for i in range(1, 7)],
          "search_query": "Apolo 11", "list": []}
    store.save(yt.WID, db)
    return db


# ── 1 · THE DECLARATIONS THAT ROUTE HIS SENTENCE ──────────────────────────────────────────────────

def test_pause_claims_the_sentence_he_actually_says():
    """The repair lives in the widget's own declaration (V2-726 §4-bis) so it reaches every reader.

    The homograph is the whole defect and the descriptor has to name it: without «es el verbo, no la
    preposición» the same 200 characters measured `none` 0.47 — better than 0.67, still not an order.
    """
    pause = _acts()["pause"]["desc"].lower()
    assert "para el vídeo" in pause, "«Vale, para el vídeo» is the sentence that came back `none` twice"
    assert "preposición" in pause, (
        "«para» is also a preposition — «Vale, para el vídeo.» reads as «OK, for the video.». Naming "
        "that is what took the verdict from none 0.47 to pause 0.98")
    assert "cargado" in pause or "congelado" in pause, "and it has to say the video STAYS, unlike close"


def test_close_stops_claiming_the_bare_verb_but_still_says_it_STOPS():
    """V2-753 anchored on the literal «para» inside `close`, because the competitor then was `restart`.

    The competitor now is `pause`, and that literal is precisely what swallowed his sentence — so the
    anchor moves onto the CLAIM: close has to say it stops for real AND empties the card, which is what
    distinguishes it. Its own four wordings still measure 0.89-1.00 (see the header).
    """
    close = _acts()["close"]["desc"].lower()
    assert "deja de sonar" in close and "sin vídeo" in close, "close has to SAY that it stops it for real"
    assert "quita" in close, "…and that the card is left EMPTY — that is the half `pause` does not do"
    assert "párralo y vuelve al inicio" in close, "V2-753's compound order stays its own (measured 0.89)"


def test_show_tab_still_carries_the_phrase_that_makes_it_routable():
    """V2-742 wrote «al inicio del widget» into the manifest so the decision could find the action.
    V2-753 raised the cut to 200 to let it through. V2-754 then wrote 485 characters and it was cut
    again — «vuelve al inicio del widget de vídeo» measured `restart` 0.69 in this session."""
    show_tab = _acts()["show_tab"]["desc"].lower()
    assert "al inicio del widget" in show_tab
    assert "catálogo" in show_tab


@pytest.mark.parametrize("name", ["pause", "close", "show_tab", "restart", "play_result"])
def test_the_declarations_this_incident_touched_FIT_the_question(name):
    """A description is product data and the right place to repair a routing miss — but only the part
    that ARRIVES can decide anything (V2-753). Third time this class has cost a live session."""
    desc = _acts()[name]["desc"]
    assert len(desc) <= _tb.MAX_DESC_CHARS, (
        f"`{name}` is {len(desc)} chars and the question carries {_tb.MAX_DESC_CHARS}: "
        f"«{desc[_tb.MAX_DESC_CHARS:]}» never reaches any reader")


#: Declared debt, measured 2026-09-23: descriptors longer than `MAX_DESC_CHARS` across every widget.
#: They reach the screen question BEHEADED and nothing says so. This may only go DOWN — the ratchet
#: exists because the same defect has now been paid for three times (V2-742, V2-753, V2-755) and a
#: silent cut is invisible until a live session hits it.
BEHEADED_DESCRIPTORS = 45


def test_the_beheaded_declarations_are_declared_debt_and_only_shrink():
    over = [f"{mf.parent.name}:{k} ({len(str((v or {}).get('desc') or ''))})"
            for mf in sorted((_ENGINE / "widgets").glob("*/manifest.json"))
            for k, v in (json.loads(mf.read_text(encoding="utf-8")).get("actions") or {}).items()
            if len(str((v or {}).get("desc") or "")) > _tb.MAX_DESC_CHARS]
    assert len(over) <= BEHEADED_DESCRIPTORS, (
        f"{len(over)} declarations are cut before they can decide anything (was {BEHEADED_DESCRIPTORS}): "
        + ", ".join(sorted(over)[:6]))


# ── 2 · AN ORDER TO PLAY BRINGS THE PLAYER'S FACE FORWARD ─────────────────────────────────────────

def _goto(db: dict) -> dict:
    return (store.load(yt.WID) or {}).get("goto_tab") or {}


def test_playing_a_result_from_the_catalog_shows_the_player(watching_from_the_catalog):
    """His «ponme el vídeo número seis»: the action ran and the screen did not move, because the card
    already HAD a video and the jump only fires on a card that had none."""
    r = yt.apply_action("play_result", {"item": 6})
    assert r["ok"] and r["position"] == 6
    assert (store.load(yt.WID) or {}).get("videoId") == "VVVVVVVVVV6", "the sixth is in the player"
    assert _goto(store.load(yt.WID))["tab"] == "player", (
        "he asked to WATCH it — leaving the catalog up while it plays underneath is the confusion "
        "the V2-596 redesign exists to end, and a swap is as much an arrival as a first video")


def test_playing_a_queue_item_shows_the_player(sandbox):
    store.save(yt.WID, {"videoId": "AAAAAAAAAA1", "pos": 0, "list": [
        {"videoId": "AAAAAAAAAA1", "title": "uno"}, {"videoId": "BBBBBBBBBB2", "title": "dos"}]})
    yt.apply_action("play_item", {"item": 2})
    assert _goto(store.load(yt.WID))["tab"] == "player"


def test_the_order_is_a_SEQUENCE_so_two_in_a_row_both_arrive(watching_from_the_catalog):
    """The same rail `show_tab` uses: a flag the card has consumed cannot fire again, and «ponme el
    tercero» right after «ponme el sexto» is an order he is entitled to give twice."""
    yt.apply_action("play_result", {"item": 6})
    first = _goto(store.load(yt.WID))["seq"]
    yt.apply_action("play_result", {"item": 3})
    assert _goto(store.load(yt.WID))["seq"] > first


def test_the_END_of_a_video_does_NOT_move_his_view(sandbox):
    """The mirror, and the reason this is declared where the ORDER is known: he reads the queue while
    one plays, and yanking the view on a track change is the same defect with the sign flipped."""
    store.save(yt.WID, {"videoId": "AAAAAAAAAA1", "pos": 0, "goto_tab": {"tab": "cola", "seq": 4},
                        "list": [{"videoId": "AAAAAAAAAA1", "title": "uno"},
                                 {"videoId": "BBBBBBBBBB2", "title": "dos"}]})
    r = yt.apply_action("ended", {})
    assert r["ok"] and (store.load(yt.WID) or {}).get("videoId") == "BBBBBBBBBB2", "it DID advance"
    assert _goto(store.load(yt.WID)) == {"tab": "cola", "seq": 4}, "and his face stayed where he put it"


def test_an_explicit_next_IS_an_order_and_shows_the_player(sandbox):
    """«siguiente» measured 0.97 as a screen action: he is asking to watch the next one."""
    store.save(yt.WID, {"videoId": "AAAAAAAAAA1", "pos": 0, "goto_tab": {"tab": "cola", "seq": 4},
                        "list": [{"videoId": "AAAAAAAAAA1", "title": "uno"},
                                 {"videoId": "BBBBBBBBBB2", "title": "dos"}]})
    yt.apply_action("next", {})
    assert _goto(store.load(yt.WID))["tab"] == "player"


def test_show_tab_still_writes_the_face_he_named(watching_from_the_catalog):
    """V2-742/V2-754's path, bit for bit — the helper is shared, not a second way to navigate."""
    assert yt.apply_action("show_tab", {"tab": "home"})["tab"] == "inicio", "the alias still resolves"
    assert _goto(store.load(yt.WID))["tab"] == "inicio"


def test_the_card_refuses_a_STALE_order_to_show_an_empty_player():
    """`goto_tab` is stored and `_gotoSeq` is module-lived, so a reload replays the last order. With
    the video gone that would park him on a blank Reproductor — the dead end V2-753 spent an
    initiative getting him out of. Source-pinned: the render half is node 4.x (it RENDERS)."""
    body = _CARD.read_text(encoding="utf-8")
    assert 'const stale = _goto.tab === "player" && !hasVid;' in body
    assert "root._hbYtSelectTab && !stale" in body


# ── 3 · THE HARNESS DOES NOT ASSERT WHAT IT HAS NOT VERIFIED ──────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_goals():
    harness.reset()
    yield
    harness.reset()


def test_an_unverified_goal_says_NOTHING_in_the_prompt():
    """The measured defect: three minutes of «la hoja `youtube` sigue VACÍA» over a card holding six
    results and a playing video, because nothing ever verified it and the prompt did not care."""
    harness.note_goal(harness.KIND_WIDGET_CONTENT, "youtube", "Vale, muéstrame el widget de vídeo.")
    assert harness.prompt_lines() == [], (
        "the module's own rule: a widget whose truth cannot be read yields None and the harness stays "
        "SILENT — a wrong «you did not deliver» over a delivered card is worse than none")


def test_a_goal_a_verifier_found_UNMET_still_speaks(monkeypatch):
    """V2-660's protection is untouched: an empty sheet is still a fact with its rule in the prompt."""
    g = harness.note_goal(harness.KIND_WIDGET_CONTENT, "documento", "Tráeme la Declaración.")
    monkeypatch.setattr(harness, "_widget_view", _async({"empty": True}))
    assert asyncio.run(harness.verify(g)) is False
    lines = harness.prompt_lines()
    assert len(lines) == 1 and "sigue VACÍA" in lines[0] and "documento" in lines[0]


def test_a_goal_that_was_MET_closes_and_stops_speaking(monkeypatch):
    g = harness.note_goal(harness.KIND_WIDGET_CONTENT, "documento", "Tráeme la Declaración.")
    monkeypatch.setattr(harness, "_widget_view", _async({"empty": False}))
    monkeypatch.setattr(harness, "_card_is_open", lambda _w: True)
    assert asyncio.run(harness.sweep()) == [g]
    assert harness.prompt_lines() == [] and g["status"] == "met"


def test_an_unreadable_card_is_reported_once_so_the_silence_is_not_invisible(monkeypatch):
    """A guard that stays quiet is how this one spent a whole session being blamed on the model."""
    seen: list[str] = []
    monkeypatch.setattr(harness, "_widget_view", _async(None))
    monkeypatch.setattr(harness, "_emit", lambda label, g, extra=None: seen.append(label))
    g = harness.note_goal(harness.KIND_WIDGET_CONTENT, "musica", "Pon algo.")
    assert asyncio.run(harness.verify(g)) is None
    assert asyncio.run(harness.verify(g)) is None
    assert [s for s in seen if "NO verificable" in s], "the unreadable card leaves a line"
    assert len([s for s in seen if "NO verificable" in s]) == 1, "…once, not on every heartbeat"


def test_the_video_card_now_ANSWERS_whether_it_holds_anything(watching_from_the_catalog):
    """The other half: the goal could never be met because the card never declared emptiness."""
    assert yt.view_data().get("empty") is False, "six numbered results are not an empty sheet"
    store.save(yt.WID, {"videoId": "", "search_results": [], "list": []})
    assert yt.view_data().get("empty") is True


def _async(value):
    async def _f(_wid):
        return value
    return _f
