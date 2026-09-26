"""«Show me the section explaining why the colonies wanted independence» over the Declaration on screen (demo run,
2026-09-26): the reply described the passage and the sheet never moved — the document card had no way to. `goto`
finds the heading or passage (exact phrase first, then the most query words, a heading winning a tie), sets it as
the focus, and the RENDERED card scrolls to it and marks it; a passage nobody can find offers the headings."""
import asyncio
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
BODY = """# The Declaration of Independence
## Preamble
When in the Course of human events, it becomes necessary for one people to dissolve the political bands.
""" + "\n\n".join(f"Filler paragraph number {i} to make the sheet long enough to scroll." for i in range(40)) + """
## The grievances
He has refused his Assent to Laws, the most wholesome and necessary for the public good.
## Conclusion
These United Colonies are, and of Right ought to be Free and Independent States."""


@pytest.fixture
def doc(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.documento import data as d
    assert d.apply_action("show", {"body": BODY, "title": "Declaration"})["ok"]
    return d


@pytest.mark.parametrize("q,want", [("He has refused his Assent", "He has refused his Assent to Laws"),
                                    ("the grievances", "The grievances"), ("preamble", "Preamble")])
def test_goto_finds_the_passage(doc, q, want):
    got = doc.apply_action("goto", {"text": q})
    assert got["ok"] and got["found"].startswith(want), got
    assert doc.view_data()["focus"]["text"].startswith(want)


def test_a_passage_nobody_finds_offers_the_headings(doc):
    got = doc.apply_action("goto", {"text": "zzzz qqqq"})
    assert not got["ok"] and "The grievances" in got["headings"]


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def test_the_card_scrolls_to_the_focus_and_marks_it(playwright_available):
    wjs = (ROOT / "widgets/documento/widget.js").read_text(encoding="utf-8")
    data = {"kind": "markdown", "title": "Declaration", "body": BODY, "focus": {"text": "He has refused his Assent"}}
    html = ("""<!doctype html><html><head><meta charset="utf-8"><style>#c{width:560px;height:420px;display:flex;
    flex-direction:column}</style></head><body><div id="c"></div><script type="module">
    import { render } from "/w.js"; render(document.getElementById("c"), __D__, {lang:"en"}); window.__ready=true;
    </script></body></html>""").replace("__D__", json.dumps(data))

    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page()
            await pg.route("http://doc.test/", lambda r: asyncio.ensure_future(
                r.fulfill(status=200, content_type="text/html", body=html)))
            await pg.route("http://doc.test/w.js", lambda r: asyncio.ensure_future(
                r.fulfill(status=200, content_type="text/javascript", body=wjs)))
            await pg.goto("http://doc.test/")
            await pg.wait_for_function("() => window.__ready === true")
            await pg.wait_for_timeout(200)
            out = await pg.evaluate("""() => ({
              marked: [...document.querySelectorAll('.hbd-focus')].map(n => n.textContent.slice(0, 30)),
              scrolled: document.querySelector('.hbd-scroll').scrollTop })""")
            await b.close()
            return out
    m = asyncio.run(go())
    assert m["marked"] == ["He has refused his Assent to L"], m
    assert m["scrolled"] > 200, "the sheet must move to the passage, not just mark it off-screen"
