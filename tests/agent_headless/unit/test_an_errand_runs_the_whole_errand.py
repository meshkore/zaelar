"""V2-684 — the errand, END TO END: order → send → echo → birth → answer → wake → reply → close.

V2-683 covered the PIECES with every neighbour stubbed. This drives the ARC, which is where all of the
interesting behaviour of an errand actually lives: it is the only shape in which «he answers in ten hours»,
«he asks to speak to Ricart», «nobody ever answers» and «the message never left» are different from one
another.

One double at the transport (`harness/errand_world.World`) and one for the party turn's model. Everything
between them is the product: the widget's `send_to`, the owner's flush WITH its secret scan, the bus
watcher's three signals, the ledger, the wake, the parse, the verifier and the expiry sweep.

## What an arc is allowed to assume

Nothing about the clock: every beat is passed the world's own `now`, so ten hours cost no seconds and no
test depends on the machine it runs on. And nothing about shadow: the shipped default is SHADOW and every
arc runs under it, except the ones that say `armed(...)` out loud, one at a time.
"""
from __future__ import annotations

import time

import pytest

from tests.agent_headless.harness.errand_world import World, agenda_holds, answers, armed

PLATFORM = "telegram"
OBJECTIVE = "organizar una reunión con Iván esta tarde, en las próximas 4 horas"
OPENER = "Hola, soy Zaelar, el asistente de Ricard. ¿Tienes un rato esta tarde para veros?"


@pytest.fixture
def world(tmp_path, monkeypatch):
    """An isolated ledger, isolated widget stores, and a world at the transport."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    import bus
    import memory.db as _db
    _db.reset_db()
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path / "widgets"))
    monkeypatch.setattr(wstore, "_last_hash", {})
    # The operator's OWN `config/playbooks.json` must not decide what green means. Measured the hard way
    # (2026-09-13): the live node writes `shadow: false` into that file while it runs, and the suite read
    # it — the shadow arc armed itself and sent a second message. Same rule as `settings.json`,
    # `config/v2.json` and `store.DATA_DIR` in the root conftest, reaching the one store it had not.
    from nucleo import workspace
    from nucleo.errands import playbooks
    monkeypatch.setattr(workspace, "root", lambda: tmp_path)
    playbooks._override_cache = (None, {})
    from nucleo.errands import wake as wake_mod, watch
    wake_mod._last_wake.clear()
    watch.stop()
    watch._pending_births.clear()
    watch._pending_wakes.clear()
    bus.reset()
    w = World()
    # The watcher subscribes at ENGINE BOOT, before anything can be sent — a bus subscription only ever
    # receives what is emitted after it exists, so a fixture that lets `tick()` subscribe lazily would
    # measure a world where the first message is structurally invisible.
    assert watch.start(), "the errand watcher has to be listening before the first order leaves"
    try:
        yield w
    finally:
        w.close()
        watch.stop()
        _db.reset_db()


# ── the arc, assembled once ──────────────────────────────────────────────────────────────────────────────
def _ivan(*, preferred: str = PLATFORM) -> None:
    from widgets.contactos import data as contactos
    contactos.apply_action("add_contact", {
        "name": "Iván Musikin", "kind": "person",
        "channels": [{"platform": "telegram", "handle": "@ivanm"},
                     {"platform": "whatsapp", "handle": "+34600111222"},
                     {"platform": "email", "handle": "ivan@example.com"}],
        "preferred": preferred,
    })


def _open(world: World, *, objective: str = OBJECTIVE, text: str = OPENER,
                deliver: bool = True) -> dict:
    """The operator's confirmed order, all the way to a born errand. Returns what the arc needs afterwards."""
    from nucleo import errands
    world.act("send_to", {"contact": "Iván Musikin", "text": text, "objective": objective})
    orders = world.outbox()
    assert len(orders) == 1, "one confirmed order is one message on the wire"
    if not deliver:
        world.fail(orders[0])
        world.beat()
        return {"order": orders[0], "chat": "", "errand": None}
    chat = world.deliver(orders[0])
    world.beat()
    errand = errands.for_thread(PLATFORM, chat)
    return {"order": orders[0], "chat": chat, "errand": errand}


def _answers_and_wakes(world: World, chat: str, text: str, *, after_s: float = 300.0) -> None:
    """The other person writes, and the engine gets far enough to have moved.

    Two beats, and that is the product: the first notes the message and starts the coalesce window (the
    owner's triage has to have landed it in the store the dossier reads), the second fires the wake. The
    gap between exchanges is real too — `wake.MIN_GAP_S` deliberately refuses two moves in twenty seconds,
    because two answers crossing in one conversation is worse than a slow one.
    """
    world.advance(after_s)
    world.say(PLATFORM, chat, text)
    world.beat()
    world.beat()


