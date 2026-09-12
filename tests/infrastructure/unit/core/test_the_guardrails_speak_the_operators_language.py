"""V2-677 · node 3.40 — the guardrails in the operator's language, and a system note is not an order.

Every case here is a sentence the operator actually said, or a sentence the engine actually produced, on
2026-09-11 in two English sessions (`e896f596` 23:16-23:20 and `366787ed` 23:23-23:26). His own reading was
«va mejor en castellano… no sé si hay algún problema idiomático en los prompts, los guardarraíles, las
reglas», and the measurements below say he was right about the mechanism as well as the symptom.

The unifying defect: every grammar guard in this codebase is bilingual by declaration and monolingual in
practice. The Spanish side is written with open suffixes and catches the whole conjugation; the English
side was a list of BARE STEMS, so it missed the forms an operator actually speaks.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from nucleo.flash import answer_guards as ag
from nucleo.flash import canvas_license as cl
from nucleo.flash import escalation_guard as eg
from nucleo.flash import router_catalog as rc


# ── A · The English half of the media grammar had no inflections ──────────────────────────────────────────
# Measured: «With playing the Neil Armstrong video.» was read as licensing nothing and the load was eaten as
# context-bleed. `🛡️ play_video ignorado — el turno no pide ningún vídeo` fired on it at 23:25:59, and the
# operator had by then asked for that video five times.
@pytest.mark.parametrize("said", [
    "With playing the Neil Armstrong video.",          # measured verbatim, vetoed
    "Go on with playing the Neil Armstrong video.",     # measured verbatim, vetoed
    "Start playing the video",
    "Keep playing that clip",
    "Can you show me a video of the first moonwalk?",   # measured, WORKED (the bare stem happens to match)
    "Play it for me.",                                  # measured, WORKED
])
def test_an_english_media_order_is_heard_in_every_form_the_operator_uses(said):
    assert cl.video_license(said), f"an English video order licensed nothing: {said!r}"


def test_the_spanish_side_is_untouched():
    """The conjugated Spanish forms V2-664 and V2-635 earned keep working — this batch only ADDED."""
    for said in ("me vas a poner el vídeo del Apolo 11", "ponme el vídeo", "¿puedes ponerme la canción?",
                 "reprodúceme el siguiente", "cámbialo, pon otro vídeo de Ronaldinho"):
        assert cl.video_license(said), said
    for chatter in ("Muy bien, señora.", "¿Pero por qué lo has cambiado otra vez?", "Johnny eres tonto"):
        assert not cl.video_license(chatter), chatter


# ── B · «get out of full screen» did the OPPOSITE of what it says ─────────────────────────────────────────
# `_EXIT_FS_RE` listed bare verbs; English leaves a mode with a PARTICLE. With no exit verb matched, the
# sentence fell through to `_GROW_RE` on its own «full screen» and TOGGLED the card INTO full screen.
@pytest.mark.parametrize("said,want", [
    ("get out of full screen", "minimize"),
    ("take it off full screen", "minimize"),
    ("come out of fullscreen please", "minimize"),
    # These two carry NO verb at all, so only the particle branch can catch them — without it they fall
    # through to _GROW_RE on their own «fullscreen» and TOGGLE the card INTO it.
    ("out of fullscreen, please", "minimize"),
    ("off fullscreen", "minimize"),
    # Found by a disarm of the English fix: the SAME inversion existed in Spanish. «sal» cannot reach
    # «sácame» across the word boundary, so this put the card INTO full screen.
    ("sácame de la pantalla completa", "minimize"),
    ("quita la pantalla completa del vídeo", "minimize"),      # the Spanish that always worked
    ("minimize it", "minimize"),
    ("make it smaller please", "minimize"),
    ("maximize the widget", "fullscreen"),                      # measured verbatim
    ("Can you maximize the screen of the image?", "fullscreen"),  # measured verbatim
    ("can you expand the image widget", "fullscreen"),
    ("make it bigger", "fullscreen"),
    ("Widget.", ""),                                            # a self-correction licenses nothing
    ("pausa el vídeo", ""),                                     # V2-635's measured drag, still ignored
])
def test_a_screen_size_order_routes_where_it_points(said, want):
    assert cl.fullscreen_license(said) == want, said


# ── C · A replay is the one mutation that must hear the verb ──────────────────────────────────────────────
# Measured in 366787ed: «And show me show me the agenda. My agenda.» and «Yeah. Okay.» each re-licensed the
# youtube load that had just run, so the video reloaded itself over an order aimed at another card and over
# a backchannel. `show` is a generic verb and the bare affirmative is not an order at all.
def test_an_order_aimed_at_another_widget_never_replays_this_one():
    assert not cl.replay_license("youtube", "load", "And show me show me the agenda. My agenda.")


def test_a_backchannel_never_replays():
    assert not cl.replay_license("youtube", "load", "Yeah. Okay.")


def test_the_explicit_replay_order_v2_650_exists_for_still_passes(monkeypatch):
    """«dale al play» is the measured order V2-650 built this escape hatch for. It must survive."""
    from widgets import producers
    monkeypatch.setattr(producers, "starts_production", lambda w, a: True)
    assert cl.replay_license("musica", "play_playlist", "Vale, pues reproduce la lista")
    assert cl.replay_license("musica", "play_playlist", "Vamos, dale al play")


# ── D · A SYSTEM NOTE IS NOT AN ORDER — the kickoff that spawned a worker ─────────────────────────────────
# The single most expensive finding of the session. At 23:16:36 `looks_like_modify_widget` fired on the
# FIRST TURN's composed prompt and escalated the greeting to a real `claude_code` worker, which ran for
# fifty seconds and came back with a Spanish greeting into an English conversation.
#
# The three words that satisfied the guard were ALL OURS: «añade» from «añade en una frase lo que sigue»,
# «fondo» from «La tarea de fondo…», and «panel» from «Lo tienes en el panel de estado».
_KICKOFF = ("Es el primer turno. Salúdame en 1-2 frases, cálido y breve; si por tu MEMORIA ya sabes mi "
            "nombre, úsalo y NO preguntes quién soy; si no, preséntate en una línea y pregúntame el "
            "nombre. Luego para.")
_MEASURED_TURN = _KICKOFF + (
    "\n\n[SISTEMA] Avisos pendientes — SOLO cuando hayas atendido y contestado lo que te ha pedido "
    "arriba, y después de eso, añade en una frase lo que sigue; nunca abras con ello ni le hagas esperar "
    "su respuesta:\n"
    "[SISTEMA] Brain worker · Tarea sin completar: Esa tarea no ha podido completarse por un fallo del "
    "proveedor. Lo tienes en el panel de estado.\n"
    "[SISTEMA] La tarea de fondo «Create a chart/graph showing the evolution of Bitcoin's price over the» "
    "ha MUERTO sin resultado y no se va a reintentar sola.")


def test_our_own_system_notes_can_never_become_an_errand():
    assert eg.escalation_text(_KICKOFF, _MEASURED_TURN) == "", (
        "a `[SISTEMA]` note satisfied the guard and spawned a real worker off a greeting")


def test_the_guard_still_fires_on_what_the_operator_actually_says():
    """The counterweight: V2-057's two real failure modes must keep escalating."""
    assert eg.escalation_text("cámbiale el color de fondo al widget de la agenda", "")
    assert eg.escalation_text("búscame una moto de segunda mano en Wallapop", "")


