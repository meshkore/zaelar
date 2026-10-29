"""The RENDERED record of a network agent's row shows text, never a Python structure (V2-831 R9, node 4.329).

Demo pass T-19, S3: the LG monitor's record painted `{'country': 'GB'}` and `Rating {'value': 100, 'count': `.
The unit half (node 4.328) proves the stored item is flat; this half mounts the served results client, opens the
record of rows that went through the real producers (`nucleo/cli/mesh._rows_in` → `Candidate.to_row`) and the
sheet's item door, and reads what is ON SCREEN — two providers with different shapes.
Audit captures go to $R9_SHOTS when it is set (the Architect's audit, never the operator's).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from tests.browser import widget_client
from tests.browser.unit.results.test_a_structured_value_reaches_the_card_as_text import AGENT_A, AGENT_B

_ENG = Path(__file__).resolve().parents[4]
#: The product's own tokens, so the capture reads like the card (the assertions read text, not colour).
_HTML = ('<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>'
         + (_ENG / "frontend/app/core/palette.css").read_text(encoding="utf-8")
         + '</style></head><body style="margin:0;background:var(--hb-bg)"><div id="host" style="width:700px">'
         + '</div></body></html>')


def _sheet(agent: dict) -> dict:
    from nucleo.cli import mesh as M
    from widgets.results import clean
    items = clean._clean_items(M._rows_in(agent))
    return {"title": "Monitors", "tab": "results", "items": items, "view": "detail", "focus": items[0]["title"]}


def _paint(sheet: dict, shot: str) -> dict:
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 760, "height": 700})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("http://zaelar.test/", lambda r: asyncio.ensure_future(
                r.fulfill(status=200, content_type="text/html", body=_HTML)))
            await pg.goto("http://zaelar.test/")
            await widget_client.mount(pg, "results")
            await pg.evaluate("""d => window.render(document.getElementById('host'), d, {
                action: async () => ({ok: true}), top: () => {}, scroll: () => {}})""", sheet)
            await pg.wait_for_timeout(300)
            out = await pg.evaluate("""() => { const el = document.querySelector('.hb-results');
                return {detail: !!(el && el.querySelector('.hr-back')),
                        text: el ? el.innerText : '',
                        facts: el ? [...el.querySelectorAll('.hr-facts *, .hr-sec *')].map(n => n.textContent) : []}; }""")
            if os.getenv("R9_SHOTS"):
                await pg.screenshot(path=os.path.join(os.environ["R9_SHOTS"], shot))
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(run())


@pytest.fixture(autouse=True)
def _playwright():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")


@pytest.mark.parametrize("agent,shot,must", [
    (AGENT_A, "agent_a_detail.png", ("GB", "100 · 2417", "173.43")),
    (AGENT_B, "agent_b_detail.png", ("289.00 · USD", "4.6 · 812", "Austin")),
])
def test_the_record_of_a_network_row_paints_no_structure(agent, shot, must):
    out = _paint(_sheet(agent), shot)
    assert not out["errors"], out["errors"]
    assert out["detail"], "the record did not open"
    text = out["text"]
    leaked = [c for c in ("{", "}", "'", "[object") if c in text]
    assert not leaked, f"a structure painted as its repr ({leaked}): {text!r}"
    for m in must:
        assert m in text, f"{m!r} missing from the record: {text!r}"