# ── 1 · the whole thing, agreed ─────────────────────────────────────────────────────────────────────────
def test_the_errand_is_born_from_a_confirmed_order_and_owns_the_conversation(world):
    _ivan()
    got = _open(world)
    e = got["errand"]
    assert e is not None, "the echo of a real send is what births the errand"
    assert e["objective"] == OBJECTIVE
    assert e["kind"] == "meeting", "the kind is read from the playbooks by start(), not by the caller"
    assert e["done_when"] == {"widget": "agenda", "has": "meeting", "within": "window"}
    assert e["state"] in ("contacting", "gathering")
    from nucleo import errands
    assert [(t["platform"], t["chat_id"]) for t in errands.threads(e["id"])] == [(PLATFORM, got["chat"])]


def test_an_agreement_closes_the_errand_against_the_AGENDA_and_not_against_the_model(world, monkeypatch):
    """The operator's condition, verbatim: «la tarea no termina hasta que no está correctamente programada
    esa reunión». So the model saying `agreed` moves the state and closes NOTHING — the agenda does."""
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "Perfecto, a las 18:00 entonces.", "state": "agreed"}')
    got = _open(world)
    eid = got["errand"]["id"]
    notes = _capture_notes(monkeypatch)

    _answers_and_wakes(world, got["chat"], "A las seis me va bien")
    assert errands.get(eid)["state"] == "agreed"
    assert not errands.get(eid)["closed_at"], "agreeing is not the same as having it in the agenda"

    # ⚠️ The step that does not exist yet: nothing in the engine turns an agreement into an agenda row.
    # The party turn holds no tools by design, and V2-683 row 6 (the calendar invitation) is still blocked
    # on `connectors/calendar/`. Writing it by hand here is what makes this a test of the VERIFIER — and
    # naming the gap is worth more than an arc that pretends the loop already closes itself.
    agenda_holds({"date": time.strftime("%Y-%m-%d"), "startTime": "18:00", "title": "Reunión con Iván",
                  "status": "confirmed", "created": time.strftime("%Y-%m-%d")})
    world.beat()
    row = errands.get(eid)
    assert row["state"] == "closed" and row["closed_at"] > 0
    assert row["outcome"] == "la gestión está hecha y verificada", \
        "it closed because the agenda says so — the sentence names WHO checked"
    assert any("ya está hecho y verificado" in n for n in notes), \
        "said by the thing that checked, never by the model that hoped"


def test_a_closed_errand_RELEASES_its_conversation(world, monkeypatch):
    from nucleo import errands
    _ivan()
    got = _open(world)
    errands.close(got["errand"]["id"], "closed", "hecho")
    assert errands.for_thread(PLATFORM, got["chat"]) is None, \
        "a finished errand owns nothing, whatever the binding still says"


# ── 2 · ten hours later ─────────────────────────────────────────────────────────────────────────────────
def test_an_answer_TEN_HOURS_later_still_finds_an_errand_that_knows_what_it_started(world, monkeypatch):
    """«cuando él conteste, ahora o dentro de diez horas» — the reason this is a ROW and not a process.

    The window comes from the operator's own words («en los próximos dos días»), which is the grammar
    `window_from` reads; a four-hour errand answered after ten is a CLOSED errand, and that is arc 4.
    """
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    model = answers(monkeypatch, '{"say": "Genial, ¿te va bien mañana a las 10?", "state": "negotiating"}')
    got = _open(world, objective="quedar con Iván en los próximos 2 días")
    eid = got["errand"]["id"]

    _answers_and_wakes(world, got["chat"], "Perdona, acabo de verlo", after_s=10 * 3600)

    assert errands.get(eid)["state"] == "negotiating"
    dossier = model.calls[-1]["dossier"]
    assert "quedar con Iván" in dossier, "the row still carries what it was opened to do"
    assert "Perdona, acabo de verlo" in dossier, "and the message that woke it"
    assert world.texts()[-1] == "Genial, ¿te va bien mañana a las 10?"


# ── 3 · «quiero hablar con Ricart» ──────────────────────────────────────────────────────────────────────
def test_asking_to_speak_to_the_operator_BLOCKS_the_errand_and_it_never_writes_again(world, monkeypatch):
    """His own rule: «si él dice que quiere hablar conmigo, tú te bloqueas y le pasas nota».

    The assertion that matters is the second one — not that it blocked, but that it stayed quiet afterwards.
    """
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch,
            '{"say": "Claro, se lo digo a Ricard.", "state": "blocked", '
            '"ask_operator": "Iván prefiere hablar contigo directamente.", "reason": "pide al operador"}')
    got = _open(world)
    eid = got["errand"]["id"]
    notes = _capture_notes(monkeypatch)

    _answers_and_wakes(world, got["chat"], "Prefiero hablarlo con Ricard directamente")

    row = errands.get(eid)
    assert row["state"] == "blocked" and row["closed_at"] > 0
    assert any("Iván prefiere hablar contigo" in n for n in notes), "the note is the whole point of blocking"

    before = len(world.sent())
    _answers_and_wakes(world, got["chat"], "¿Hola? ¿Sigues ahí?")
    assert len(world.sent()) == before, "a blocked errand is deaf on purpose: it owns nothing any more"


