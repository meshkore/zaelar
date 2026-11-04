"""A picture the sheet fetches never leaves the public web, and only an image is kept (V2-840 H4, node 7.88).

A row's `url` and a worker's `image` were written by whoever read a page; fetching them is the engine making a
request for a stranger. `search.public_fetch.get` is the bound: public addresses only (every DNS answer), the
connection pinned to the checked address, redirects re-checked hop by hop, a byte cap, a declared type — and
`media.copy_picture` keeps a file only when its BYTES are an image too. The network is `httpx.MockTransport` and a
fake resolver: nothing leaves the machine.
"""
from __future__ import annotations

import httpx
import pytest

from scrape import extract
from search import public_fetch
from search.public_fetch import Refused
from widgets import store
from widgets.results import media

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PUBLIC = "93.184.216.34"


def _resolver(table):
    return lambda host, port: table[host]


def _get(url, handler, table=None, **kw):
    kw.setdefault("accept", ("image/jpeg",))
    kw.setdefault("max_bytes", 10_000)
    return public_fetch.get(url, resolve=_resolver(table or {}), transport=httpx.MockTransport(handler), **kw)


def _never(request):
    raise AssertionError(f"the guard let a request through to {request.url}")


@pytest.mark.parametrize("url,table", [
    ("http://192.168.1.10/cam.jpg", {}),                                   # a private literal
    ("http://127.0.0.1:43917/api/tasks", {}),                              # the engine itself
    ("http://[::1]/x.jpg", {}),
    ("http://169.254.169.254/latest/meta-data/", {}),                      # a cloud metadata service
    ("https://router.home.example/x.jpg", {"router.home.example": ["10.0.0.1"]}),
    ("https://mixed.example/x.jpg", {"mixed.example": [PUBLIC, "172.16.0.9"]}),   # one inside answer is enough
    ("http://[::ffff:127.0.0.1]/x.jpg", {}),                               # loopback dressed as IPv6
    ("file:///etc/passwd", {}),
])
def test_a_non_public_target_is_refused_before_any_request(url, table):
    with pytest.raises(Refused) as e:
        _get(url, _never, table)
    assert e.value.reason in ("non_public_address", "scheme")


def test_the_connection_goes_to_the_address_that_was_checked():
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers["host"], request.extensions.get("sni_hostname")))
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)
    got = _get("https://cdn.shop.example/a.jpg", handler, {"cdn.shop.example": [PUBLIC]})
    assert got.body == JPEG
    assert seen == [(PUBLIC, "cdn.shop.example", "cdn.shop.example")]


def test_a_redirect_into_the_network_is_refused():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://internal.example/admin"})
    with pytest.raises(Refused) as e:
        _get("https://cdn.shop.example/a.jpg", handler,
             {"cdn.shop.example": [PUBLIC], "internal.example": ["10.1.2.3"]})
    assert e.value.reason == "non_public_address"


def test_a_public_redirect_is_followed_and_a_loop_is_cut():
    hops = []

    def handler(request):
        hops.append(str(request.url))
        if request.headers["host"] == "a.example":
            return httpx.Response(301, headers={"location": "https://b.example/pic.jpg"})
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)
    got = _get("https://a.example/pic.jpg", handler, {"a.example": [PUBLIC], "b.example": ["93.184.216.35"]})
    assert got.url == "https://b.example/pic.jpg" and len(hops) == 2
    with pytest.raises(Refused) as e:
        _get("https://a.example/x", lambda r: httpx.Response(302, headers={"location": "/x"}), {"a.example": [PUBLIC]})
    assert e.value.reason == "too_many_redirects"


@pytest.mark.parametrize("ctype", ["text/html", "application/octet-stream", "application/json"])
def test_a_body_that_is_not_declared_an_image_is_refused(ctype):
    def handler(request):
        return httpx.Response(200, headers={"content-type": ctype}, content=b"<html></html>")
    with pytest.raises(Refused) as e:
        _get("https://cdn.shop.example/a", handler, {"cdn.shop.example": [PUBLIC]}, accept=("image/",))
    assert e.value.reason == "content_type"


@pytest.mark.parametrize("declared", [True, False])
def test_a_body_past_the_cap_is_cut_not_kept(declared):
    """Refused on the declared length, and on the stream when the server declares none."""
    def handler(request):
        body = JPEG * 400
        if declared:
            return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=body)
        return httpx.Response(200, headers={"content-type": "image/jpeg"},
                              stream=_chunks(body))
    with pytest.raises(Refused) as e:
        _get("https://cdn.shop.example/a.jpg", handler, {"cdn.shop.example": [PUBLIC]}, max_bytes=1000)
    assert e.value.reason == "too_large"


class _chunks(httpx.SyncByteStream):
    def __init__(self, body):
        self.body = body

    def __iter__(self):
        for i in range(0, len(self.body), 256):
            yield self.body[i:i + 256]


@pytest.mark.parametrize("ctype,body", [("image/jpeg", b"<html>not a picture</html>"),
                                        ("image/svg+xml", b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>')])
def test_a_file_labelled_image_whose_bytes_are_not_one_is_not_kept(monkeypatch, tmp_path, ctype, body):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    def get(url, **kw):
        return public_fetch.Fetched(url=url, content_type=ctype, body=body)
    with pytest.raises(Refused) as e:
        media.copy_picture("https://cdn.shop.example/fake.jpg", get)
    assert e.value.reason == "not_an_image"
    assert not [n for n in (tmp_path / "results").iterdir() if n.name.startswith("pic-")]


@pytest.mark.parametrize("html,cover", [
    ('<meta property="og:image" content="/img/xc60.jpg">', "https://www.autoscout24.es/img/xc60.jpg"),
    ('<meta content="https://cdn.example/flat.png" name="twitter:image">', "https://cdn.example/flat.png"),
    ('<script type="application/ld+json">{"@type":"Product","name":"Stratocaster","image":"https://i.example/s.jpg",'
     '"offers":{"price":"900","priceCurrency":"EUR"}}</script>', "https://i.example/s.jpg"),
    ("<title>nothing declared</title>", ""),
    ('<meta name="twitter:image" content="https://t.example/card.jpg"><meta property="og:image:alt" content="a red car">'
     '<meta property="og:image" content="http://o.example/a.jpg"><meta property="og:image:secure_url" '
     'content="https://o.example/a.jpg"><meta property="og:image:width" content="1200">', "https://o.example/a.jpg"),
])
def test_the_cover_is_the_one_the_page_declares(html, cover):
    assert extract.declared_cover(html, "https://www.autoscout24.es/anuncios/volvo") == cover
