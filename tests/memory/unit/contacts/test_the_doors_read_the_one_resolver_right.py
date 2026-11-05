"""V2-854 · the two doors around the resolver read it right once it ranks by margin and filters by the act.

  · the send door hands the CHANNEL it sends by to the resolver (`platform=`), so the act filters the candidates first
    — and stays callable on a resolver that does not take it;
  · «did he name this recipient» (`acts.message.is_his`): with winners by margin a single word of his («Pablo») can
    lead to his favorite «Pablo FF» while his words named somebody else WHOLE («Pablo Hernandez») — then he did not
    name the favorite, and the send asks.

The resolver is stubbed: these are the doors' contracts, independent of how it ranks.
"""
from __future__ import annotations

import pytest

FF = {"id": "c-ff", "name": "Pablo FF", "kind": "person", "favorite": True, "channels": []}
HERNANDEZ = {"id": "c-h", "name": "Pablo Hernandez", "kind": "person", "channels": []}


def _fold(s) -> str:
    return " ".join(str(s or "").lower().split())


@pytest.fixture
def margin_resolver(monkeypatch):
    """A resolver with winners by margin: «pablo» alone is his favorite, «pablo hernandez» is that one person."""
    from widgets import directory
    book = {"pablo": [FF], "pablo ff": [FF], "pablo hernandez": [HERNANDEZ], "hernandez": [HERNANDEZ]}

    def resolve(name, *, tolerant=True, platform=""):
        return list(book.get(_fold(name), []))
    monkeypatch.setattr(directory, "resolve", resolve)
    return directory


def test_his_words_naming_someone_else_whole_do_not_name_the_favorite(margin_resolver):
    from nucleo.acts import message
    said = ["pregúntale a Pablo Hernandez si ha probado Zaelar"]
    assert message.is_his("Pablo Hernandez", said) is True
    assert message.is_his("Pablo FF", said) is False


@pytest.mark.parametrize("said", ["pregúntale a Pablo si ha probado Zaelar", "ask pablo if he tried zaelar"])
def test_his_one_word_still_names_the_favorite(margin_resolver, said):
    from nucleo.acts import message
    assert message.is_his("Pablo FF", [said]) is True


def test_the_send_door_hands_its_channel_to_the_resolver(monkeypatch):
    from widgets import directory
    from widgets.mensajeria.outbound import targets
    seen = []

    def resolve(name, *, tolerant=True, platform=""):
        seen.append(platform)
        return [dict(HERNANDEZ, email="ph@example.com")]
    monkeypatch.setattr(directory, "resolve", resolve)
    t = targets.resolve_target({"contact": "Pablo Hernandez", "channel": "email", "text": "hola"})
    assert t.get("ok") and seen and seen[0] == "email", (t, seen)


def test_the_send_door_still_works_on_a_resolver_without_a_channel(monkeypatch):
    from widgets import directory
    from widgets.mensajeria.outbound import targets

    def resolve(name, *, tolerant=True):                    # the base signature
        return [dict(HERNANDEZ, email="ph@example.com")]
    monkeypatch.setattr(directory, "resolve", resolve)
    t = targets.resolve_target({"contact": "Pablo Hernandez", "channel": "email", "text": "hola"})
    assert t.get("ok") and t.get("contactId") == "c-h", t