# ── 4 · nobody answers ──────────────────────────────────────────────────────────────────────────────────
def test_nobody_answers_so_the_errand_ENDS_and_he_is_told_once(world, monkeypatch):
    """«tampoco hay que abrir una tarea y dejarla abierta, porque esa persona puede no contestar nunca más»."""
    from nucleo import errands
    _ivan()
    got = _open(world)
    eid = got["errand"]["id"]
    notes = _capture_notes(monkeypatch)

    world.advance(6 * 24 * 3600)          # past the 4 h window AND past the 24 h grace
    world.beat()

    row = errands.get(eid)
    assert row["state"] == "abandoned" and row["closed_at"] > 0
    assert sum("Se acabó el plazo" in n for n in notes) == 1, "told once, not once per beat"

    world.beat()
    assert sum("Se acabó el plazo" in n for n in notes) == 1


# ── 5 · the counter-offer ───────────────────────────────────────────────────────────────────────────────
def test_two_exchanges_are_ONE_conversation_and_ONE_errand(world, monkeypatch):
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch,
            '{"say": "¿Te va bien a las 18:00?", "state": "negotiating"}',
            '{"say": "Perfecto, a las 19:00.", "state": "agreed"}')
    got = _open(world, objective="quedar con Iván en los próximos 2 días")
    eid = got["errand"]["id"]

    _answers_and_wakes(world, got["chat"], "¿Qué hora te viene bien?")
    _answers_and_wakes(world, got["chat"], "A las 18:00 no puedo, ¿a las 19:00?")

    assert world.texts()[1:] == ["¿Te va bien a las 18:00?", "Perfecto, a las 19:00."]
    assert {o["chatId"] for o in world.sent()[1:]} == {got["chat"]}, "one conversation, never a second one"
    assert errands.count_open() == 1
    assert errands.get(eid)["wake_count"] == 2


# ── 6 · the message that never left ─────────────────────────────────────────────────────────────────────
def test_a_send_that_FAILED_opens_no_errand_at_all(world):
    from nucleo import errands
    _ivan()
    got = _open(world, deliver=False)
    assert got["errand"] is None
    assert errands.count_open() == 0, "an errand must not exist for a message that never left"


def test_a_LATE_echo_for_a_failed_send_births_nothing_either(world):
    """What `msg.send_failed` actually buys, measured rather than assumed.

    ⚠️ Written after a disarm came back GREEN: killing the `send_failed` handler changed nothing, because
    the arc above is ALSO protected by «no echo, no errand» — two independent guards, and the test was
    anchored on the one that carries no weight there. This is the case where the drop is load-bearing: a
    transport that reports a failure and then echoes anyway (a retry that half-worked, a duplicate
    delivery) must not open an errand for an order the operator was already told had failed.
    """
    from nucleo import errands
    _ivan()
    got = _open(world, deliver=False)
    world.deliver(got["order"])
    world.beat()
    assert errands.count_open() == 0
    assert errands.for_thread(PLATFORM, "chat-1") is None


def test_the_owners_OWN_BEAT_flushes_the_outbound_queues(world):
    """The wiring of the V2-684 fix, guarded at the source.

    ⚠️ Also written after a GREEN disarm: the arcs drive the flush through the harness's beat, so removing
    it from the owner's own cycle left every one of them green — the arcs measure the FLUSH and nothing
    measured that anybody calls it. Read comment-stripped, because documenting this rule in prose must not
    be what satisfies it (V2-615's trap).
    """
    import re
    from pathlib import Path
    src = Path("widgets/mensajeria/owner.py").read_text(encoding="utf-8")
    code = re.sub(r"#[^\n]*", "", re.sub(r'"""(?:.|\n)*?"""', "", src))
    assert "_flush_queues" in code.split("async def _consume")[1].split("@staticmethod")[0], \
        "an errand's reply reaches nobody unless the owner drains the queue on its own beat"


