#
# test_a_blocked_image_index_serves_its_last_answer.py — demo pass 36 (2026-09-29), B1.
#
# Google answered a captcha for a few minutes (the pass and its workers share one search profile); the chain
# fell to Yandex and «the wallpaper cosmic eye in the sky by tyler young» came back as six Pinterest nebulas, none
# of them his. Minutes later Google answered the same query with the right wallpaper first. A captcha is about our
# traffic, not about the pictures: the first index's last good answer for the query is served while it blocks.
#
import asyncio

import pytest

from nucleo import browser_search as bs

_RIGHT = [{"url": f"https://wall.alphacoders.com/{i}.jpg", "title": "Cosmic Eye in the Sky by Tyler Young"}
          for i in range(6)]
_WRONG = [{"url": f"https://i.pinimg.com/{i}.jpg", "title": "Orion nebula"} for i in range(6)]


@pytest.fixture
def chain(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "_IMAGE_CACHE", str(tmp_path / "image_answers.json"))
    state = {"google": {"items": _RIGHT, "source": "google", "blocked": False}}

    async def google(q, k):
        return dict(state["google"])

    async def yandex(q, k):
        return {"items": _WRONG, "source": "yandex", "blocked": False}

    async def bing(q, k):
        return {"items": [], "source": "bing", "blocked": False}

    monkeypatch.setattr(bs, "search_images", google)
    monkeypatch.setattr(bs, "search_images_yandex", yandex)
    monkeypatch.setattr(bs, "search_images_bing", bing)
    return state


def _run(q):
    return asyncio.run(bs.images(q, 6))


def test_while_google_blocks_its_last_answer_is_served(chain):
    assert _run("cosmic eye in the sky Tyler Young Orion Nebula wallpaper")["source"] == "google"
    chain["google"] = {"items": [], "source": "google", "blocked": True}
    res = _run("cosmic eye in the sky wallpaper by Tyler Young, Orion Nebula")
    assert res["items"][0]["url"].startswith("https://wall.alphacoders.com"), res
    assert res["degraded_because"] == "blocked" and "remembered_s" in res


def test_a_query_google_never_answered_still_falls_to_the_next_index(chain):
    chain["google"] = {"items": [], "source": "google", "blocked": True}
    assert _run("red ferrari f40")["source"] == "yandex"


def test_an_empty_google_answer_is_not_served_from_memory(chain):
    """Empty is a fact about the query (rephrase), not a block: the chain moves on as before."""
    _run("red ferrari f40")
    chain["google"] = {"items": [], "source": "google", "blocked": False}
    assert _run("red ferrari f40")["source"] == "yandex"
