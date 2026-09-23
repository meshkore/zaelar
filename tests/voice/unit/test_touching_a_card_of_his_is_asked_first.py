"""V2-757 — a card of his is not built, rewritten, mounted or moved by a turn he did not aim at us.

LIVE SESSION `f84f91ef` (2026-09-23), on the V2-756 build. Six and a half minutes, and the last ninety
seconds are the operator watching the engine do things nobody asked it for:

    +219…+280  a design brief dictated to ANOTHER conversation, with the mic open — «hace el header ese
               más bonito», «todos los gráficos a la misma escala», «un grid de veinte puntos»
    +240.9     🧭 comisión → delegated · «Modificar el widget `youtube` del operador…»
    +284.6     «todo eso que me pides es un cambio de verdad en el widget, así que lo mando hacer»
    +297.0     «Olvídate de eso, no va por ti.»   → el worker siguió: «lleva 59s», «lleva 1 min»
    +306.6     `act show --help` → una tarjeta ROTA llamada «--help» montada en su canvas
    +348.2     «Hay un widget ahí que pone help… ha aparecido en pantalla ahora. Ciérralo inmediatamente»
    +366.3     «Lo de modificar el widget de YouTube ha sido un error, y no estaba hablando contigo.»

HIS RULE, from the same session: «hay que pedir confirmación siempre que pidamos crear un widget o
modificar un widget… que sea algo de sistema, porque así nos evitaremos que se empiecen a generar
widgets por ahí fuera de cualquier manera».

And the other four the same session measured, each one its own section below.
"""
from __future__ import annotations

import inspect
import os

import pytest


# ── A · TOCAR UN WIDGET SE PREGUNTA ANTES (la norma del operador) ──────────────────────────────────────
from nucleo import dispatch, errand_kind

#: The commission the engine actually wrote and dispatched, verbatim from the session log.
THE_REAL_COMMISSION = (
    "Modificar el widget `youtube` del operador (Paco) en dos cosas concretas: (1) rediseñar el "
    "HEADER/encabezado de la tarjeta para que quede más bonito y limpio")


class _Task:
    def __init__(self, kind="code", trusted=True, context=None):
        self.kind, self.trusted, self.context = kind, trusted, dict(context or {})


@pytest.fixture(autouse=True)
def _clean():
    dispatch._PENDING_CONFIRM.clear()
    dispatch._EXPIRED_CONFIRM.clear()
    yield
    dispatch._PENDING_CONFIRM.clear()
    dispatch._EXPIRED_CONFIRM.clear()


def _es(fn):
    """Pin the language: these sentences come from the table and the table answers in HIS language."""
    prev = os.environ.get("ZAELAR_LANGUAGE")
    os.environ["ZAELAR_LANGUAGE"] = "es"
    try:
        return fn()
    finally:
        os.environ.pop("ZAELAR_LANGUAGE", None) if prev is None else os.environ.__setitem__(
            "ZAELAR_LANGUAGE", prev)


def test_the_commission_that_ran_is_the_one_the_gate_catches():
    """Not a synthetic phrase: the exact text the engine handed the Brain Worker that afternoon."""
    assert errand_kind.classify_kind(THE_REAL_COMMISSION) == "code"
    assert errand_kind.code_change(THE_REAL_COMMISSION) == "modify"


def test_building_and_changing_are_told_apart():
    assert errand_kind.code_change("móntame un widget de ajedrez") == "create"
    assert errand_kind.code_change("modifica el widget de vídeo, ponle otra columna") == "modify"


def test_an_errand_that_is_not_about_a_card_is_not_gated():
    """The gate must not become a toll on everything: only the generator goes through it."""
    for req in ("búscame vuelos a Roma para el jueves",
                "rellena el widget de informes con los resultados",
                "enséñame la agenda de mañana"):
        assert errand_kind.classify_kind(req) != "code", req
        assert errand_kind.code_change(req) == "", req


def test_the_question_names_what_it_is_about_to_do_and_asks():
    q = _es(lambda: errand_kind.code_change_question(THE_REAL_COMMISSION))
    assert "MODIFIQUE" in q and "?" in q
    assert "irreversible" not in q.lower(), "not dangerous — expensive and visible, which is another question"
    q2 = _es(lambda: errand_kind.code_change_question("móntame un widget de ajedrez"))
    assert "CONSTRUYA" in q2 and "?" in q2


