"""V2-582 — the connector-state line the brain reads every turn tells the truth in words, and it OUTRANKS
the conversation.

Measured in the operator's live session (e32b00f1, 2026-09-05): with «Email: error.» in the prompt the model
answered «lo tengo conectado y funcionando», and after the operator connected it mid-dialogue — the line now
saying «Email: conectado.» — the model kept answering «no me ha quedado conectado», anchored on its own
earlier sentences. Two mechanism halves close what mechanism can close:

  · "error" is no longer a bare raw status (neither connected nor not): it says NO conectado, in words.
  · the block declares that it is THIS turn's live state and wins over anything said earlier in the
    conversation — including the model's own claims (V2-221: without the phrase inside, the model has
    nothing to check itself against).

The model still deciding to contradict the line is conduct and gets measured by the use-case platform; this
file pins the information side, which was the half we owed.
"""
from __future__ import annotations

from unittest.mock import patch


def _states_with_email(status: str) -> str:
    from connectors.messaging import brief

    fake_store = {"platforms": {"whatsapp": {"status": "connected"},
                                "telegram": {"status": "connected"},
                                "email": {"status": status}}}
    with patch("connectors.whatsapp.service.enabled", return_value=True), \
         patch("connectors.telegram.service.enabled", return_value=True), \
         patch("connectors.email.service.enabled", return_value=True), \
         patch("connectors.messaging.store.load", return_value=fake_store):
        return brief._platform_states()


def test_an_errored_connector_says_NO_conectado_in_words():
    line = _states_with_email("error")
    assert "Email: NO conectado" in line, line
    # The bare raw status is what let the model read "error" as "connected but grumpy".
    assert "Email: error." not in line, line


def test_a_connected_connector_still_says_conectado():
    line = _states_with_email("connected")
    assert "Email: conectado." in line, line


def test_the_block_declares_it_outranks_the_conversation():
    """The load-bearing words: live state of THIS turn, wins over the window, names the model's own prior
    claims as the thing not to repeat. Phrased as substrings of the shipped Spanish prompt text."""
    line = _states_with_email("connected")
    assert "EN VIVO" in line, line
    assert "MANDA sobre la conversación anterior" in line, line
    assert "TUS propias frases" in line, line


# ── What HE sees vs what the brain holds (V2-607) ───────────────────────────
def test_the_brief_says_which_chats_are_not_in_his_summary(monkeypatch, tmp_path):
    """The brain's list and his first tab stopped being the same list, and two surfaces over one dataset that
    disagree is exactly how V2-606 happened: a «connected» flag plus an empty card produced «no tienes correos
    sin leer» over 1088 of them. So the split is stated, the count is stated, and the forbidden sentence is named.
    """
    from connectors.messaging import brief

    chats = [{"n": 1, "platform": "whatsapp", "name": "Mercè", "highlight": True, "count": 1,
              "dirigido_a_mi": True, "urgencia": "alta", "lastBody": "urgent"},
             {"n": 2, "platform": "email", "name": "Lowi", "highlight": False, "count": 3,
              "dirigido_a_mi": False, "urgencia": "media", "lastBody": "factura"}]
    out = brief._summary_split(chats)
    assert "1 conversación(es) más" in out and "3 mensaje(s)" in out, out
    assert "JAMÁS digas que no tiene nada" in out, "the sentence it must not say has to be named"
    assert "set_notify" in out, "and the door for «avísame» has to be in reach"


def test_with_everything_addressed_to_him_it_still_says_nobody_interrupts(monkeypatch):
    """The other branch. Silence by default is only safe if the model KNOWS it is the default — otherwise it
    promises to warn him, or apologises for not having warned him, and both are inventions."""
    from connectors.messaging import brief

    out = brief._summary_split([{"n": 1, "platform": "email", "name": "Ana", "highlight": True, "count": 1}])
    assert "NINGÚN canal te interrumpe" in out and "set_notify" in out, out
    assert "conversación(es) más" not in out, "there is no remainder to announce"


# ── V2-686: a brief may claim its OWN family and no more ───────────────────────────────────────────────

def test_the_brief_claims_messaging_channels_and_not_every_connector():
    """Measured live on 2026-09-14, engine 3.26+e35211f8. This line used to read «si quiere conectar/ver UNA
    APP, emite [[show:mensajeria]] … Guíale tú también de palabra ('te abro Mensajería, ahí tienes los
    pasos')» — a blanket claim over every connection ceremony in the product, with the reply pre-written.
    Asked «open the google connector», the model opened Messaging and answered «I'm opening the Messaging
    widget — the Google connector is right there with the login steps»: this line, obeyed exactly, while the
    calendar's connector lives in the AGENDA and Drive's in ARCHIVOS.

    It was true when messaging was the only connector with a wizard. What makes it a defect is that the
    engine grew five more and nobody came back to narrow the sentence — so the guard is on the SCOPE, not on
    the wording."""
    low = _states_with_email("connected").lower()
    assert "mensajería" in low or "mensajeria" in low
    # It has to say WHICH channels it is talking about, instead of «una app».
    for channel in ("whatsapp", "telegram", "correo"):
        assert channel in low, f"the claim does not name {channel}, so it reads as every connector"
    assert "conectar/ver una app" not in low, "the blanket claim is back"


def test_the_brief_points_the_other_families_at_their_own_widgets():
    """The counterweight, and the half that actually redirects: saying «not me» without saying «them» leaves
    the model exactly where it was. `connectors/google/brain.py` names each door's surface; this line only
    has to stop swallowing them."""
    low = _states_with_email("connected").lower()
    assert "desde su widget" in low or "su propio widget" in low
    for other in ("calendario", "archivos", "fotos"):
        assert other in low, other