def test_both_channels_call_the_same_function_and_neither_reads_the_composed_turn():
    """V2-252: this decision existed twice. A copy is how the two halves drift apart."""
    for path in ("voice/engine/llm/providers/nucleo.py", "nucleo/flash/probe.py"):
        src = open(path, encoding="utf-8").read()
        assert "escalation_guard" in src, f"{path} stopped going through the shared guard"
        assert "looks_like_modify_widget(text)" not in src, (
            f"{path} reads the composed turn again — that is the kickoff bug")


# ── E · The model denied three capabilities it HAS, and had just used ─────────────────────────────────────
# «dice que no tiene capacidades el widget de vídeo, así como tampoco tienen capacidades los widgets de
# maximizarse o hacer un resize». All three sentences were false when said: every card on the canvas has
# carried ⤢, eight drag-resize handles and a rail chip since V2-537/V2-608, and the tools were in the
# turn's own list. A denial is indistinguishable from an absence, which is why it costs so much.
@pytest.mark.parametrize("said", [
    # the three measured verbatim, in order
    "I can't display images or graphs, but I can describe the trend for you if that helps.",
    "I don't have a way to actually select or display images from my side right now—I can only describe "
    "what I see. If you can open the image on your end, I'll help you identify which of the six is the "
    "graph you need.",
    "I can't resize or maximize windows or widgets on your screen directly—I don't have control over your "
    "device's interface. You'd need to click the maximize button on the image widget yourself.",
    "No puedo mostrar imágenes, pero te cuento lo que dicen.",
    "No tengo forma de maximizar el widget desde aquí.",
    "I cannot select pictures myself.",
])
def test_a_denial_of_the_canvas_is_caught(said):
    assert ag.a_reply_denies_the_screen(said), said