def test_the_question_survives_the_translation():
    """V2-682's rule: a gate that stops the product has to explain itself in HIS language. Default: English."""
    q = errand_kind.code_change_question("redesign the youtube widget header")
    assert "CHANGE one of your cards" in q and "Shall I?" in q
    assert "BUILD you a new card" in errand_kind.code_change_question("build me a chess widget")


def test_the_gate_lives_where_EVERY_door_into_the_generator_passes():
    """The wiring guard, and the reason the gate is not in the voice provider.

    The generator is reached from six places — the voice turn, the text channel, the probe, V2-118's
    create-widget backstop, the promise backstop, and a turn promoted from an injection. `_run_session`
    is the only door that actually starts a worker, and `kind` is already classified by the time it
    runs. Every assertion in this section passes with the gate deleted; this one does not."""
    src = "\n".join(l for l in inspect.getsource(dispatch._run_session).splitlines()
                    if not l.strip().startswith("#"))
    assert 'kind == "code"' in src and "remember_code_change(key, req, task, sheet=" in src
    # …and the exemption is read from THIS gate's own condition, not from anywhere else in the method:
    # `_dev_worker_params` is also called further down to build the worker spec, and an anchor on the
    # whole source was satisfied by that one with the exemption deleted (measured while disarming).
    cond = src[src.index('if (kind == "code"'):src.index("remember_code_change")]
    assert "_dev_worker_params(task.context)" in cond, (
        "the cluster dev-worker brings its own repo and its own authorisation — it is not his catalogue")
    # …and it stands BEFORE anything is launched, like the irreversible gate it sits next to.
    assert src.index("remember_code_change") < src.index("WorkerSpec(")


def test_the_parked_errand_keeps_its_question_and_its_context():
    dispatch.remember_code_change("7", THE_REAL_COMMISSION, _Task(context={"src": "voice"}))
    p = dispatch.pending_confirm()
    assert p and p["task_id"] == "7"
    assert p["code_change"] == "modify"
    assert p["question"] == errand_kind.code_change_question(THE_REAL_COMMISSION)
    assert p["context"]["src"] == "voice"


def test_the_brain_is_told_NOTHING_has_been_touched():
    """«Muy bien… entonces lo dejo estar y sigo con los ajustes del widget» — said while a worker it could
    not see was rewriting his card. The live state is what stops the turn narrating that."""
    dispatch.remember_code_change("7", THE_REAL_COMMISSION, _Task())
    line = dispatch.confirm_line()
    assert "MODIFICAR una tarjeta suya" in line
    assert "NI UNA LÍNEA" in line and "no digas que estás con ello" in line
    assert "IRREVERSIBLE" not in line, "that is the other gate, and it frightens him for nothing"


def test_a_yes_relaunches_the_SAME_errand_through_the_SAME_door(monkeypatch):
    sent: list = []
    from nucleo.flash import escalate as esc
    monkeypatch.setattr(esc, "escalate_to_slowbrain",
                        lambda req, context=None: sent.append((req, dict(context or {}))) or 1)
    dispatch.remember_code_change("7", THE_REAL_COMMISSION, _Task(context={"src": "voice"}))
    out = dispatch.resolve_confirm(True)
    assert out["ok"] is True and len(sent) == 1
    req, ctx = sent[0]
    assert req == THE_REAL_COMMISSION
    assert ctx["confirmed"] is True        # …which is what lets it past the gate the second time
    assert ctx["src"] == "voice"


def test_HIS_OWN_RETRACTION_drops_it(monkeypatch):
    """«Olvídate de eso, no va por ti.» — said at +297.0 and heard, and the worker kept going anyway.

    Parked instead of launched, the same words are simply the answer to the question."""
    sent: list = []
    from nucleo.flash import escalate as esc
    monkeypatch.setattr(esc, "escalate_to_slowbrain", lambda req, context=None: sent.append(req) or 1)
    from widgets import confirm as _wc
    dispatch.remember_code_change("7", THE_REAL_COMMISSION, _Task())
    assert _wc.classify_reply("Olvídate de eso, no va por ti.") == "no"
    assert _wc.classify_reply("no estaba hablando contigo") == "no"
    assert dispatch.resolve_confirm(False)["ok"] is False
    assert sent == [] and dispatch.pending_confirm() is None


