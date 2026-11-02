"""Every row brings its picture (V2-840 H4, node 7.87).

A car search delivered three AutoScout24 ads with a `url` and no `image`: the sheet drew monograms, in the list and
in the record. The door now reads the cover each page declares (`og:image`), copies it into the results widget's own
folder and points the row at the engine's asset route — after the push, never in it — and counts the rows that are
still without one. Through the REAL `present`/`append`; only the network is a double (`get`), so no test leaves the
machine. Variants: a car ad (ES), a flat (EN), a guitar, a worker-supplied remote picture, a tariff that must stay
without a photo, a page that declares nothing.
"""
from __future__ import annotations

import os

import pytest

from search.public_fetch import Fetched, Refused
from widgets import store
from widgets.results import data as sheet, media

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

PAGES = {
    "https://www.autoscout24.es/anuncios/volvo-xc60-d4": "https://prod.pictures.autoscout24.net/listing/xc60.jpg",
    "https://www.rightmove.co.uk/properties/1234": "https://media.rightmove.co.uk/flat-1234.png",
    "https://reverb.com/item/5678-fender-stratocaster": "https://images.reverb.com/strat.jpg",
}


class Net:
    """The open web, as a dict: a page declares its cover with og:image; the cover is a real image file."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, url, *, accept, max_bytes, truncate=False):
        self.calls.append(url)
        if url in PAGES:
            html = f'<html><head><meta property="og:image" content="{PAGES[url]}"></head><body></body></html>'
            return Fetched(url=url, content_type="text/html", body=html.encode())
        if url.endswith(".jpg"):
            return Fetched(url=url, content_type="image/jpeg", body=JPEG)
        if url.endswith(".png"):
            return Fetched(url=url, content_type="image/png", body=PNG)
        if "no-cover" in url:
            return Fetched(url=url, content_type="text/html", body=b"<html><head><title>x</title></head></html>")
        raise Refused("http_404")


@pytest.fixture
def rig(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    media._memo.clear()
    media._inflight.clear()
    net, queued, events = Net(), [], []
    real_fill = media.fill
    monkeypatch.setattr(media, "fill", lambda s, d, **k: real_fill(s, d, get=net, spawn=queued.append))
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda fam, name, **k: events.append((fam, name, k.get("extra") or {})))
    yield net, queued, events, tmp_path


def _run(queued):
    while queued:
        queued.pop(0)()


def _door(events):
    return [e for (f, n, e) in events if (f, n) == ("widget", "door")][-1]


def _media(events):
    return [e for (f, n, e) in events if (f, n) == ("widget", "media")][-1]


@pytest.mark.parametrize("title,url", [
    ("Volvo XC60 D4 Business Plus Aut.", "https://www.autoscout24.es/anuncios/volvo-xc60-d4"),
    ("2-bed flat, Islington", "https://www.rightmove.co.uk/properties/1234"),
    ("Fender Stratocaster 1998", "https://reverb.com/item/5678-fender-stratocaster"),
])
def test_a_row_with_a_page_and_no_picture_gets_the_cover_that_page_declares(rig, title, url):
    net, queued, events, folder = rig
    res = sheet.apply_action("present", {"sheet": "s1", "kind": "product", "items": [
        {"title": title, "price": "1.000 €", "url": url}]})
    assert res["ok"]
    # the push is not held for the picture: the row is there, still without it, and the fetch is queued
    assert "image" not in sheet.view_data("s1")["items"][0]
    assert _door(events)["no_picture"] == 1 and _door(events)["picture_queued"] == 1
    _run(queued)
    img = sheet.view_data("s1")["items"][0].get("image") or ""
    assert img.startswith("/widgets/results/asset/pic-"), img
    assert os.path.isfile(os.path.join(store.data_dir("results"), img.rsplit("/", 1)[1]))
    assert net.calls == [url, PAGES[url]]
    m = _media(events)
    assert m["covers"] == 1 and m["no_picture"] == 0
    assert ("widget", "data") in [(f, n) for (f, n, _e) in events]       # the card repaints with its picture


def test_rows_on_the_same_page_fetch_it_once_and_a_second_push_does_not_fetch_again(rig):
    net, queued, events, _ = rig
    url = "https://www.autoscout24.es/anuncios/volvo-xc60-d4"
    sheet.apply_action("present", {"sheet": "s2", "items": [{"title": "XC60 white", "url": url},
                                                             {"title": "XC60 black", "url": url}]})
    _run(queued)
    assert net.calls.count(url) == 1
    assert all(i.get("image", "").startswith(media.LOCAL) for i in sheet.view_data("s2")["items"])
    sheet.apply_action("append", {"sheet": "s2", "items": [{"title": "XC60 grey", "url": url}]})
    _run(queued)
    assert net.calls.count(url) == 1                     # resolved once in this process: the memo answers
    assert sheet.view_data("s2")["items"][2]["image"].startswith(media.LOCAL)


def test_a_worker_supplied_picture_is_copied_and_served_by_the_engine(rig):
    net, queued, events, _ = rig
    remote = "http://cdn.example-shop.com/strat.jpg"           # http inside the engine's page: mixed content
    sheet.apply_action("present", {"sheet": "s3", "items": [
        {"title": "Fender Stratocaster", "url": "https://shop.example/strat", "image": remote,
         "images": [remote, "https://cdn.example-shop.com/back.png"]}]})
    _run(queued)
    it = sheet.view_data("s3")["items"][0]
    assert it["image"].startswith(media.LOCAL) and all(u.startswith(media.LOCAL) for u in it["images"])
    assert "https://shop.example/strat" not in net.calls       # it HAD a picture: its page is not read
    assert net.calls.count(remote) == 1                        # the same picture in both slots, downloaded once


def test_a_tariff_and_a_link_keep_their_template_without_a_photo(rig):
    net, queued, events, _ = rig
    sheet.apply_action("present", {"sheet": "s4", "items": [
        {"title": "Fibra 600 Mb", "price": "30 €/mes", "url": "https://www.autoscout24.es/anuncios/volvo-xc60-d4",
         "kind": "offer"},
        {"title": "Guía de compra", "url": "https://reverb.com/item/5678-fender-stratocaster", "kind": "link"}]})
    _run(queued)
    assert net.calls == []
    assert all("image" not in i for i in sheet.view_data("s4")["items"])
    assert "no_picture" not in _door(events)                   # they are not a gap: they draw no plate


def test_a_page_that_declares_nothing_or_fails_leaves_the_row_and_says_why(rig):
    net, queued, events, _ = rig
    sheet.apply_action("present", {"sheet": "s5", "items": [
        {"title": "Piano Yamaha U3", "url": "https://pianos.example/no-cover"},
        {"title": "Piano Kawai K300", "url": "https://pianos.example/gone"}]})
    _run(queued)
    assert all("image" not in i for i in sheet.view_data("s5")["items"])
    m = _media(events)
    assert m["failed"] == {"no_cover": 1, "http_404": 1} and m["no_picture"] == 2


def test_the_door_event_counts_the_gap_with_the_network_off(monkeypatch, tmp_path):
    """The count does not depend on the fetch: with nothing fetched (the suite's default) the gap is still said."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    events = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda fam, name, **k: events.append((fam, name, k.get("extra") or {})))
    sheet.apply_action("present", {"sheet": "s6", "items": [
        {"title": "Lagoon 440", "url": "https://boats.example/1"},
        {"title": "Lagoon 450", "url": "https://boats.example/2", "image": media.LOCAL + "pic-x.jpg"}]})
    door = _door(events)
    assert door["no_picture"] == 1 and "picture_queued" not in door


def test_a_page_already_being_fetched_is_not_queued_again_by_the_next_push(rig):
    net, queued, events, _ = rig
    url = "https://reverb.com/item/5678-fender-stratocaster"
    sheet.apply_action("present", {"sheet": "s7", "items": [{"title": "Strat sunburst", "url": url}]})
    sheet.apply_action("append", {"sheet": "s7", "items": [{"title": "Strat olympic white", "url": url}]})
    assert _door(events).get("picture_queued", 0) == 0          # the first push's fetch is still on its way
    _run(queued)
    assert net.calls.count(url) == 1
    assert all(i.get("image", "").startswith(media.LOCAL) for i in sheet.view_data("s7")["items"])


def test_the_picture_folder_keeps_only_the_newest(rig, monkeypatch):
    net, queued, events, _ = rig
    monkeypatch.setattr(media, "_MAX_FILES", 2)
    for n in range(4):
        media.copy_picture(f"https://images.reverb.com/strat-{n}.jpg", net)
    pics = [p for p in os.listdir(store.data_dir("results")) if p.startswith("pic-")]
    assert len(pics) == 2