# ── 7 · a meeting he already had ────────────────────────────────────────────────────────────────────────
def test_a_meeting_with_NO_creation_STAMP_closes_nothing(world):
    """⚠️ The case the FIRST LIVE RUN found, and the one the unit tests could not (2026-09-13).

    The agenda writes no `created` on any meeting — measured on the operator's own store. The verifier
    used to skip a row only when it carried a stamp OLDER than the errand, so a row with no stamp at all
    read as «could be ours»: a real errand closed itself in the same second it was born, announcing «la
    gestión está hecha y verificada» over his own «Cinema with Mary» that evening.

    Every previous test of this passed because it wrote the field BY HAND — measuring a shape the real
    data has never had. This one measures the real one.
    """
    from nucleo import errands
    _ivan()
    agenda_holds({"date": time.strftime("%Y-%m-%d"), "startTime": "19:00", "title": "Cinema with Mary",
                  "status": "confirmed"})
    got = _open(world)
    world.beat()
    row = errands.get(got["errand"]["id"])
    assert not row["closed_at"], "no creation stamp means it cannot be told from what was already there"
    assert row["state"] != "closed"


def test_a_meeting_he_ALREADY_had_closes_nothing(world):
    """Last week's dentist must not close today's errand — the difference between verifying and coinciding."""
    from nucleo import errands
    _ivan()
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    agenda_holds({"date": time.strftime("%Y-%m-%d"), "startTime": "09:00", "title": "Dentista",
                  "status": "confirmed", "created": yesterday})
    got = _open(world)
    world.beat()
    assert not errands.get(got["errand"]["id"])["closed_at"]


# ── shadow rides all seven ──────────────────────────────────────────────────────────────────────────────
def test_in_SHADOW_the_arc_runs_whole_and_reaches_nobody(world, monkeypatch):
    """The shipped default. It decides, it moves state, it logs what it would have said — and the wire is
    silent after the one message the operator himself confirmed."""
    from nucleo import errands
    _ivan()
    model = answers(monkeypatch, '{"say": "¿Te va bien a las 18:00?", "state": "negotiating"}')
    got = _open(world)

    _answers_and_wakes(world, got["chat"], "¿Qué hora te viene bien?")

    assert model.calls, "it still thinks"
    assert errands.get(got["errand"]["id"])["state"] == "negotiating", "and still moves"
    assert len(world.sent()) == 1, "and nothing beyond his own confirmed opener ever left"


def test_the_reply_it_composes_leaves_only_through_the_owner_and_its_SECRET_SCAN(world, monkeypatch):
    """Where a composed reply actually goes, measured rather than assumed.

    `wake._send` puts the text in the SAME outbound queue a dictated reply uses; the owner's flush is what
    publishes it, and that flush is the one door where `memory/secrets.py` reads a text written by a MODEL
    for somebody outside.

    ⚠️ This arc is what FOUND the defect it now guards (2026-09-13): that flush ran only inside
    `_Owner.handle`, and the messaging widget declares no background cycle — so nothing drained the queue
    until the operator's next messaging action, and an ARMED errand would have answered nobody, ever. It
    was invisible because the feature ships in SHADOW, where there is nothing to flush. The owner's own
    beat calls it now.
    """
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "Te paso mi clave: sk-live-0123456789abcdefghij", "state": "negotiating"}')
    got = _open(world)

    notes = _capture_notes(monkeypatch)
    _answers_and_wakes(world, got["chat"], "¿Cómo entro?")

    assert len(world.sent()) == 1, "the scan refused to publish a text carrying a secret"
    refused = world.refusals()
    assert refused and refused[0]["ref"] != got["order"]["ref"], "and it refused the COMPOSED one"
    assert any("NO he enviado" in n for n in notes), "and told the operator instead of failing silently"


def _capture_notes(monkeypatch) -> list[str]:
    from voice import brain_notes
    out: list[str] = []
    monkeypatch.setattr(brain_notes, "push", lambda text, **kw: out.append(str(text)))
    return out


# ══ THE WORD SWAP ════════════════════════════════════════════════════════════════════════════════════════
# «Lo más importante para mí es que el sistema pueda soportar tareas, workflows de este tipo o de cualquier
# otra índole SIN necesidad de que lo tengamos que programar.» That is the brain-worker doctrine's own test
# — swap reunión→cena, Iván→el taller, Meet→Zoom and see whether it still stands — applied to the first
# system built explicitly to satisfy it. It has been written down as a rule since V2-036 and never executed.

