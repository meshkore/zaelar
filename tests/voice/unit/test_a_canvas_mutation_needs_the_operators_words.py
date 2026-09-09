"""V2-635 — a canvas mutation needs the operator's words, and a known order survives the wake word.

One live session (34386d8f, 2026-09-09) measured four failure classes, every one the model dragging its
PREVIOUS tool call into a turn whose words licensed nothing of the kind:
  · «Johnny pausa el vídeo» → fullscreen (the verbatim «pausa el video» seed missed because the phrase
    carried the agent's name, so the turn fell to the model — which repeated its last tool);
  · «minimiza el vídeo» → fullscreen, twice (the toggle was the only route, and on a non-maximized card
    the toggle does the exact opposite);
  · «Johnny eres tonto» and «¿Y por qué lo has quitado?» → closes nobody asked for (the first emptied the
    loaded video, so «Continúa el vídeo» died with «No hay ningún vídeo cargado»);
  · «Muy bien, señora.» and «¿Pero por qué lo has cambiado otra vez?» → play_video reloads of the video
    that was already playing.

The remedy is GRAMMAR, never intent (V2-095), the stop_worker GUARD 2 posture: what removes or replaces
things on the operator's screen requires the operator to have said so in the very turn that fires it.
"""
from __future__ import annotations

import json
import pathlib

from nucleo.flash import canvas_license as lic

ENGINE = pathlib.Path(__file__).resolve().parents[3]


# ── 1 · the license grammar, against the session's own sentences ─────────────────────────────────────────

def test_chatter_and_complaints_license_no_video():
    for t in ("Muy bien, señora.", "No, tonta.", "¿Pero por qué lo has cambiado otra vez?",
              "Vale, Johnny, cierra el vídeo.", "Johnny eres tonto.",
              "si quieres luego miramos otra cosa distinta ya veremos"):
        assert lic.video_license(t) is False, t


def test_a_real_request_licenses_the_load():
    for t in ("Johnny, pon otro vídeo de Ronaldinho.", "Pues carga el vídeo de Ronaldinho.",
              "busca vídeos de gatitos", "quiero ver un video de cocina", "otra canción",
              "play a ronaldinho video", "siguiente"):
        assert lic.video_license(t) is True, t


def test_a_short_bare_yes_answers_the_models_own_offer():
    """«Si quieres, busco de nuevo el vídeo» → «Sí» must keep working; a long conditional must not."""
    assert lic.video_license("Sí") is True
    assert lic.video_license("vale, hazlo") is True
    assert lic.video_license("si te soy sincero no me gusta mucho este canal la verdad") is False


def test_a_close_needs_a_close_verb_in_the_turn():
    assert lic.close_license("Vale, Johnny, cierra el vídeo.") is True
    assert lic.close_license("te he dicho que cierres el widget") is True
    for t in ("Johnny eres tonto.", "¿Y por qué lo has quitado?", "no cierres nada"):
        assert lic.close_license(t) is False, t


def test_fullscreen_calls_need_screen_size_words_and_shrink_routes_to_minimize():
    assert lic.fullscreen_license("Johnny pausa el vídeo.") == ""          # the measured drag
    assert lic.fullscreen_license("Callatilla, habéis bajado un número al pelo.") == ""
    for t in ("Johnny, minimiza el vídeo.", "quita la pantalla completa", "sal de pantalla completa",
              "hazlo más pequeño", "minimize the video"):
        assert lic.fullscreen_license(t) == "minimize", t
    for t in ("Pon el video a pantalla completa.", "hazlo más grande", "maximize the video"):
        assert lic.fullscreen_license(t) == "fullscreen", t


# ── 2 · the leading wake word comes off before the action-map lookup ─────────────────────────────────────

def test_the_vocative_wake_word_is_stripped_and_only_the_wake_word(monkeypatch):
    from voice import attention as att
    monkeypatch.setitem(att._state, "assistant_name", "Johnny")
    assert att.strip_leading_wakeword("Johnny pausa el vídeo.") == "pausa el video."
    assert att.strip_leading_wakeword("oye johnny, minimiza el vídeo") == "minimiza el video"
    assert att.strip_leading_wakeword("Zaelar, cierra el vídeo") == "cierra el video"
    # No wake word → nothing stripped; courtesy prefixes stay forbidden (normalize.py doctrine).
    assert att.strip_leading_wakeword("por favor pausa el vídeo") == ""
    assert att.strip_leading_wakeword("Johnny.") == ""            # the bare name is not an order


def test_match_spoken_retries_with_the_name_removed(monkeypatch):
    from nucleo import actionmap as amap
    from nucleo.actionmap import store as _store
    from voice import attention as att
    monkeypatch.setitem(att._state, "assistant_name", "Johnny")
    entry = {"id": 7, "action": {"do": "widget_data", "widget": "youtube", "action": "pause"},
             "source": "seed"}
    monkeypatch.setattr(_store, "index", lambda: {"pausa el video": entry})
    assert amap.match_spoken("pausa el vídeo") is not None
    hit = amap.match_spoken("Johnny pausa el vídeo.")
    assert hit is not None and hit["action"]["action"] == "pause", \
        "the leading vocative must not hide a verbatim-known order (measured: it fell to the model)"
    assert amap.match_spoken("Johnny eres tonto.") is None


