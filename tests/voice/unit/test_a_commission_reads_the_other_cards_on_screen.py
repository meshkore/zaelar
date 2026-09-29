"""Demo pass 43 (2026-09-29), C5: «send ethan a telegram with the new time». The meeting had just been moved to 4:30
on the open agenda — silently, so no words in the window said so — the model escalated with «17:00», and the
commission pass, which saw only the messaging card and that brief, wrote Ethan «moved to 5:00 PM». The time was on
his screen, in another card; the pass is now shown the other open cards too."""
import asyncio

import pytest

from nucleo.flash import act_repair

_AGENDA = "· 2026-09-30 16:30 «Catch up with Ethan»–17:15"


@pytest.fixture
def seen(monkeypatch):
    from memory import api as memapi
    from nucleo.flash import widget_read
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": ["results::x-1", "agenda", "mensajeria"]})
    monkeypatch.setattr(widget_read, "read", lambda wid: {"agenda": _AGENDA, "mensajeria": "BANDEJA: 3"}.get(wid, ""))
    monkeypatch.setattr(widget_read, "can_answer", lambda wid: wid in ("agenda", "mensajeria"))
    got = []

    class _M:
        async def complete(self, messages, **kw):
            got.append(messages)
    import nucleo.flash.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", _M)
    return got


def test_the_commission_pass_sees_the_agenda_on_screen(seen):
    asyncio.run(act_repair.call_or_read_for_commission(
        "send ethan a telegram with the new time", "Tell Ethan the catch-up moved to 17:00", "mensajeria"))
    system = seen[0][0]["content"]
    assert "16:30 «Catch up with Ethan»" in system, "the time on his screen never reached the pass"
    # live against the model, the digest alone was not enough (0/3): the brief's «17:00» won. Told which source
    # wins, 3/4 wrote 4:30 and the fourth called nothing (the errand keeps its path).
    assert "se toma de la TARJETA, no del encargo" in system
    # full46 C5: with the agenda already at 4:30 and «move it half an hour later» in the window, 2/3 wrote 5:00 —
    # the move applied twice. Told the card is the state AFTER his changes: 4/5 wrote 4:30.
    assert "YA APLICADOS" in system


def test_the_card_being_commissioned_is_not_repeated(seen):
    asyncio.run(act_repair.call_or_read_for_commission("send ethan a telegram", "x", "mensajeria"))
    assert seen[0][0]["content"].count("BANDEJA: 3") == 1