def test_an_errand_with_NO_PLAYBOOK_still_runs_the_whole_arc(world, monkeypatch):
    """The property that keeps a briefing from being a fence: an errand nobody wrote a playbook for is not
    refused, not downgraded, and not told to wait for a release that adds its kind."""
    from nucleo import errands
    from nucleo.errands import playbooks
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "¿Te lo llevo el jueves?", "state": "negotiating"}')

    got = _open(world, objective="pedirle a Iván que me revise el manuscrito esta semana",
                text="Hola, soy Zaelar, el asistente de Ricard. ¿Podrías revisarle un manuscrito?")
    e = got["errand"]
    assert e is not None
    assert e["kind"] == "generic" and playbooks.brief_for("generic") == "", "no playbook, and it runs anyway"
    assert e["done_when"] == {}, "and with no closing condition it ends by its deadline, never by a guess"

    _answers_and_wakes(world, got["chat"], "Claro, ¿cuándo lo necesitas?")
    assert errands.get(e["id"])["state"] == "negotiating"
    assert world.texts()[-1] == "¿Te lo llevo el jueves?"


def test_the_SAME_arc_with_the_words_swapped(world, monkeypatch):
    """reunión → cena. A different kind, a different playbook, the same machinery and not one line of it
    written for either word."""
    from nucleo import errands
    from nucleo.errands import playbooks
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "Te reservo mesa para dos a las 21:00.", "state": "negotiating"}')

    got = _open(world, objective="reservar mesa para cenar con Iván el viernes",
                text="Hola, soy Zaelar. ¿Te va bien cenar el viernes?")
    assert got["errand"]["kind"] == "booking", "the lexical sweep read the objective, nobody routed it"
    assert "confirma con la otra parte" in playbooks.brief_for("booking")

    _answers_and_wakes(world, got["chat"], "El viernes me va bien")
    assert errands.get(got["errand"]["id"])["state"] == "negotiating"
    assert world.texts()[-1] == "Te reservo mesa para dos a las 21:00."


def test_the_OPERATORS_OWN_FILE_wins_over_genesis(world, monkeypatch, tmp_path):
    """«esos workflows además fueran dinámicos, porque las preferencias de otro usuario podrían ser
    diferentes» — his Meet is somebody else's Zoom, and that is ONE file away, never a release."""
    from nucleo import workspace
    from nucleo.errands import playbooks
    monkeypatch.setattr(workspace, "root", lambda: tmp_path)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "playbooks.json").write_text(
        '{"playbooks": {"meeting": {"brief": "Usa SIEMPRE Zoom, nunca Meet."}}}', encoding="utf-8")
    playbooks._override_cache = (None, {})

    _ivan()
    armed(monkeypatch)
    model = answers(monkeypatch, '{"say": "Te paso el Zoom.", "state": "negotiating"}')
    got = _open(world)
    _answers_and_wakes(world, got["chat"], "¿Por dónde hacemos la llamada?")

    brief = model.calls[-1]["dossier"]
    assert "Zoom" in brief and "Propón dos horas CONCRETAS" not in brief, \
        "his file REPLACES the briefing for that kind; genesis is the default, not the law"


def test_no_playbook_names_a_person_a_company_or_a_site():
    """The ratchet that keeps a briefing from quietly becoming a script.

    A playbook may say «empieza por aquí»; the moment it says «llama a Iván» or «usa Google Meet» it has
    stopped being a shortcut and become a fence — and the next errand, the one nobody has written yet, gets
    LESS capability than the ones inside the catalogue. Grammar, not intent: a proper noun is a capitalised
    word that is not the first of its sentence and not one the language itself capitalises.
    """
    import re
    from nucleo.errands import playbooks
    banned = re.compile(r"\b(google|meet|zoom|teams|whatsapp|telegram|gmail|outlook|calendly|opentable|"
                        r"thefork|booking\.com|ivan|iván|ricard|ricart)\b", re.I)
    for kind, spec in playbooks.playbooks().items():
        blob = " ".join(str(v) for k, v in spec.items() if k != "matches" and isinstance(v, (str,)))
        blob += " " + " ".join(str(x) for x in (spec.get("needs") or []) + (spec.get("stop_when") or []))
        hit = banned.search(blob)
        assert not hit, f"playbook «{kind}» names «{hit.group(0)}» — that is a script, not a briefing"


# ══ THE INTERSECTION: the party's language, not the operator's ═══════════════════════════════════════════
# This is where V2-684's two halves meet. Every other language surface in the engine follows the OPERATOR;
# this one deliberately does not — a stranger who writes in English gets answered in English, from a
# Spanish install. `party.build_system` claims it in one line and nothing measured it.

def test_the_reply_follows_the_PARTYS_language_and_the_operators_is_only_the_fallback():
    from nucleo.errands import party
    from tests.lang import speaking
    from i18n import langs
    for code in ("es", "en"):
        with speaking(code):
            native = langs.current_language().native
            sys_prompt = party.build_system("Zaelar", "Ricard", native)
            assert "en el idioma en el que te escriba" in sys_prompt, \
                "the party's language wins — this is the one surface that does not follow the operator"
            assert f"si todavía no ha escrito, en {native}" in sys_prompt, \
                "and the operator's is the fallback for the FIRST message, when nobody has written yet"


