"""A `canvas:show:<card>` that CARRIES the model's own media request is not a bare show of the card.

Measured in `show-real-photo-of-a-new-car__us` (2026-10-11, turn 2): «I don't see any photo — send the actual
pic.» The model called `show_images {query: "Ferrari Amalfi"}`; the text channel named the turn
`canvas:show:imagenes` and parked the search in `images_req`, to run it after the stream. The verdict read
`screen_action = imagenes:show` (0.59) — and the V2-770 repair («a show of a card that is already open, on a turn
whose verdict names an action INSIDE it, is not the act») demoted the action to `chat`, because the verdict's
action lived inside the card the show named. The search never ran, nothing was said, and the mute backstop
answered «Sorry, I lost that. Could you say it again?» to a request he had made three times.

The V2-770 repair is right about `show_widget(agenda)` over an open agenda: that show is only canvas, and the
inner action is the order. It is wrong about `show_images` and `play_video`: for them the `canvas:show:` action
IS the execution — the viewer's `show` is what `show_images` fills (`card_commission.TOOL_FILLED`), the player's
`load` is what `play_video` performs. Demoting one of these to `chat` does not hand the order to a repair; it
drops it. This predicate names the difference by what the MODEL CALLED, never by his words.
"""
from __future__ import annotations

#: The media tools whose `canvas:show:<card>` action is the execution itself, and the card each one fills.
TOOL_SHOWS = {"show_images": "imagenes", "play_video": "youtube"}


def carries_media_request(action: str, names) -> bool:
    """Is this `canvas:show:<card>` the one a media tool the model called will fill? Then it is the act, not a
    canvas gesture, and no repair may demote it."""
    a = str(action or "")
    if not a.startswith("canvas:show:"):
        return False
    card = a.split(":", 2)[2].split("::", 1)[0].strip().lower()
    return any(TOOL_SHOWS.get(str(n or "")) == card for n in (names or []))