def test_the_fast_lane_and_the_probe_mirror_both_use_match_spoken():
    lane = (ENGINE / "voice/engine/llm/providers/fast_lane.py").read_text(encoding="utf-8")
    probe = (ENGINE / "nucleo/flash/probe_actionmap.py").read_text(encoding="utf-8")
    assert "match_spoken(" in lane and "match_spoken(" in probe, \
        "both channels must retry the lookup with the wake word stripped (V2-539 parallel-impl rule)"


# ── 3 · the shared branch bodies act on the license ──────────────────────────────────────────────────────

def _emits():
    rows = []
    def emit(kind, label, **kw):
        rows.append((kind, label, kw))
    return rows, emit


def test_voice_execute_discards_an_unlicensed_load_and_counts_it_handled():
    from nucleo.flash import video_turn as vt
    rows, emit = _emits()
    applied = []
    deduped = {"v": False}
    vt.voice_execute({"query": "Ronaldinho"}, "Muy bien, señora.", emit,
                     lambda *a: applied.append(a), deduped)
    assert applied == [], "the drag reloaded the playing video live — it must not execute"
    assert deduped["v"] is True, "a discarded drag is handled, not a void for the mute backstop"
    assert any("play_video ignorado" in label for _, label, _kw in rows)


def test_voice_execute_runs_a_licensed_load_exactly_as_before():
    from nucleo.flash import video_turn as vt
    rows, emit = _emits()
    applied = []
    vt.voice_execute({"query": "Ronaldinho"}, "pon otro vídeo de Ronaldinho", emit,
                     lambda *a: applied.append(a), {"v": False})
    assert applied == [("youtube", "load", {"query": "Ronaldinho"})]
    assert ("widget", "show") in [(k, l) for k, l, _ in rows]


def test_fullscreen_dispatch_routes_by_direction_and_discards_the_drag(monkeypatch):
    from nucleo.flash import show_target as st
    monkeypatch.setattr(st, "fullscreen_target", lambda rid, text: "youtube")
    for text, want_tags in (
            ("Johnny pausa el vídeo.", []),                                  # drag → nothing
            ("minimiza el vídeo", [("minimize", {"id": "youtube"})]),        # shrink → canvas minimize
            ("pon el vídeo a pantalla completa",
             [("show", {"id": "youtube"}), ("fullscreen", {"id": "youtube"})])):
        rows, emit = _emits()
        tags = []
        deduped = {"v": False}
        st.fullscreen_dispatch({}, text, lambda a, e: tags.append((a, e)), emit, deduped)
        assert tags == want_tags, text
        if not want_tags:
            assert deduped["v"] is True


# ── 4 · the provider and the probe carry the guards (source contracts) ───────────────────────────────────

def test_the_voice_provider_gates_model_closes_and_delegates_the_bodies():
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert 'if action == "close" and not _closeg.looks_like_close(text):' in src, \
        "a model-emitted [[close]] with no close order in the turn is drag (the «eres tonto» close)"
    assert 'if action_name == "close" and not _router.looks_like_close(text):' in src, \
        "the widget_data close (which EMPTIES the loaded video) needs the same license"
    assert "_video_turn.voice_execute(" in src and "_show_target.fullscreen_dispatch(" in src, \
        "the branch bodies live in the shared modules — one impl, both channels"


def test_the_probe_channel_mirrors_all_three_guards():
    src = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "close_guards" in src and 'if action == "close":' in src, "probe must drop unlicensed closes"
    assert "video_license(text)" in src, "probe must gate play_video on the same license"
    assert "fullscreen_license(text)" in src, "probe must route the fullscreen direction the same way"


# ── 5 · minimize is a first-class canvas order ───────────────────────────────────────────────────────────

def test_the_executor_knows_minimize_and_emits_the_canvas_event():
    from nucleo.actionmap import executor
    assert executor.validate({"do": "minimize", "widget": "youtube"}) == ""
    rows, emit = _emits()
    assert executor.execute({"do": "minimize", "widget": "youtube"}, emit, phrase="minimiza el video")
    assert [(k, l) for k, l, _ in rows] == [("widget", "minimize")]
    assert rows[0][2]["extra"]["id"] == "youtube"


def test_the_frontend_routes_minimize_to_one_honest_step_down():
    sse = (ENGINE / "frontend/app/services/sse.js").read_text(encoding="utf-8")
    assert 'd.label === "minimize"' in sse and "desktop.shrink(" in sse
    desk = (ENGINE / "frontend/app/widgets/desktop.js").read_text(encoding="utf-8")
    assert "shrink(id){" in desk, "desktop.shrink: exit fullscreen → restore maximize → rail chip"
    body = desk.split("shrink(id){", 1)[1].split("\n  }", 1)[0]
    assert "exitFullscreen" in body and "this.maximize(id)" in body and "this.minimize(id)" in body


def test_the_seed_packs_carry_the_sessions_missing_phrases_in_both_languages():
    for lang, phrases in (("es", ("minimiza el video", "pon el video a pantalla completa",
                                  "cierra el video")),
                          ("en", ("minimize the video", "put the video in full screen",
                                  "close the video"))):
        pack = json.loads((ENGINE / f"nucleo/actionmap/seeds/{lang}.json").read_text(encoding="utf-8"))
        assert pack["version"] >= 6, "the packs must re-import on upgrade"
        have = {e.get("phrase"): (e.get("action") or {}).get("do") for e in pack["entries"]}
        assert have.get(phrases[0]) == "minimize", lang
        assert have.get(phrases[1]) == "fullscreen", lang
        assert have.get(phrases[2]) == "close_widget", lang