def test_the_operators_language_reaches_the_party_turn_through_the_engine(world, monkeypatch):
    """End to end, not by reading `build_system`: the language the engine is speaking is what lands in the
    system prompt of the turn that talks to a stranger."""
    from tests.lang import speaking
    _ivan()
    model = answers(monkeypatch, '{"say": "ok", "state": "negotiating"}')
    got = _open(world)
    with speaking("en"):
        _answers_and_wakes(world, got["chat"], "Hi, who is this?")
    assert "English" in model.calls[-1]["system"], \
        "the engine's own language travelled into the party turn as the fallback"


# ══ THE ⏻ SWITCH: postponed, never lost ══════════════════════════════════════════════════════════════════

def test_an_answer_arriving_while_the_agent_is_STOPPED_is_postponed_and_not_lost(world, monkeypatch):
    """⚠️ The defect the first live run found (2026-09-13).

    The operator answered from his own second account while the ⏻ was off. The beat POPPED the pending
    wake and `wake()` then refused with «parado» — so the answer was not postponed, it was DISCARDED, and
    the errand could only ever move if that person happened to write a second time. «Postpone, don't
    lose» is the rule; consuming the queue six lines before the refusal is how it gets broken.
    """
    from nucleo import errands, runstate
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "¿Te va bien a las 18:00?", "state": "negotiating"}')
    got = _open(world)

    # Patched rather than `runstate.stop()`: the suite-root fixture pins the switch to RUNNING for every
    # test (conftest `_agente_en_marcha`), which is right — it stops the operator's real ⏻ from deciding
    # what green means — and it also means a test that wants the switch OFF has to say so at the reader.
    real = runstate.blocks_new_work
    runstate.blocks_new_work = lambda: True          # by hand: `monkeypatch.undo()` would also undo the
    try:                                             # model double and the arming, and call the real API
        _answers_and_wakes(world, got["chat"], "¿Qué hora te viene bien?")
        assert errands.get(got["errand"]["id"])["state"] == "contacting", "stopped means nothing moves"
        assert len(world.sent()) == 1, "and nothing is said to anybody"
    finally:
        runstate.blocks_new_work = real

    # The very next beat, with nobody writing again, finds the same answer still waiting.
    world.advance(60)
    world.beat()
    assert errands.get(got["errand"]["id"])["state"] == "negotiating"
    assert world.texts()[-1] == "¿Te va bien a las 18:00?"


# ══ WHAT THE PARTY TURN IS SHOWN, AND WHAT IT GIVES BACK ════════════════════════════════════════════════

def test_the_agenda_line_says_what_is_TAKEN_and_never_calls_it_free(world, monkeypatch):
    """⚠️ The line said the exact opposite of its own value, and the first live run caught it.

    `playbooks.free_slots_line` computes the intervals ALREADY TAKEN — its own docstring says so, and gives
    the reason: a gap this module computed would be a promise about his time made by arithmetic. The
    dossier announced them as «HUECOS LIBRES», so the model was told the operator was FREE exactly where he
    was busy, and the next thing it would have done is offer that hour to a stranger.
    """
    _ivan()
    model = answers(monkeypatch, '{"say": "¿Te va bien a las 18:00?", "state": "negotiating"}')
    agenda_holds({"date": time.strftime("%Y-%m-%d"), "startTime": "19:00",
                  "title": "Cine con María", "status": "confirmed"})
    got = _open(world)

    _answers_and_wakes(world, got["chat"], "¿A qué hora?")
    dossier = model.calls[-1]["dossier"]
    assert "Cine con María" in dossier, "what he already has is what the model has to work around"
    assert "HUECOS LIBRES" not in dossier, "these are the hours he is BUSY — the old label was a lie"
    assert "YA OCUPADO" in dossier and "no propongas encima" in dossier


def test_the_person_is_named_from_the_CONVERSATION_when_the_directory_has_nobody(world, monkeypatch):
    """«PERSONA con la que hablas: telegram» — the platform standing in for a person, live on 2026-09-13.

    And it is not an exotic case: the contact is filed under the HANDLE the operator dictated
    (`@cryptonite_fund`), while the conversation the connector created is keyed by the platform's own
    numeric id — so `find_by_channel(platform, chat_id)` legitimately finds nobody for a contact that
    exists. The thread knows the name the connector delivered it under.
    """
    _ivan()                                  # filed by handle; the chat the echo creates is another key
    model = answers(monkeypatch, '{"say": "Perfecto.", "state": "negotiating"}')
    got = _open(world)
    world.advance(300)
    world.say(PLATFORM, got["chat"], "Mejor mañana", name="Cryptonite")
    world.beat()
    world.beat()

    dossier = model.calls[-1]["dossier"]
    assert "PERSONA con la que hablas: Cryptonite" in dossier
    assert "PERSONA con la que hablas: telegram" not in dossier