def test_a_silence_expires_into_never_started_not_into_a_new_card():
    import time
    dispatch.remember_code_change("7", THE_REAL_COMMISSION, _Task())
    dispatch._PENDING_CONFIRM["7"]["ts"] = time.time() - dispatch._CONFIRM_TTL - 1
    assert dispatch.pending_confirm() is None
    assert dispatch.resolve_confirm(True) is None          # a late «sí» builds nothing
    assert "CADUCÓ" in dispatch.confirm_line()


# ── B · UN ID QUE NO EXISTE NO SE MONTA ────────────────────────────────────────────────────────────────
# +306.6: `act show --help`. argparse took `show` as the action and `--help` as the payload, this handler
# emitted `widget/show` with id «--help», the canvas mounted an instance, the browser failed to import
# `/widgets/--help/widget.js` (a client error, invisible) and a broken card stayed on his screen. The call
# had answered `OK: {"widget": "--help"}`.

def test_show_widget_refuses_an_id_that_is_not_in_the_catalogue():
    from widgets import runtime as rt
    ids = sorted(str(w.get("id") or "") for w in rt.catalog() if w.get("id"))
    assert "youtube" in ids and "--help" not in ids
    src = inspect.getsource(__import__("nucleo.worker_api", fromlist=["x"]))
    body = src[src.index('if action in ("show_widget", "close_widget")'):]
    body = body[:body.index('if action == "widget_data"')]
    assert 'if action == "show_widget":' in body, "CLOSE is not validated: closing what is not there is harmless"
    assert "_rt.catalog()" in body and "exists — the ones there are" in body
    assert 'split("::", 1)[0]' in body, "a live INSTANCE (`results::abc-1`) is not in the catalogue"


def test_the_refusal_hands_the_worker_the_list_it_needed():
    """A worker that gets an id wrong needs the catalogue, not a «no»."""
    src = inspect.getsource(__import__("nucleo.worker_api", fromlist=["x"]))
    assert '", ".join(_ids)' in src


# ── C · UNA BÚSQUEDA QUE NO SE VE NO ES UNA RESPUESTA ──────────────────────────────────────────────────
# +52: with Ronaldinho playing, «búscame vídeos del alunizaje». Six numbered results landed on the
# dashboard and the card stayed on the PLAYER. «Ya, pero yo no veo el catálogo, solo veo el vídeo de
# Ronaldinho.» Three turns of friction followed.

@pytest.fixture
def yt(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    import widgets.youtube.data as _yt
    return _yt


def _seed_band(yt, monkeypatch, query="ronaldinho"):
    monkeypatch.setattr(yt, "_search_many", lambda q, n=5: [
        {"videoId": f"v{i}", "title": f"{q} {i}", "channel": "c", "published": ""} for i in range(1, 7)])
    return yt.apply_action("search", {"query": query})


def test_a_search_brings_the_catalogue_to_the_FRONT(yt, monkeypatch):
    from widgets import store
    _seed_band(yt, monkeypatch, "alunizaje 1969")
    db = store.load(yt.WID, {})
    assert db.get("goto_tab", {}).get("tab") == "inicio", (
        "the results are on the card and he is looking at another face of that same card")


def test_the_same_search_answered_again_ALSO_shows_it(yt, monkeypatch):
    """V2-756 stopped re-running it. The reason he asks twice is almost always that he cannot see it."""
    from widgets import store
    _seed_band(yt, monkeypatch, "alunizaje 1969")
    db = store.load(yt.WID, {})
    db["goto_tab"] = {"tab": "player", "seq": 99}
    store.save(yt.WID, db)
    r = yt.apply_action("search", {"query": "alunizaje 1969"})
    assert r.get("unchanged") is True
    db = store.load(yt.WID, {})
    assert db["goto_tab"]["tab"] == "inicio" and db["goto_tab"]["seq"] == 100


def test_but_the_search_still_does_not_touch_what_is_SOUNDING(yt, monkeypatch):
    """V2-366's rule, unchanged: a search must not interrupt playback. Only the VIEW moves."""
    from widgets import store
    _seed_band(yt, monkeypatch, "ronaldinho")
    db = store.load(yt.WID, {})
    db.update({"videoId": "keep-me", "paused": False})
    store.save(yt.WID, db)
    _seed_band(yt, monkeypatch, "alunizaje 1969")
    db = store.load(yt.WID, {})
    assert db["videoId"] == "keep-me" and db["paused"] is False


# ── D · LA COLA DE UNA FRASE NO ES UNA ORDEN ───────────────────────────────────────────────────────────
# +49.1: «Vale, páralo, y ahora búscame vídeos del alunizaje en el año … sesenta y nueve.» The tail came
# back as a turn of its own and the model called `youtube:set_volume {volume: 69}`. «Yo no he dicho nada
# de ningún volumen.»
from nucleo.flash import direct_action


def _brief(answers: dict, *, open_ids=("youtube",)):
    """A brief handle in the REAL shape `jev.ask_many` returns — the same double nodes 2.68/2.72/2.75 use."""
    import threading
    from nucleo.flash import turn_brief as _tb
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


@pytest.fixture
def on_screen(monkeypatch):
    from nucleo.flash import turn_brief as _tb
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)


