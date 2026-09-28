"""A person the operator names reaches the turn that has to write to them (demo pass 2026-09-28, full14 E3).

«send the invoice to andrew, tell him we're already trying inworld» was answered «I don't see an Andrew in your
contacts» with Andrew saved: the directory reaches the prompt only as the open card's first rows (~2,700 people),
so a person named by first name was invisible. The rows his sentence names now ride that turn's prompt — the
public row only (platforms, never handles)."""
import pytest


@pytest.fixture
def cd(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data
    data.apply_action("add_contact", {"name": "Andrew", "email": "andrew@example.com", "preferred": "email"})
    data.apply_action("add_contact", {"name": "Josep Solá Fabá", "email": "j@example.com"})
    data.apply_action("add_contact", {"name": "Al", "email": "al@example.com"})
    return data


def test_a_first_name_in_the_order_finds_the_row_with_its_channels(cd):
    rows = cd.people_named("send the invoice to andrew, tell him we're already trying inworld")
    assert [(r["name"], r.get("channels")) for r in rows] == [("Andrew", ["email"])]
    assert "andrew@example.com" not in str(rows), "the address never rides a prompt"


def test_a_whole_name_wins_and_a_word_is_not_a_person(cd):
    assert [r["name"] for r in cd.people_named("write to Josep Solá Fabá")] == ["Josep Solá Fabá"]
    assert cd.people_named("play some madonna, al fresco") == []


def test_the_turn_prompt_carries_them():
    from nucleo.flash import prompt
    import inspect
    src = inspect.getsource(prompt.build_flash_system)
    assert "_people_block(turn_text)" in src