def test_a_model_that_says_NOTHING_is_asked_again_with_more_room(world, monkeypatch):
    """⚠️ The defect that ended the first live run's conversation (2026-09-13).

    The turn brain is a REASONER and the call asked it for 700 tokens: it spent `reasoning_tokens: 700` of
    700 deliberating and returned `finish_reason: length` with `content: ''`. An empty string is not a
    decision — it is an empty turn — and the errand filed it as «unreadable» and said nothing at all to
    somebody who was waiting for an answer.
    """
    _ivan()
    armed(monkeypatch)
    model = answers(monkeypatch, "", '{"say": "Mañana a las 10, ¿te va bien?", "state": "negotiating"}')
    got = _open(world)

    _answers_and_wakes(world, got["chat"], "Mejor mañana por la mañana")
    assert len(model.calls) == 2, "an empty turn is asked again, exactly once"
    assert model.calls[1]["max_tokens"] > model.calls[0]["max_tokens"], \
        "asking the same thing the same way is not a retry"
    assert world.texts()[-1] == "Mañana a las 10, ¿te va bien?"
    from nucleo import errands
    assert errands.get(got["errand"]["id"])["state"] == "negotiating"


def test_an_errand_that_could_not_answer_TELLS_the_operator(world, monkeypatch):
    """He must never discover this one by himself: somebody answered, the errand could not answer back, and
    from outside that looks exactly like a gestión still quietly in flight — the class of lie the whole
    expiry announcement exists against."""
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, "no es JSON, es prosa", "tampoco esto")
    got = _open(world)
    notes = _capture_notes(monkeypatch)

    _answers_and_wakes(world, got["chat"], "¿Qué hora te viene bien?")
    assert len(world.sent()) == 1, "unreadable means SILENT toward the person — half an action is worse"
    assert any("no he sabido qué responder" in n for n in notes), \
        "and loud toward the operator, who is the one who can still answer"
    assert errands.get(got["errand"]["id"])["state"] == "contacting"


def test_the_party_turn_is_told_it_can_only_WRITE_in_this_conversation(world, monkeypatch):
    """⚠️ It closed the deal and added «Te enviaré el enlace de la videollamada» — live, 2026-09-13.

    It cannot: it has no tools, and nothing in the engine creates that link (V2-683 row 6). «No prometas
    nada que no esté en el encargo» does not catch it either, because the medium IS part of the errand —
    this is the other failure, the one this codebase keeps paying: an undeclared capability is one the
    model narrates. So the limit is stated, and stated in the FIRST PERSON, which is where the lie lives.
    """
    _ivan()
    model = answers(monkeypatch, '{"say": "Perfecto.", "state": "agreed"}')
    got = _open(world)
    _answers_and_wakes(world, got["chat"], "Vale, a las 11")

    system = model.calls[-1]["system"]
    assert "LO ÚNICO QUE PUEDES HACER es escribir mensajes" in system
    assert "enlaces" in system and "lo hace tu operador" in system, \
        "the way out has to be named too — a limit with no alternative is answered by inventing one"


def test_an_errand_that_AGREED_and_ran_out_is_not_announced_as_silence(world, monkeypatch):
    """«Se acabó el plazo y nadie contestó» over a deal the other person ACCEPTED is a plain falsehood
    about his own gestión, and the expensive direction of it: he would believe a closed agreement never
    happened. The announcement exists against believing something false about work in flight — inventing
    the ending is the one thing it may not do."""
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "Perfecto, mañana a las 11:00.", "state": "agreed"}')
    got = _open(world)
    eid = got["errand"]["id"]
    _answers_and_wakes(world, got["chat"], "Ok, a las 11")
    assert errands.get(eid)["state"] == "agreed"

    notes = _capture_notes(monkeypatch)
    world.advance(6 * 24 * 3600)              # past the window AND past the grace
    world.beat()

    row = errands.get(eid)
    assert row["state"] == "abandoned" and row["closed_at"] > 0
    told = " ".join(n for n in notes if "Se acabó el plazo" in n)
    assert told, "an errand that ends is always told once"
    assert "nadie contestó" not in told, "somebody DID answer, and they agreed"
    assert "se acordó" in told and "sin que quedara confirmado" in told