@pytest.mark.parametrize("said", [
    # An honest report about ONE attempt is exactly what we want said instead, and must survive.
    "No he podido abrir esa imagen, el enlace está roto.",
    "Esa foto no carga; pruebo con otra.",
    "La búsqueda no ha traído ningún gráfico esta vez.",
    # Asking WHICH one is the correct answer to an ambiguous select, not a denial.
    "Dime cuál de las seis quieres y te la pongo a pantalla completa.",
    "Which one is the chart? Tell me the number and I'll show it.",
    # The operator's own machine, outside the app, IS a real limit — we drive OUR canvas, not his desktop.
    # These three DO reach the denial pattern and are exempted by naming his machine; without that
    # exemption the agent would be corrected for telling the truth.
    "No puedo mover la ventana de tu ordenador.",
    "I can't resize the window on your computer.",
    "No puedo minimizar la ventana de tu sistema operativo.",
    "No puedo cerrar tu navegador, eso está fuera de la aplicación.",
    "I can't close your desktop apps, but I can close any widget in here.",
    # And a plain success.
    "He maximizado el widget de imágenes.",
])
def test_an_honest_sentence_is_never_mistaken_for_a_denial(said):
    assert not ag.a_reply_denies_the_screen(said), said


def test_the_repair_speaks_and_it_comes_from_the_language_table():
    """What has to be said is a FACT about this system, so it is never re-composed by a model."""
    from nucleo.flash import second_pass as sp
    from i18n import langs

    spec = langs.spec("en")
    bad = ("I can't resize or maximize windows or widgets on your screen directly—I don't have control "
           "over your device's interface.")
    out = asyncio.run(sp.probe_hollow_repairs("maximize the widget", bad, [], spec))
    assert out != bad and spec.screen_denied_repair in out
    # It offers the one thing that WAS actually missing: which card.
    assert "which one" in spec.screen_denied_repair.lower()
    # And it leaves a healthy turn alone.
    ok = "I've maximized the images widget."
    assert asyncio.run(sp.probe_hollow_repairs("maximize it", ok, [], spec)) == ok


def test_the_voice_channel_repairs_it_too():
    """V2-252 again: the seam is shared, so the branch has to live in it and not in one caller."""
    src = open("nucleo/flash/second_pass.py", encoding="utf-8").read()
    assert src.count("a_reply_denies_the_screen") == 2, (
        "both `hollow_repairs` (voice) and `probe_hollow_repairs` (text) must carry the branch")


def test_the_prompt_AFFIRMS_the_capability_and_names_the_forbidden_sentence():
    """V2-221: without the sentence in the prompt the model has nothing to check itself against."""
    from nucleo.flash import canvas_claim
    block = canvas_claim.SCREEN_BLOCK
    assert "PROHIBIDO" in block, "the forbidden claim has to be named, not merely contradicted"
    for verb in ("mostrar", "seleccionar", "maximizar", "redimensionar"):
        assert verb in block, verb
    # V2-640's LIMIT travels with it — the two halves are one paragraph on purpose.
    assert "nunca sigas como si existiera" in block
    from nucleo.flash import prompt as _p
    import inspect
    assert "_canvas_claim.SCREEN_BLOCK" in inspect.getsource(_p)


