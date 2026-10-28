"""With only the mail connected, the voice turn still offers the messaging tools (bank case msg-es-email-new).

`turn_tools` read «messaging is on» from WhatsApp and Telegram only, so an install whose one messaging connector was
the mail answered «no tengo conector de correo» to «mándale un correo a…». Every messaging connector counts; none
readable fails open. Disarm: drop "email" from `turn_tools.messaging_on` → the first test is red.
"""
from connectors.email import service as email
from connectors.telegram import service as telegram
from connectors.whatsapp import service as whatsapp
from voice.engine.llm.providers import turn_tools


def _only(monkeypatch, **on):
    for mod, name in ((whatsapp, "whatsapp"), (telegram, "telegram"), (email, "email")):
        monkeypatch.setattr(mod, "enabled", lambda n=name: on.get(n, False))


def test_the_mail_alone_turns_messaging_on(monkeypatch):
    _only(monkeypatch, email=True)
    assert turn_tools.messaging_on()


def test_no_connector_on_is_no_messaging(monkeypatch):
    _only(monkeypatch)
    assert not turn_tools.messaging_on()