def test_an_errand_ANSWERED_but_never_closed_says_that_instead(world, monkeypatch):
    """The third ending, between the two: they talked and nothing was settled."""
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "¿Te va bien a las 18:00?", "state": "negotiating"}')
    got = _open(world)
    _answers_and_wakes(world, got["chat"], "Ya te diré algo")

    notes = _capture_notes(monkeypatch)
    world.advance(6 * 24 * 3600)
    world.beat()

    told = " ".join(n for n in notes if "Se acabó el plazo" in n)
    assert "hubo conversación" in told and "nadie contestó" not in told
    assert errands.get(got["errand"]["id"])["state"] == "abandoned"


# ══ THE RESTART: the conversation is the record, the bus is only a notification ══════════════════════════

def _restart() -> None:
    """What a restart really costs an errand: the wake queue and the bus subscriptions, both in memory.

    Not a simulation of one detail — it is the whole of what the process was holding. The ledger and the
    thread store are files and survive, which is the entire point of the row.
    """
    from nucleo.errands import wake as wake_mod, watch
    watch.stop()                          # the subscriptions die: whatever was queued on them is gone
    watch._pending_births.clear()
    watch._pending_wakes.clear()
    watch._last_reconcile = 0.0
    wake_mod._last_wake.clear()
    assert watch.start()


def test_an_answer_that_arrived_before_a_RESTART_is_taken_from_the_CONVERSATION(world, monkeypatch):
    """⚠️ The second defect of the first live run, and the one that actually killed it (2026-09-13).

    Three messages arrived at 22:28 on the conversation the errand owned. The engine was restarted at
    22:33. `_pending_wakes` is memory, the bus subscription is memory, and nothing ever asked the thread
    store what it was already holding — so the errand sat in `contacting` with `last_inbound` empty for
    ever, and the only thing that could have moved it was that person happening to write a fourth time.

    An errand is a ROW precisely so that it survives the process. Waking it can't depend on one.
    """
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "Mañana a las 10 entonces, te paso el enlace.", "state": "negotiating"}')
    got = _open(world)
    eid = got["errand"]["id"]

    world.advance(300)
    world.say(PLATFORM, got["chat"], "Mejor mañana por la mañana")
    _restart()
    assert errands.get(eid)["last_inbound"] == "", "the answer reached the store and nothing else"

    world.beat()                          # the reconciliation reads the conversation and owes itself a wake
    world.beat()                          # the coalesce window has passed: it moves
    row = errands.get(eid)
    assert row["state"] == "negotiating", "a restart is not an excuse for leaving somebody unanswered"
    assert row["last_inbound"], "and it records WHICH message it answered, so it does not answer it twice"
    assert world.texts()[-1] == "Mañana a las 10 entonces, te paso el enlace."


def test_the_same_reconciliation_does_NOT_answer_twice(world, monkeypatch):
    """The idempotency mark is the whole reason `last_inbound` exists. A reconciliation that ignored it
    would rewrite to the same person every thirty seconds — the loudest possible failure, and to a
    stranger."""
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "Mañana a las 10 entonces.", "state": "negotiating"}')
    got = _open(world)

    world.advance(300)
    world.say(PLATFORM, got["chat"], "Mejor mañana por la mañana")
    _restart()
    world.beat()
    world.beat()
    said = len(world.sent())

    for _ in range(4):                    # four sweeps, nobody writing anything new
        world.advance(60)
        world.beat()
    assert len(world.sent()) == said, "the message it already answered is not an answer it owes"
    assert errands.get(got["errand"]["id"])["state"] == "negotiating"


def test_the_reconciliation_never_answers_a_message_OLDER_than_the_errand(world, monkeypatch):
    """A conversation usually has a past. Reading the newest inbound without asking WHEN would make a new
    errand open by answering whatever was last said in that chat, which may have nothing to do with it."""
    from nucleo import errands
    _ivan()
    armed(monkeypatch)
    answers(monkeypatch, '{"say": "no debería decir nada", "state": "negotiating"}')

    # An hour before the errand exists. The world's clock starts at the real one and `start()` stamps the
    # row with the real one too, so «older than the errand» has to be walked backwards, not forwards.
    chat = "chat-con-pasado"
    world.advance(-3600)
    world.say(PLATFORM, chat, "oye, ¿te acordaste de lo del otro día?")
    world.beat()                          # drained while no errand owns this conversation: ignored
    world.advance(3600)

    world.act("send_to", {"contact": "Iván Musikin", "text": OPENER, "objective": OBJECTIVE})
    world.deliver(world.outbox()[0], chat_id=chat)
    world.beat()
    e = errands.for_thread(PLATFORM, chat)
    assert e is not None
    said = len(world.sent())

    _restart()
    for _ in range(3):
        world.advance(60)
        world.beat()
    assert len(world.sent()) == said, "an errand answers what was said TO it, not what the chat already had"
    assert errands.get(e["id"])["state"] == "contacting"