# ── F · Everything the operator HEARS is in his language, including the auditor and the workers ───────────
def test_the_internal_auditor_writes_its_repair_in_the_operators_language():
    """`repair_say` is SPOKEN VERBATIM, so the auditor is a mouth. Measured: it produced «Perdona el
    cruce, Richard: me lié con el vídeo» and the reply ended «Perdona el fallo de antes, ahora lo pongo.»
    into an English conversation. He asked, in the next breath, why it kept speaking Spanish."""
    from nucleo.susurro import catalog
    import i18n.langs as L

    prompt_en = _with_language("en", catalog.system_prompt)
    assert "English" in prompt_en
    assert "en castellano" not in catalog.SYSTEM.split("\n")[0], (
        "the catalog itself must not pin the auditor to one language")
    # V2-452's lesson: naming the target is not enough — the window is full of OUR Spanish.
    assert "NUNCA copies esa lengua" in prompt_en
    prompt_es = _with_language("es", catalog.system_prompt)
    assert "Español" in prompt_es and "NUNCA copies esa lengua" not in prompt_es

    assert L  # the import is the point: the auditor reads the same table everything else does


def test_every_worker_prompt_carries_the_language_of_the_delivery():
    """The GENERIC worker prompt named the language NOWHERE, while every block in it is Spanish.
    Measured: a worker's delivery came back «¡Hola, Richard! Qué gusto tenerte aquí» in English session."""
    from nucleo import dispatch_prompts as dp

    block_en = _with_language("en", dp.worker_language_block)
    assert "English" in block_en and "A PROPÓSITO" in block_en
    block_es = _with_language("es", dp.worker_language_block)
    assert "Español" in block_es and "A PROPÓSITO" not in block_es, (
        "a Spanish operator must not be told his own instructions are in the wrong language")
    generic = _with_language("en", lambda: dp._build_prompt("do a thing", "", True))
    assert "IDIOMA DE LA ENTREGA" in generic


def _with_language(code, fn):
    """Call `fn` with the active language forced — the table reads it from the environment."""
    import os
    import i18n.langs as L
    old = os.environ.get("ZAELAR_LANGUAGE")
    os.environ["ZAELAR_LANGUAGE"] = code
    try:
        L.lock(code) if hasattr(L, "lock") else None
        return fn()
    finally:
        if old is None:
            os.environ.pop("ZAELAR_LANGUAGE", None)
        else:
            os.environ["ZAELAR_LANGUAGE"] = old
        if hasattr(L, "lock") and old:
            L.lock(old)


# ── G · The canvas verbs are reachable in English, and the catalog stays under its ceiling ────────────────
def test_arranging_the_canvas_can_be_asked_for_in_english():
    """«Can you reposition all the boxes in the screen, all the widgets?» reached no tool at all, and the
    reply narrated a video instead. The description had no English word in it."""
    desc = next(t["function"]["description"] for t in rc.TOOLS
                if t["function"]["name"] == "arrange_canvas")
    for word in ("tidy", "arrange", "reposition"):
        assert word in desc.lower(), word
    assert "ORDENA" in desc, "the Spanish it always had must stay"


def test_the_shared_catalog_ceiling_is_paid_by_compressing_never_by_raising():
    """This catalog is paid on EVERY voice turn (INI-027), so English coverage buys its own room."""
    assert len(json.dumps(rc.TOOLS, ensure_ascii=False)) <= 23_100


# ── H · A generated widget is told about all THREE sizes and told the chrome is not its job ───────────────
def test_the_generator_teaches_three_sizes_and_the_host_contract():
    """The operator: «que por defecto les dé tres tamaños de pantalla que sean responsive y además que
    tengan estas funcionalidades para interactuar con el frontend, de maximizarse, minimizarse, etc.»
    The contract taught TWO (desk + phone); the third — maximized, filling the canvas — is the one he
    reached for, and the one a narrow-only layout strands a 400px column inside."""
    from widgets import generator
    c = generator._CONTRACT
    assert "THREE SIZES, ONE WIDGET" in c
    for token in ("PHONE", "DESK CARD", "MAXIMIZED", "auto-fit"):
        assert token in c, token
    # The chrome already exists for every widget; a widget drawing its own is a frame inside a frame.
    assert "CHROME IS THE HOST'S, NEVER YOURS" in c
    for control in ("close", "maximize", "minimize", "resize"):
        assert control in c
    guide = open("widgets/AGENTS.md", encoding="utf-8").read()
    assert "THREE SIZES, ONE WIDGET" in guide, "the guide and the injected contract must agree"


