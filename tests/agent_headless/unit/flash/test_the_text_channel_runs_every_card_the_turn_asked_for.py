"""«Put on the Dune trailer, some calm music, and open my calendar» opens THREE cards on the text channel too.

Measured in `tres-tarjetas-y-el-video-por-alusion` (both languages, 2026-10-10): the model called play_video,
play_music and show_widget(agenda) in one turn; the voice channel runs every call, the text channel named ONE
action (`music`) and dropped the other two — then «I'll get all three going» and «Paused» over a video that was
never loaded. The companions run beside the primary action.
"""
import asyncio

from nucleo.flash import probe_companions as pc

CALLS = [{"name": "play_video", "args": {"query": "Dune trailer", "action": "play"}},
         {"name": "play_music", "args": {"query": "calm ambient music", "action": "play"}},
         {"name": "show_widget", "args": {"widget_id": "agenda"}}]
TEXT = "Put on the Dune trailer, and some calm music in the background. Oh, and open my calendar."


def _wire(monkeypatch):
    ran = []
    from nucleo.flash import canvas_license, music_turn, video_turn

    async def _v(q, a="play"):
        ran.append(("video", q)); return {"executed": "play_video", "ok": True}

    async def _m(a, q):
        ran.append(("music", q)); return {"executed": "play_music", "ok": True}

    monkeypatch.setattr(video_turn, "execute", _v)
    monkeypatch.setattr(music_turn, "execute", _m)
    monkeypatch.setattr(canvas_license, "video_license", lambda *a, **k: True)
    monkeypatch.setattr(pc, "_show", lambda wid: ran.append(("show", wid)) or True)
    return ran


def _run(action, calls=CALLS, text=TEXT):
    return asyncio.new_event_loop().run_until_complete(pc.run(action, calls, text, window=[], brief=None))


def test_music_won_so_the_video_and_the_calendar_run_beside_it(monkeypatch):
    ran = _wire(monkeypatch)
    out = _run("music")
    assert ("video", "Dune trailer") in ran and ("show", "agenda") in ran
    assert not any(k == "music" for k, _ in ran), "the primary action is not run twice"
    assert len(out) == 2


def test_a_turn_that_is_not_about_cards_gets_no_companions(monkeypatch):
    ran = _wire(monkeypatch)
    assert _run("escalate") == [] and ran == []


def test_a_close_order_does_not_open_the_named_card(monkeypatch):
    ran = _wire(monkeypatch)
    _run("music", [{"name": "play_music", "args": {"query": "x"}},
                   {"name": "show_widget", "args": {"widget_id": "agenda"}}], "close the calendar and play jazz")
    assert ("show", "agenda") not in ran


def test_the_probe_calls_it():
    import inspect
    from nucleo.flash import probe_after
    assert "probe_companions" in inspect.getsource(probe_after)
