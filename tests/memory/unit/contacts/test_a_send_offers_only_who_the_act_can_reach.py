"""V2-854 F0 · the send door names only people the ACT can reach, and his pick is learned once.

Asked through the messaging card's own resolution (`widgets/mensajeria/outbound/targets.resolve_target`, what
`send_to` and `create_group` both go through) on the synthetic directory. The act filters BEFORE the ranking: a mail
never offers a phone-only contact, a WhatsApp never offers an e-mail-only one, and a person with no phone, no e-mail
and no channel (unclassified) is never offered for a send at all. Strict xfails name the phase that turns them green.
"""
from __future__ import annotations

import pytest

F2 = lambda f: f   # V2-854 F2 landed: the baseline reds are green, the marker stays as the record


def _target(contact: str, channel: str = "") -> dict:
    from widgets.mensajeria.outbound import targets
    return targets.resolve_target({"contact": contact, "channel": channel, "text": "hola"})


def _by_name(rows):
    return {r["name"]: r for r in rows}


def _offered(t: dict, rows) -> list[dict]:
    """The people this answer puts in front of him: the one it writes to, or the ones it asks about."""
    by_id = {r["id"]: r for r in rows}
    names = _by_name(rows)
    if t.get("ok"):
        return [by_id[t["contactId"]]] if t.get("contactId") in by_id else []
    return [names[n] for n in (t.get("candidates") or t.get("near") or []) if n in names]


def _reaches(r: dict, channel: str) -> bool:
    if channel == "email":
        return bool(r.get("email"))
    return bool(r.get("phone")) or any(ch.get("platform") == channel for ch in r.get("channels") or [])


# ── the act filters first ────────────────────────────────────────────────────────────────────────────────────────

@F2
@pytest.mark.parametrize("said,who", [("Lucía", "lucia-mail"), ("lucia", "lucia-mail"), ("Megan", "megan-mail")],
                         ids=["es-typed", "es-voice", "en"])
def test_a_mail_goes_to_the_only_namesake_with_an_address(directory_world, said, who):
    _cd, _d, _rows = directory_world
    t = _target(said, "email")
    assert t.get("ok") and t.get("contactId") == who, t


@F2
@pytest.mark.parametrize("said", ["Raquel", "raquel", "John", "Catherine"])
def test_a_mail_never_offers_a_phone_only_contact(directory_world, said):
    _cd, _d, rows = directory_world
    t = _target(said, "email")
    offered = _offered(t, rows)
    assert offered and all(_reaches(r, "email") for r in offered), (t.get("say"), [r["name"] for r in offered])


@F2
@pytest.mark.parametrize("said", ["Jordi", "jordi", "John", "Megan"])
def test_a_whatsapp_never_offers_an_e_mail_only_contact(directory_world, said):
    _cd, _d, rows = directory_world
    t = _target(said, "whatsapp")
    offered = _offered(t, rows)
    assert offered and all(_reaches(r, "whatsapp") for r in offered), (t.get("say"), [r["name"] for r in offered])


@F2
@pytest.mark.parametrize("said,who,channel", [("Tomeu", "tomeu-tel", "whatsapp"), ("tomeu", "tomeu-tel", ""),
                                              ("Noel", "noel-tel", "whatsapp"), ("noel", "noel-tel", "")],
                         ids=["es-whatsapp", "es-any", "en-whatsapp", "en-any"])
def test_an_unclassified_namesake_is_never_offered_for_a_send(directory_world, said, who, channel):
    _cd, _d, rows = directory_world
    from widgets.contactos import data as cd
    if not channel:                     # «by any channel»: give the reachable one a chat so a channel is decidable
        cd.apply_action("set_channel", {"contactId": who, "platform": "whatsapp", "handle": "+44 7700 900999"})
    t = _target(said, channel)
    assert t.get("ok") and t.get("contactId") == who, t


@pytest.mark.parametrize("said", ["Tomeu Bauzà", "noel quill"])
def test_an_unclassified_person_named_in_full_is_a_missing_fact_never_a_send(directory_world, said):
    t = _target(said, "whatsapp")
    assert t.get("ok") is False and t.get("say") == "widgets.mensajeria.refusal_no_channel", t


# ── his favorite, by the channel she really has ──────────────────────────────────────────────────────────────────

@F2
@pytest.mark.parametrize("said,who,channel,chat", [
    ("Raquel", "fav-rakel", "whatsapp", "900000000000001@lid"), ("raquel", "fav-rakel", "whatsapp", "900000000000001@lid"),
    ("Catherine", "fav-katherine", "telegram", "khale_fx")], ids=["es-typed", "es-voice", "en"])
def test_a_message_to_his_favorites_first_name_goes_to_her_with_no_question(directory_world, said, who, channel, chat):
    t = _target(said, channel)
    assert t.get("ok") and t.get("contactId") == who and t.get("chatId") == chat, t


@pytest.mark.parametrize("said", ["Pádel domingos", "padel domingos"], ids=["typed", "voice"])
def test_a_whatsapp_group_he_has_is_one_recipient(directory_world, said):
    t = _target(said)
    assert t.get("ok") and t.get("contactId") == "group-padel" and t.get("chatId", "").endswith("@g.us"), t


# ── his pick, learned once ───────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said,pick,again", [("Pablo", "Pablo Elastic", "pablo"), ("pablo", "Pablo Elastic", "Pablo"),
                                             ("Owen", "Owen Stroud", "owen")],
                         ids=["es-typed-then-voice", "es-voice-then-typed", "en"])
def test_his_pick_among_namesakes_is_learned_once(directory_world, said, pick, again):
    _cd, d, _rows = directory_world
    from widgets.mensajeria import data as ms
    first = ms.apply_action("send_to", {"contact": said, "channel": "whatsapp", "text": "¿vienes el sábado?"})
    assert first["ok"] is False and pick in (first.get("candidates") or []), first
    chosen = ms.apply_action("send_to", {"contact": pick, "channel": "whatsapp", "text": "¿vienes el sábado?"})
    assert chosen["ok"] is True and (chosen["result"].get("learned") or {}).get("alias"), chosen
    later = ms.apply_action("send_to", {"contact": again, "channel": "whatsapp", "text": "¿y el domingo?"})
    assert later["ok"] is True and later["result"]["to"] == pick and "learned" not in later["result"], later
