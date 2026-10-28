"""An address that belongs to a contact he named is HIS recipient, on every door (demo pass 141, E3, 2026-10-19).

«send the invoice to quinn, tell him we're already trying inworld» — the model wrote the forward with the ADDRESS in
`contact`. The repair's check and the stranger's-text check matched it literally against his words, so the call was
dropped and then turned into a question, while the same send with «Quinn» in the field went out (p139, p140). One
reading now — `leave_gate.is_his` — and the three doors ask it. The note the repair writes is in the SESSION's
language by name: «the OPERATOR's language» let it read the Spanish manifest and write Spanish in an English session.
"""
import inspect
import re

import pytest

from nucleo.acts import message as leave_gate
from nucleo.flash import act_repair, repair_grounding

BOOK = {"quinn@example.com": [{"name": "Quinn", "email": "quinn@example.com"}],
        "rowan@example.com": [{"name": "Rowan Ferrer", "email": "rowan@example.com"}]}
STRANGER = "billing@inworld.example"


@pytest.fixture(autouse=True)
def _directory(monkeypatch):
    from widgets import directory
    monkeypatch.setattr(directory, "resolve", lambda q: BOOK.get(str(q).strip().lower(), []))


def _doors(recipient: str, said: str) -> tuple[bool, bool, bool]:
    pl = {"contact": recipient, "from": "Inworld AI", "text": "…"}
    return (repair_grounding.recipient_was_named("mensajeria", "forward", pl, said, None),
            leave_gate._named_by_him(pl, said),
            leave_gate.unnamed_recipients("mensajeria", "forward", pl, said) == [])


def test_the_address_of_the_contact_he_named_passes_every_door():
    assert _doors("quinn@example.com", "send the invoice to quinn, tell him we're already trying inworld") == \
        (True, True, True)


def test_the_same_in_spanish_with_a_two_word_name():
    assert _doors("rowan@example.com", "reenvíale la factura a Rowan y dile que ya lo estamos probando") == \
        (True, True, True)


def test_an_address_he_never_named_is_stopped_by_every_door():
    assert _doors(STRANGER, "send the invoice to quinn") == (False, False, False)


def test_every_payload_writing_pass_names_the_session_language(monkeypatch):
    monkeypatch.setattr(repair_grounding, "session_lang", lambda: "English")
    src = inspect.getsource(act_repair)
    vague = [n for n, v in vars(act_repair).items()
             if n.startswith("_SYS") and isinstance(v, str) and "OPERATOR's language" in v]
    assert vague, "the templates moved — re-measure"
    for name in vague:
        # formatted where it is written (alone or with a line appended), or handed on as `_sys=` to the one
        # site that formats `_sys or …`
        lines = [ln for ln in src.splitlines() if re.search(rf"\b{name}\b(\)?\.format\(|\.replace\(| \+ [^()]*\([^()]*\)\)\.format\()", ln)
                 or re.search(rf"\b_sys or {name}\b", ln)]
        lines = [ln if "_sys=" not in ln else next(x for x in src.splitlines() if "(_sys or " in x) for ln in lines]
        assert lines and all("_in_his_lang(" in ln for ln in lines), f"{name} is formatted unnamed: {lines}"
        assert "OPERATOR's language (English)" in act_repair._in_his_lang(getattr(act_repair, name))