def test_the_host_really_does_give_every_card_those_controls():
    """The claim above is only honest if the desktop actually builds them for EVERY widget, unconditionally
    — which is what makes «I can't resize or maximize widgets» a false sentence rather than a limitation."""
    src = open("frontend/app/widgets/desktop.js", encoding="utf-8").read()
    i = src.index("const card=document.createElement(\"div\"); card.className=\"hb-win loading\"")
    fresh = src[i:i + 4000]
    for piece in ('className="hb-x"', 'className="hb-max"', "_addHandles(card)",
                  "_wireDrag(card)", "_wireResize(card"):
        assert piece in fresh, f"a fresh card stopped getting {piece}"


# ── I · Picking one of six pictures, in either language ───────────────────────────────────────────────────
# «Why don't you just show me the one with the graph?» → `select` answered «dime cuál: un número o parte del
# título» over six NEWS HEADLINES, none of which could match anything he might say. A bare digit resolved
# and every ordinal resolved to NOTHING — in both languages — which is the most natural way a person picks
# from a numbered row and the one way that failed.
_SHOT = [{"title": "Bitcoin (BTC) on Verge of Worst Month", "site": "cnews24.ru"},
         {"title": "Bitcoin declines following $1 trillion", "site": "x.com"},
         {"title": "CZ Sees Faster Bitcoin Price Recovery", "site": "coindesk.com"},
         {"title": "Bitcoin Price Chart USD", "site": "tradingview.com"}]


@pytest.mark.parametrize("said,want", [
    ("1", 0), ("3\u00ba", 2),                                   # what already worked
    ("the first one", 0), ("la primera", 0),
    ("el tercero", 2), ("the third", 2),
    ("the last one", 3), ("la \u00faltima", 3), ("el cuarto", 3),
])
def test_a_picture_is_picked_by_its_position_in_either_language(said, want):
    from widgets.imagenes import data as imgdata
    assert imgdata._resolve(_SHOT, said) == want, said


def test_picking_by_what_the_title_says_still_wins():
    """The counterweight: position is tried FIRST, but a real content word must still resolve."""
    from widgets.imagenes import data as imgdata
    assert imgdata._resolve(_SHOT, "chart") == 3
    assert imgdata._resolve(_SHOT, "Bitcoin declines") == 1
    assert imgdata._resolve(_SHOT, "something nobody said") is None


def test_position_is_resolved_from_the_one_table_that_holds_it():
    """A second ordinal table is how the two would come to disagree — so it is exported, not copied."""
    src = open("widgets/imagenes/data.py", encoding="utf-8").read()
    assert "refs.position_index" in src
    assert "primero" not in src, "the ordinals must not be re-listed here"


# ── J · A SYSTEM NOTE never licenses what touches his screen (V2-678) ─────────────────────────────────────
# The third door of this class in two days. Measured live 2026-09-12 (session 352268b5, 10:58:57): the
# widget action logged the words that licensed it as «Now show me\n\n[SISTEMA] Avisos pendientes — SOLO
# cuando hayas atendido y contestado…», so the grammar deciding what may touch his canvas, the context-bleed
# dedupe and the audit trail were all reading our own Spanish prose in an English session.
_NOTE = ("[SISTEMA] La tarea de fondo «Create a chart» ha MUERTO sin resultado. Díselo con tus palabras y "
         "ofrécele una salida concreta — reintentarlo, ponerle otro vídeo o dejarlo.")


def _composed(said):
    from voice import brain_notes
    return brain_notes.compose_turn(said, [_NOTE])


def test_a_note_that_talks_about_a_video_licenses_no_video():
    assert not cl.video_license(_composed("What time is it?")), (
        "our own note licensed a media mutation on his screen")


def test_a_note_that_talks_about_closing_licenses_no_close():
    from voice import brain_notes
    note = "[SISTEMA] El worker ha terminado; puedes cerrar la tarjeta cuando quieras."
    assert not cl.close_license(brain_notes.compose_turn("¿qué hora es?", [note]))