@pytest.mark.parametrize("words,expected", [
    ("sesenta y nueve.", True), ("69", True), ("el tres", True),
    ("mil novecientos sesenta y nueve", True),
    ("Vale, páusalo.", False), ("páralo", False), ("ponme el dos", False),
    ("ciérralo todo", False), ("", False),
])
def test_only_a_number_reaches_only_numbers(words, expected):
    """The narrowing that makes this guard shippable. `too_thin_to_commission` calls «páusalo» and
    «páralo» fragments too — its `_ALSO_A_VERB` hatch matches «para», and the enclitic is another token
    — and those are his commonest orders. Measured, not assumed:"""
    from nucleo.flash import turn_brief as _tb
    assert direct_action.only_a_number(words) is expected, words
    if not expected and words:
        # …with the brief ANSWERING exactly as it did on the measured turn. Without it `_info is None`
        # makes the guard stand down for every word and the parametrize proves nothing — a disarm that
        # deleted the narrowing stayed green.
        b = _brief({_tb.TARGET_KEY: ("none", 0.31), _tb.REQUEST_KEY: ("order", 0.9)})
        assert direct_action.a_fragment_moves_nothing(words, brief=b) == "", words


def test_a_bare_number_with_the_verdict_silent_moves_nothing():
    """The measured turn: `screen_action = none` at 0.31 — answered, and naming nothing."""
    from nucleo.flash import turn_brief as _tb
    b = _brief({_tb.TARGET_KEY: ("none", 0.31), _tb.REQUEST_KEY: ("answer", 1.0)})
    assert direct_action.a_fragment_moves_nothing("sesenta y nueve.", brief=b)


def test_but_a_bare_number_the_verdict_NAMES_still_runs(on_screen):
    """A text guard may not contradict the screen verdict — V2-741 and V2-748 both paid for that."""
    from nucleo.flash import turn_brief as _tb
    b = _brief({_tb.TARGET_KEY: ("youtube:play_result", 0.92), _tb.REQUEST_KEY: ("order", 0.9)})
    assert direct_action.a_fragment_moves_nothing("el tres", brief=b) == ""


def test_and_with_NO_brief_at_all_it_stands_down():
    """Jev off, slow, failed or disabled: today's path, exactly. Fail-open, as V2-754 promised."""
    assert direct_action.a_fragment_moves_nothing("sesenta y nueve.", brief=None) == ""


def test_the_guard_sits_at_the_ONE_point_both_branches_converge_on():
    """The tag and the `widget_data` tool both end in `_apply_widget_data`. A rule installed in one of two
    branches is this repo's own named way of fixing half a defect."""
    import voice.engine.llm.providers.nucleo as prov
    src = inspect.getsource(prov)
    body = src[src.index("def _apply_widget_data(wid: str"):]
    body = body[:body.index("def _log_dataop")]
    # CODE only: the comment above the call names the function too, and a disarm that deleted the call
    # and left the comment stayed green.
    body = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    assert "a_fragment_moves_nothing" in body
    assert body.index("a_fragment_moves_nothing") < body.index("action_mode_now"), (
        "it has to decide BEFORE the call enters the consent gate")


