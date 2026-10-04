"""An ORDER beside a searched fact is carried out, in both channels (V2-781 T515, 2026-10-03).

Measured on the pair `find-a-future-release-and-remind-me__us`: «Can you set a reminder for the premiere day?» — the
model searched the date again, and the search's answer pass, which has no tools, said «I can't actually set
reminders myself, but I've got the date for you: … October 30, 2026». The brief had read `request_type=order`,
`wants_words=act`, `catalog_widget=agenda` (0.91). `scheduled_jobs` stayed empty. The sibling of
`call_after_read` (full20 C5) now runs after a search too: one bounded pass on the card the brief names.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import act_repair

DENIAL = ("I can't actually set reminders myself, but I've got the date for you: Dexter: Resurrection season 2 "
          "premieres Friday, October 30, 2026 on Paramount+. Anything else you need?")
CALL = ("widget_data", {"widget_id": "agenda", "action": "add_meeting",
                        "payload": {"title": "Dexter: Resurrection S2 premiere", "date": "2026-10-30"}})


class _Model:
    def __init__(self, calls):
        self.calls, self.seen = calls, []

    async def complete(self, messages, **kw):
        self.seen.append(messages)
        for name, args in self.calls:
            kw["on_tool_call"](name, args)


@pytest.fixture
def brief(monkeypatch):
    """A brief that reads like the measured one; `set(**verdicts)` changes what it says."""
    from nucleo.flash import build_decision as bd, turn_brief as tb
    said = {tb.REQUEST_KEY: "order", tb.WORDS_KEY: "act"}
    monkeypatch.setattr(tb, "read", lambda b, k, d="", min_confidence=None: (said[k], {"used": True})
                        if k in said else (d, None))
    monkeypatch.setattr(bd, "named_card", lambda b: "agenda")
    return said


@pytest.fixture
def model(monkeypatch):
    import nucleo.flash.fast_client as fc
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid, *a, **k: "")
    holder = {}

    def use(calls):
        holder["m"] = _Model(calls)
        monkeypatch.setattr(fc, "FastClient", lambda: holder["m"])
        return holder["m"]
    return use


def test_the_order_card_needs_a_sure_order_or_a_refused_act(brief):
    from nucleo.flash import turn_brief as tb
    assert act_repair.order_card_after_search({"x": 1}, "It premieres October 30.") == "agenda"
    brief[tb.WORDS_KEY] = "tell"                    # the ES twin read `tell` on the same order
    assert act_repair.order_card_after_search({"x": 1}, "Se estrena el 30 de octubre.") == "agenda"
    brief[tb.REQUEST_KEY] = "question"
    assert act_repair.order_card_after_search({"x": 1}, "Se estrena el 30 de octubre.") == "", \
        "a question answered with its fact never reaches here"
    assert act_repair.order_card_after_search(
        {"x": 1}, "Se estrena el 30 de octubre. Eso sí, avisarte no puedo hacerlo por mi cuenta.") == "agenda"


def test_the_pass_takes_the_call_with_what_was_found(brief, model):
    m = model([CALL])
    got = asyncio.run(act_repair.call_after_search("Can you set a reminder for the premiere day?", DENIAL, {"x": 1}))
    assert got == {"widget_id": "agenda", "action": "add_meeting", "payload": CALL[1]["payload"]}
    assert "October 30, 2026" in m.seen[0][0]["content"], "what the search found travels to the pass"


def test_no_call_or_another_card_is_nothing(brief, model):
    model([])
    assert asyncio.run(act_repair.call_after_search("set a reminder", DENIAL, {"x": 1})) is None
    model([("widget_data", {"widget_id": "mensajeria", "action": "send_to", "payload": {}})])
    assert asyncio.run(act_repair.call_after_search("set a reminder", DENIAL, {"x": 1})) is None


def test_the_text_channel_unsays_the_refusal_and_keeps_the_answer():
    out = act_repair.without_the_denial(DENIAL)
    assert "can't" not in out and "October 30, 2026" in out
    assert act_repair.without_the_denial("No puedo poner avisos. Se estrena el 30 de octubre.") == "Se estrena el 30 de octubre."


def test_the_probe_runs_the_call_through_its_execute_block(brief, model, monkeypatch):
    from nucleo import websearch
    from nucleo.flash import probe_after
    model([CALL])
    monkeypatch.setattr(websearch, "search", lambda q: {"source": "test", "results": [{"title": "Dexter", "url": "u",
                                                                                       "snippet": "October 30, 2026"}]})

    class _Stream:
        def stream(self, *a, **k):
            async def gen():
                yield DENIAL
            return gen()

    class _Same:
        def sanitize(self, s, **k):
            return s

        def sanitize_reply(self, s):
            return s

    calls = [{"name": "web_search", "args": {"query": "Dexter Resurrection season 2 premiere"}}]
    out = asyncio.run(probe_after.answer_a_search(
        FastClient=_Stream, _forced_search=False, _res=None, action="search", dialog=_Same(), speech=_Same(),
        operator_text="Can you set a reminder for the premiere day?", spec=None, text="set a reminder",
        tool_calls=calls, _tbrief={"x": 1}))
    assert out["action"] == "widget_data"
    assert calls[-1]["args"]["action"] == "add_meeting" and calls[-1]["args"]["_repair"] is True
    assert "can't" not in out["spoken"] and "October 30, 2026" in out["spoken"]


def test_the_voice_runs_it_and_says_what_happened_after_the_refusal(brief, model):
    model([CALL])
    applied, sent, acted, done = [], [], {}, {"v": False}
    ran = asyncio.run(act_repair.voice_after_search(
        "Can you set a reminder for the premiere day?", DENIAL, {"x": 1}, None, window=[],
        apply=lambda *a: applied.append(a), send=sent.append, emit=lambda *a, **k: None, acted=acted, done=done))
    assert ran and applied == [("agenda", "add_meeting", CALL[1]["payload"])]
    assert acted.get("widget") is True and done["v"] is True
    assert sent, "a refusal that already streamed is followed by what happened"


# ── the ES twin's path (round 3, 2026-10-03 22:3x): escalate + agenda write in one turn ───────────────────────

ES_TURN = ("Pero si te pedí que me avisaras tú, no que me lo apunte yo. ¿No puedes programarme un recordatorio para el "
           "día del estreno? Y de paso, ¿de dónde has sacado esa fecha?")
ES_CALLS = [{"name": "escalate_to_slowbrain", "args": {"request": "Verificar la fecha de estreno de Dexter"}},
            {"name": "widget_data", "args": {"widget_id": "agenda", "action": "add_task",
                                             "payload": {"title": "Estreno de Dexter", "date": "2026-10-30",
                                                         "remind": "2026-10-30 09:00"}}}]


def test_the_show_backstop_never_throws_away_a_write(monkeypatch):
    """«has sacado esa fecha» read as «saca» + «fecha» → `canvas:show:clock`, and the agenda write was lost."""
    from nucleo.flash import probe_mirrors as PM, reply_promise as RP
    from nucleo.flash import router_guards as RG

    async def _none(*a, **k):
        return None
    monkeypatch.setattr(RP, "prefetch", _none)

    class _Sess:
        window, last_action = [], ""
    blk = asyncio.run(PM.mirror_the_voice_backstops(
        _akp=None, _cw=None, _hw=False, _router=RG, _rt=None, _sp=None, _tbrief=None, action="escalate",
        canvas_h=None, dialog=None, names={c["name"] for c in ES_CALLS}, operator_text=ES_TURN, sess=_Sess(),
        spec=None, speech=None, spoken="Te programo el recordatorio para el 30 de octubre.", tags=[], text=ES_TURN,
        tool_calls=list(ES_CALLS)))
    assert not str(blk.get("action", "escalate")).startswith("canvas:show"), blk.get("action")


def test_an_escalating_turn_still_runs_its_data_op(monkeypatch):
    from nucleo.flash import escalate as ESC, probe_after as PA, widget_data_turn as WDT
    ran = []
    monkeypatch.setattr(ESC, "escalate_to_slowbrain", lambda req, context=None: "task-1")

    async def _exec(calls, text="", brief=None):
        ran.append([c["args"]["action"] for c in calls if c["name"] == "widget_data"])
        return {"executed": "widget_data"}
    monkeypatch.setattr(WDT, "execute", _exec)

    class _Sess:
        window, last_action = [], ""
    out = asyncio.run(PA.execute_what_was_decided(
        _kind=None, _r=None, _res=None, _tbrief=None, _trace_id="t", _window_goal="", action="escalate", execute=True,
        images_req=None, music_req=None, operator_text=ES_TURN, sess=_Sess(), spoken="", tags=[], text=ES_TURN,
        tool_calls=list(ES_CALLS), video_req=None))
    assert ran == [["add_task"]], "the agenda write the model made beside the escalation never ran"
    assert out["return_extra_exec"]["executed"] == "escalate"