def test_his_own_order_still_licenses_through_the_notes():
    """The counterweight: stripping the notes must not strip him."""
    assert cl.video_license(_composed("play the Beatles"))
    assert cl.close_license(_composed("cierra el widget de música"))
    assert cl.fullscreen_license(_composed("maximize the widget")) == "fullscreen"


def test_the_operator_half_is_recovered_from_one_place():
    from voice import brain_notes
    assert brain_notes.operator_half(_composed("Now show me")) == "Now show me"
    # A turn with no notes is already his words — fail-open, today's behaviour exactly.
    assert brain_notes.operator_half("Play the Beatles") == "Play the Beatles"


@pytest.mark.parametrize("said", [
    "Now show me the music widget.",                            # measured 10:59:00, reloaded the video
    "I said, show me the music widget, not the video widget.",   # measured 10:59:15, reloaded it AGAIN
    "Yeah. Okay.",
])
def test_an_order_about_another_card_never_replays_this_one(said, monkeypatch):
    from widgets import producers
    monkeypatch.setattr(producers, "starts_production", lambda w, a: True)
    assert not cl.replay_license("youtube", "load", _composed(said)), said


def test_an_explicit_replay_order_still_passes(monkeypatch):
    from widgets import producers
    monkeypatch.setattr(producers, "starts_production", lambda w, a: True)
    assert cl.replay_license("musica", "play_playlist", _composed("dale al play"))


# ── K · The close-ALL door finally gets a grammar (V2-678) ────────────────────────────────────────────────
# The most destructive thing the operator can trigger by accident: it bypasses the attention gate, executes
# immediately, and there is no undo. It was also the ONLY close door with no grammar behind it.
# Measured live 2026-09-12 (session 352268b5), twice in six seconds — both wiped his canvas.
@pytest.mark.parametrize("said", [
    "Close also the agenda. And reposition all the widgets.",   # 10:59:45, verbatim
    "I said reposition widgets. Do not close the widgets.",     # 10:59:51, verbatim
    "Do not close the widgets.",
    "Don't close the widgets, just move them",
    "reposition all the widgets",
    "cierra el widget de música",                               # ONE named card is not a close-all
    "no cierres los widgets",
    "sal de pantalla completa",                                 # V2-600 stays
])
def test_these_never_wipe_the_canvas(said):
    import voice.attention as attention
    assert attention.hard_interrupt(said) != "close", said


@pytest.mark.parametrize("said", [
    "close everything", "close all the widgets", "cierra todos los widgets",
    "quita todas las tarjetas", "ciérralo todo", "limpia el escritorio",
])
def test_a_real_close_all_still_fires(said):
    """The counterweight — the guard errs toward not firing, it must not stop firing."""
    import voice.attention as attention
    assert attention.hard_interrupt(said) == "close", said


def test_the_negation_guard_hears_english_written_out():
    """V2-631 built the veto with the CONTRACTION alone, so «Do not close» read as an order. Same bare-stem
    asymmetry V2-677 found in the request verbs — here in the guard that exists to prevent damage."""
    from nucleo.flash.close_guards import looks_like_close
    for negated in ("Do not close the widgets.", "Don't close the widgets", "Never close the music widget",
                    "please do not close them", "no cierres el widget", "no me quites la música"):
        assert not looks_like_close(negated), negated
    for real in ("Close also the agenda.", "close everything", "cierra el widget de música",
                 "hide the agenda"):
        assert looks_like_close(real), real


def test_the_client_lane_carries_the_same_rule():
    """V2-252/V2-555: this decision genuinely exists twice, and the client half executes with no server."""
    src = open("frontend/app/services/voiceCommands.js", encoding="utf-8").read()
    # Anchor on the CALL SITE, never on the name — `closesTheWholeCanvas(n)` also matches the function's own
    # definition, so a disarm that reverted the call stayed green (the V2-571 lesson, paid again here).
    assert "if (closesTheWholeCanvas(n)) {" in src, (
        "the close-all lane still asks its two questions of the whole turn")
    assert "ALL_RE.test(n) || quantifiesTheCanvas(n)" not in src, (
        "the whole-turn test is back in the close-all branch")
    assert "NO_CLOSE_RE" in src, "the client lane had no negation check at all"
    assert "CLAUSE_SPLIT_RE" in src
