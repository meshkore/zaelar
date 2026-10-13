"""The probe's verdict backstop stays out of a turn whose model called a media tool (`show-real-photo-of-a-new-car__es`).

2026-10-14, «enséñamelo igual»: the model called `show_images {query: "Ferrari Amalfi"}`; the backstop — written
for a turn with NO call — added `imagenes:show {items: <his sentence>}`, renamed the turn `widget_data` so the
search never ran, and the viewer refused the sentence. The voice channel's `_no_tool` already counts every one of
these calls; `probe_mirrors.model_already_acted` now counts the same ones.
"""
from nucleo.flash import probe_mirrors as PM


def test_a_media_or_search_call_is_the_turns_act():
    for name in ("show_images", "play_video", "play_music", "web_search", "read_widget"):
        assert PM.model_already_acted([{"name": name, "args": {}}]), name


def test_no_call_or_a_bare_show_still_lets_the_backstop_run():
    assert not PM.model_already_acted([])
    assert not PM.model_already_acted([{"name": "show_widget", "args": {"widget_id": "agenda"}}]), \
        "V2-770: a show over an open card is only canvas — the inner order is the backstop's"
