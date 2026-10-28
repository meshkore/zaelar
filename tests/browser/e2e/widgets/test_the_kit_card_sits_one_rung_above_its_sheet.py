"""The widget kit's card (`hbk-card`) sits one rung above the sheet it is drawn on, in both themes (V2-831 T-13, node 4.326).

CRIT-K20 / node 4.274 hold the results card to it: a card is `--hb-bg-soft` on a widget's `--hb-bg`, never the same
rung (V2-691 — a card the colour of its ground has only a hairline to tell it apart). The kit painted `--hb-bg`, so
any widget that followed the generator's advice to use it drew cards that vanished into their sheet. RENDERED with
the shell's real stylesheets, in dark (the default) and in light.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

ENG = Path(__file__).resolve().parents[4]
_CSS = [ENG / "frontend" / "app" / "core" / "palette.css", ENG / "frontend" / "app" / "styles.css"]

_MEASURE = """() => {
  const bg = (v) => { const p = document.createElement('div'); p.style.background = v; document.body.appendChild(p);
                      const c = getComputedStyle(p).backgroundColor; p.remove(); return c; };
  return {card: getComputedStyle(document.querySelector('.hbk-card')).backgroundColor,
          sheet: getComputedStyle(document.querySelector('.sheet')).backgroundColor,
          soft: bg('var(--hb-bg-soft)')};
}"""


def _paint(theme: str) -> dict:
    css = "".join(p.read_text(encoding="utf-8") for p in _CSS)
    attr = f" data-theme='{theme}'" if theme == "light" else ""
    html = (f"<!doctype html><html{attr}><head><meta charset='utf-8'><style>{css}</style></head><body>"
            "<div class='sheet' style='background:var(--hb-bg);padding:16px'>"
            "<div class='hbk-card'><div class='hbk-hd'><b>Card</b></div>text</div></div></body></html>")

    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page()
            await pg.set_content(html)
            out = await pg.evaluate(_MEASURE)
            await b.close()
            return out
    return asyncio.run(run())


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_kit_card_is_one_rung_above_its_sheet(theme):
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright is required for the rendered kit card")
    r = _paint(theme)
    assert r["card"] == r["soft"] and r["card"] != r["sheet"], r