# ── E · UNA PREGUNTA EDUCADA ES UNA ORDEN ──────────────────────────────────────────────────────────────
# +95.2: «¿Puedes enseñarme el catálogo?» → screen_action = youtube:show_tab 0.85, request_type = question
# 0.64 → V2-756's refusal list vetoed it, the card never moved, and the turn PROMISED instead: «Voy a
# quitar el vídeo para que quede el catálogo a la vista». «Bueno, dices que vas a hacer eso, pero no lo
# haces.»

def test_a_question_is_no_longer_a_veto():
    assert "question" not in direct_action.NOT_AIMED_AT_THE_SCREEN
    assert set(direct_action.NOT_AIMED_AT_THE_SCREEN) == {"comment", "greeting"}


def test_the_measurement_that_removed_it_is_written_down():
    """Every entry of this list costs a real order when it is wrong. The numbers stay beside it."""
    src = inspect.getsource(direct_action)
    block = src[:src.index("NOT_AIMED_AT_THE_SCREEN = ")]
    for phrase in ("¿Puedes enseñarme el catálogo?", "¿Me pones el siguiente?",
                   "¿el siguiente es de la NASA?"):
        assert phrase in block, phrase


# ── F · EL ORBE SE APARTA CUANDO ALGO SE PONE A PANTALLA COMPLETA ──────────────────────────────────────
# «en el frontend se ve el orbe con el pulso, y eso molesta cuando estás viendo un vídeo a pantalla
# completa. Yo creo que automáticamente cuando algo se pone en pantalla completa, el orbe tiene que
# desaparecer y irse a la barra inferior del sistema operativo.»

def _js(path):
    return open(path, encoding="utf-8").read()


def test_the_dock_is_the_one_V2_623_already_built():
    src = _js("frontend/app/core/store.js")
    assert "export const orbDockForFullscreen" in src
    fn = src[src.index("export const orbDockForFullscreen"):]
    fn = fn[:fn.index("\n};") + 3]
    assert "setOrbDockRaw" in fn and "setOrbDock(" not in fn, (
        "his own choice of place is NOT overwritten: this one is ours and it is temporary")
    assert "localStorage" not in fn
    assert "_dockBeforeFullscreen" in fn, "…and it is handed back on the way out"


def test_every_site_that_enters_or_leaves_full_screen_tells_the_orb():
    """There are six of them and the classes are the truth — so they all ask the DOM through one method
    instead of each remembering to move a flag."""
    src = _js("frontend/app/widgets/desktop.js")
    assert "_syncOrbDock(){" in src
    method = src[src.index("_syncOrbDock(){"):]
    method = method[:method.index("\n  }") + 4]
    assert "document.fullscreenElement" in method and "hb-cinema" in method and "hb-fullwide" in method
    assert "orbDockForFullscreen" in method
    # Every METHOD that adds or removes those classes must also tell the orb. Per-method and not
    # per-line on purpose: in `maximize()` the mutation is at the top of an if/else and the sync is at
    # the bottom of the method, which is the right place for it — one call covering both branches.
    import re
    lines = src.splitlines()
    starts = [i for i, ln in enumerate(lines) if re.match(r"^  [A-Za-z_$][\w$]*\(.*\{\s*$", ln)]
    assert len(starts) > 20, "failed to split the class into methods"

    def _method_of(i):
        head = max([s0 for s0 in starts if s0 <= i], default=0)
        end = min([s0 for s0 in starts if s0 > i], default=len(lines))
        return "\n".join(lines[head:end])

    seen = 0
    for i, ln in enumerate(lines):
        if "hb-cinema" not in ln or not (".classList.add(" in ln or ".classList.remove(" in ln):
            continue
        seen += 1
        # …and the call has to be in the method's OWN flow, not buried in a callback that only runs on
        # the lazy-catalog path: `maximize()` carries one inside a `.then()` (indent 10), and with the
        # method-level call deleted this assertion stayed green on it. Indent ≤ 6 = the body, or a
        # branch of it; deeper than that is somebody else's continuation.
        flow = [l for l in _method_of(i).splitlines()
                if "_syncOrbDock()" in l and len(l) - len(l.lstrip()) <= 6]
        assert flow, (
            f"line {i+1} moves full-screen and its method never tells the orb: {ln.strip()}")
    assert seen >= 5, f"only found {seen} sites that move full-screen"
    assert 'addEventListener("fullscreenchange"' in src, (
        "leaving native fullscreen with Escape goes through none of the six sites")
