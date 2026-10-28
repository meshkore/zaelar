"""V2-469 · the links the operator PASTED all travel — and the enumeration marks the one playing.

Measured in `build-a-video-playlist-from-links` (23:17): two links pasted in one message, the model called
ONE `add` carrying one of them — «Hecho. Ahora mismo hay: «Rick Astley…»» — and the user had to correct it
(«te pasé dos, ¿no?»), costing two turns. The multi-link add works (V2-384 bis, verified); what failed was
the model's payload. The links are the operator's own words, so completing the payload with the ones his
turn carries invents nothing. Same round, the other half: «¿y qué está sonando ahora?» got the enumeration
WITHOUT marking which one — `named_ack` used labels and dropped the hints ref_index publishes.
"""

from nucleo.flash import widget_data_turn as WDT

_TURN = ("Te paso un par de vídeos: https://www.youtube.com/watch?v=dQw4w9WgXcQ y "
         "https://youtu.be/9bZkp7q19f0 — móntame una lista con ellos.")


# ── the failure rides along even when the model spoke (V2-469, round 11 turn 7) ──────────────────────────
def test_a_spoken_reply_over_a_failed_op_gets_the_failure_appended():
    """«Ahora en pantalla te muestro el siguiente» over widget_data_failed («No hay más vídeos en la
    lista») — the model spoke, so the honest canned failure never replaced anything, and the narration
    lied over a failure the system had in hand."""
    parte = {"executed": "widget_data_failed", "widget": "youtube", "act": "next",
             "message": "No hay más vídeos en la lista."}
    out = WDT.ensure_failure_named("Ahora en pantalla te muestro el siguiente.", parte)
    assert out.startswith("Ahora en pantalla")
    assert "No hay más vídeos" in out


def test_a_successful_op_appends_nothing():
    parte = {"executed": "widget_data", "widget": "youtube", "act": "next"}
    assert WDT.ensure_failure_named("Hecho.", parte) == "Hecho."


def test_a_mute_turn_keeps_the_plain_failure_line():
    parte = {"executed": "widget_data_failed", "widget": "youtube", "act": "next", "message": "no va"}
    assert WDT.ensure_failure_named("", parte) == ""
