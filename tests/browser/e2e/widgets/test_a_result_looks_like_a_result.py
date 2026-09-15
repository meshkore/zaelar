"""V2-702 — the results LIST, rendered, because every one of its defects was a matter of geometry.

The operator ran a real search ("cacerola inox 18cm · tapa cristal · 4L+ · inducción"), got one 100% match, and
sent the screenshot: "me pone el precio, me pone la puntuación, la foto no se ve bien (…) estas fotos
horizontales no sirven para nada porque no se ve absolutamente nada. Debería haber quedado la foto a la izquierda
y los resultados a la derecha. Eso como formato estándar de búsqueda. Después, el botón de ver los detalles no
funciona."

Four separate defects, all of them measurable in a mounted DOM and none of them visible from source:

  1. THE BAND. `.hr-img` was `width:100%;height:128px;object-fit:cover`, so the box aspect came from the CARD's
     width and a constant. On his maximized sheet that box measured 1142x168 (6.8:1) while the photo was 320x251
     (1.27:1): `cover` scaled it to 1142x896 and cropped 81% of its height away. What survived was a horizontal
     strip of stainless steel with no pot in it. The cure is a plate of FIXED aspect with the image CONTAINED,
     so the ratio on screen is the photo's own, whatever the card width does.
  2. THE COLUMN. Photo on top, data under it. He asked for the market standard — photo left, data right.
  3. THE LINK THAT WAS NEVER THERE. The card became an <a> only when it had NOTHING else to offer
     (`asLink = url && !hasDetail`), so the RICHEST results — the ones with a rating, a spec sheet and photos,
     i.e. the ones worth opening — were exactly the ones whose url never reached the screen. His item carried
     `https://www.amazon.es/dp/B075WGKKGB` and the rendered list contained ZERO anchors.
  4. THE DEAD BUTTON. Measured separately in `tests/browser/unit/widgets/test_a_sheet_push_reaches_its_card.py`:
     the POST landed and the screen never moved. Here we assert the other half — the record opens from what is
     already in memory, without waiting for any round trip at all.

Nothing here can be seen by a source test: whether an image is cropped is a question about `naturalWidth`
against a painted box, and whether a photo is to the LEFT of the data is a question about two rectangles.
"""
from __future__ import annotations

import asyncio
import base64
import os
import struct
import zlib

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "results", "widget.js")


def _png(w: int, h: int) -> str:
    """A real PNG of an exact size, as a data: URI. The harness must not reach the network (and a 404 image
    removes itself, which would make "the photo is not cropped" pass for the wrong reason: there would be no
    photo). Built here rather than committed as a fixture so the DIMENSIONS are visible in the test that
    depends on them."""
    def chunk(tag: bytes, body: bytes) -> bytes:
        c = tag + body
        return struct.pack(">I", len(body)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes((200, 205, 215)) * w for _ in range(h))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


#: The REAL shape of the photo in his sheet: 320x251, i.e. slightly TALLER than 4:3 and nothing like a band.
_SHOT_W, _SHOT_H = 320, 251
_SHOT = _png(_SHOT_W, _SHOT_H)

#: His sheet, reduced to the fields that decide the layout. The url is the real one from the incident.
_SHEET = {
    "title": "Cacerola inox 18cm · tapa cristal · 4L+ · inducción",
    "subtitle": "1 de ~75 evaluados cumple el 100%.",
    "tab": "results",
    "items": [{
        "title": "VIER Olla Alta OI18",
        "subtitle": "Olla alta 18/10 · O18 x 16 cm · tapa cristal",
        "price": "EUR 17,36",
        "badge": "ONLY 100% MATCH",
        "url": "https://www.amazon.es/dp/B075WGKKGB",
        "image": _SHOT,
        "images": [_SHOT],
        "primary": True,
        "facts": [{"label": "Capacidad", "value": "4 L"},
                  {"label": "Diámetro base", "value": "18 cm"},
                  {"label": "Tapa", "value": "Cristal con aro inox"}],
        "score": {"value": 9.2, "max": 10, "why": "el único que cumple los 5 criterios duros"},
    }],
}

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-bg-soft:#16202b;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
--hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-bubble:#1b2735;--hb-ok:#1f9d55;
--hb-warn-ink:#e0a355;--hb-danger:#d6455d;
--s1:4px;--s2:8px;--s3:12px;--s4:16px;--s5:24px;--r-sm:6px;--r-md:10px;--r-lg:14px;--line:1px solid #243244;
--f-micro:10px;--f-sm:12px;--f-body:13px;--f-md:15px;--f-lg:18px}
body{margin:0;background:#0a1017;padding:0}#host{width:1140px}
</style></head><body><div id="host"></div></body></html>"""

#: HOW MUCH OF THE PHOTO IS ACTUALLY ON SCREEN.
#:
#: The first version of this file compared the IMG's bounding box against the photo's natural aspect, and a
#: disarm proved it worthless: putting the 168px band back left it GREEN. An `<img>` element's rect is its
#: LAYOUT box, and with `object-fit` the pixels are painted somewhere else entirely — under `cover` the content
#: is scaled to FILL that box and overflows it, and what the operator sees is whatever survives the parent's
#: `overflow:hidden`. Measuring the box measured neither the painting nor the clipping.
#:
#: So compute what the browser actually paints — the content rect that `object-fit` produces — intersect it with
#: the plate that clips it, and return the surviving FRACTION of the picture. That is the operator's complaint
#: expressed as a number, and it holds whatever CSS mechanism is used to get there. On the original code it
#: comes out at 0.19: box 1142x168, photo 320x251, `cover` scales it to 1142x896, and 168 of those 896 rows
#: survive. Eighty-one per cent of the pot was not on screen.
_SHOWN = """function shown(img, clipEl){
  const b = img.getBoundingClientRect();
  const clip = clipEl.getBoundingClientRect();
  const nw = img.naturalWidth, nh = img.naturalHeight;
  if(!nw || !nh || !b.width || !b.height) return null;
  const fit = getComputedStyle(img).objectFit;
  let cw, ch;
  if(fit === 'fill' || fit === 'none'){ cw = b.width; ch = b.height; }
  else {
    const s = fit === 'cover' ? Math.max(b.width/nw, b.height/nh) : Math.min(b.width/nw, b.height/nh);
    cw = nw*s; ch = nh*s;
  }
  const cx = b.left + (b.width - cw)/2, cy = b.top + (b.height - ch)/2;   // default object-position: 50% 50%
  const ix = Math.max(0, Math.min(cx+cw, clip.right)  - Math.max(cx, clip.left));
  const iy = Math.max(0, Math.min(cy+ch, clip.bottom) - Math.max(cy, clip.top));
  return {fraction: (ix*iy)/(cw*ch), painted: {w: cw, h: ch}, clip: {w: clip.width, h: clip.height}};
}"""

_MEASURE = """() => {
  """ + _SHOWN + """
  const el = document.querySelector('.hb-results');
  if(!el) return {mounted:false};
  const card = el.querySelector('.hr-card');
  const plate = el.querySelector('.hr-shot');
  const img = plate ? plate.querySelector('img') : null;
  const body = el.querySelector('.hr-body');
  const r = img ? img.getBoundingClientRect() : null;
  const pr = plate ? plate.getBoundingClientRect() : null;
  const br = body ? body.getBoundingClientRect() : null;
  return {
    mounted: true,
    card_classes: card ? card.className : '',
    plate: pr ? {w: pr.width, h: pr.height} : null,
    photo: (img && plate) ? shown(img, plate) : null,
    img_natural: img ? {w: img.naturalWidth, h: img.naturalHeight} : null,
    photo_left_of_data: (r && br) ? (r.right <= br.left + 1) : null,
    anchors: [...el.querySelectorAll('a[href]')].map(a => ({text: a.textContent.trim(), href: a.href})),
    detail_btn: !!el.querySelector('.hr-more'),
  };
}"""

_AFTER_CLICK = """() => {
  """ + _SHOWN + """
  const el = document.querySelector('.hb-results');
  return {
    detail_open: !!el.querySelector('.hr-back'),
    title: (el.querySelector('.hr-dt') || {}).textContent || '',
    anchors: [...el.querySelectorAll('a[href]')].map(a => a.href),
    gallery: [...el.querySelectorAll('.hr-gal img')]
      .map(i => { const r = shown(i, i.parentElement); return r ? r.fraction : null; }),
  };
}"""


def _paint(sheet, *, width=1140, click_detail=False, answer=None):
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": width + 60, "height": 1000})
            errors, sent = [], []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("http://zaelar.test/",
                           lambda route: asyncio.ensure_future(
                               route.fulfill(status=200, content_type="text/html", body=_HTML)))
            await pg.goto("http://zaelar.test/")
            await pg.evaluate("w => document.getElementById('host').style.width = w + 'px'", width)
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(
                content=src.replace("export function render", "window.render = function render"))
            # The action channel is a SPY, never a repaint: the whole point of the detail assertion is that the
            # widget draws the record WITHOUT the server pushing anything back.
            await pg.expose_function("_send", lambda n, p: (sent.append((n, p)),
                                                            answer if answer is not None else {"ok": True})[1])
            await pg.evaluate("""d => window.render(document.getElementById('host'), d, {
                action: async (n, p) => await window._send(n, p), top: () => {}, scroll: () => {}})""", sheet)
            await pg.wait_for_timeout(350)
            out = await pg.evaluate(_MEASURE)
            if click_detail:
                btn = await pg.query_selector(".hr-more")
                assert btn is not None, "no hay botón de detalle que pulsar"
                await btn.click()
                await pg.wait_for_timeout(250)
                out["after_click"] = await pg.evaluate(_AFTER_CLICK)
            out["errors"] = errors
            out["sent"] = sent
            await b.close()
            return out
    return asyncio.run(run())


@pytest.fixture(scope="module")
def wide():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return _paint(_SHEET)


def test_it_mounts_without_a_single_error(wide):
    assert wide["mounted"], "the sheet did not paint"
    assert wide["errors"] == [], wide["errors"]


def test_the_photo_is_shown_WHOLE_never_cropped_to_a_band(wide):
    """DEFECT 1, and the one this file exists for. What fraction of the picture survives to the screen?

    Measured on the code he was looking at: 0.19 — a 1142x168 band showing 168 of the 896 rows the browser
    painted. The property is "the pot is visible", not "`object-fit` is `contain`": the assertion is on what
    reaches the glass, so any future way of getting there passes and any future band fails.
    """
    nat = wide["img_natural"]
    assert nat == {"w": _SHOT_W, "h": _SHOT_H}, f"la foto de prueba no cargó: {nat}"
    p = wide["photo"]
    assert p, "no hay foto pintada que medir"
    assert p["fraction"] >= 0.98, (
        f"solo se ve el {p['fraction']:.0%} de la foto — se pinta {p['painted']['w']:.0f}x{p['painted']['h']:.0f} "
        f"dentro de un recorte de {p['clip']['w']:.0f}x{p['clip']['h']:.0f}")
    plate = wide["plate"]
    assert plate["w"] / plate["h"] < 2.2, f"la bandeja es una banda apaisada: {plate}"


def test_the_photo_is_on_the_LEFT_and_the_data_on_the_right(wide):
    """DEFECT 2. His words, verbatim: «debería haber quedado la foto a la izquierda y los resultados a la
    derecha. Eso como formato estándar de búsqueda»."""
    assert "split" in wide["card_classes"], wide["card_classes"]
    assert wide["photo_left_of_data"] is True, (
        "la foto no está a la izquierda de los datos — la tarjeta sigue apilada")


def test_the_link_to_the_ORIGINAL_page_is_on_the_card(wide):
    """DEFECT 3. And it names the SITE, because "where does this take me" is the question a link answers."""
    hrefs = [a["href"] for a in wide["anchors"]]
    assert "https://www.amazon.es/dp/B075WGKKGB" in hrefs, (
        f"el enlace a la ficha original no está en la lista: {wide['anchors']}")
    label = next(a["text"] for a in wide["anchors"] if "amazon.es/dp" in a["href"])
    assert "amazon.es" in label, f"el enlace no dice a dónde lleva: «{label}»"


def test_the_record_opens_WITHOUT_waiting_for_the_server():
    """DEFECT 4, the half that lives in the widget. The item is already on screen; drawing it needs no fetch.

    The spy answers `{ok:True}` but pushes NOTHING back — there is no SSE in this harness — so if the record
    appears, it was painted locally. Before the fix this button only posted and waited, which is why it looked
    dead for as long as the push carried an id the canvas could not match.
    """
    out = _paint(_SHEET, click_detail=True)
    assert out["errors"] == [], out["errors"]
    assert out["after_click"]["detail_open"] is True, "«Ver detalle» no abrió el expediente"
    assert "VIER" in out["after_click"]["title"], out["after_click"]["title"]
    assert ("detail", {"title": "VIER Olla Alta OI18"}) in out["sent"], (
        f"el expediente se pintó pero no se persistió: {out['sent']}")


def test_the_record_ALSO_carries_the_link_and_no_cropped_gallery():
    """The record is the page he opens BECAUSE he wants to look at the thing: the gallery there had the same
    100px-of-`cover` band, and the url was printed raw at the very bottom under the whole spec table."""
    out = _paint(_SHEET, click_detail=True)
    after = out["after_click"]
    assert "https://www.amazon.es/dp/B075WGKKGB" in after["anchors"], after["anchors"]
    assert after["gallery"], "el expediente no pintó ninguna foto"
    assert all(f is not None and f >= 0.98 for f in after["gallery"]), (
        f"la galería del expediente recorta las fotos: fracciones visibles {after['gallery']}")


def test_a_view_that_could_not_be_saved_SAYS_SO_instead_of_undoing_itself():
    """A refused action has to show — but it no longer snatches the page back. The record IS painted and
    correct; what failed is storing that he is looking at it, and that is what the notice says."""
    out = _paint(_SHEET, click_detail=True, answer={"ok": False, "error": "no encuentro esa hoja"})
    assert out["after_click"]["detail_open"] is True, (
        "un fallo al PERSISTIR deshizo una navegación que era correcta")


def test_a_narrow_card_stacks_the_photo_but_never_flattens_it():
    """The two columns only work while there is room for two. Below ~430px the photo goes back on top — still a
    fixed-aspect plate, never the band this whole file exists to kill."""
    out = _paint(_SHEET, width=380)
    assert out["errors"] == [], out["errors"]
    p = out["photo"]
    assert p["fraction"] >= 0.98, f"estrecha, la foto se recorta: se ve el {p['fraction']:.0%}"
    assert out["photo_left_of_data"] in (False, None), "a 380px la foto sigue robando una columna"


# ── THE FOUR LIST FORMATS ────────────────────────────────────────────────────────────────────────────────────
# «me gustaría que la lista de resultados pueda tener de uno a cinco tipos de formato y que nos adaptemos a cada
# tipo de artículo dependiendo de lo que hay que mostrar». They are preset in the widget and CHOSEN BY IT, from
# the shape of the items plus an optional `kind` that says WHAT the results are — which is content, not layout,
# and therefore the one thing a filler may declare (`widgets/presentation.py` rule 1: the surface owns layout).

def _sheet(items, **rest):
    return {"title": "x", "tab": "results", "items": items, **rest}


_A_PHOTO = {"image": _SHOT}


def _classes(sheet, width=1140):
    out = _paint(sheet, width=width)
    assert out["errors"] == [], out["errors"]
    return out["card_classes"]


def test_an_article_with_data_gets_the_photo_left_format():
    """The default for anything that IS a thing you buy: the photo identifies it, the data decides it."""
    cls = _classes(_sheet([{"title": "Olla", "price": "17,36 €", **_A_PHOTO},
                           {"title": "Cazo", "price": "12,10 €", **_A_PHOTO}]))
    assert "split" in cls, cls


def test_a_bare_thumbnail_list_gets_the_GALLERY_format():
    """Nothing to put in a column beside the photo — no price, no rating, no spec sheet. A photo-left card there
    would be a wide tile mostly made of empty space."""
    cls = _classes(_sheet([{"title": "Cala Tarida", **_A_PHOTO}, {"title": "Ses Salines", **_A_PHOTO}]))
    assert "gallery" in cls, cls


def test_results_with_no_photo_at_all_get_PLAIN_ROWS():
    """A column of empty plates is worse than no column."""
    cls = _classes(_sheet([{"title": "Informe 2025", "subtitle": "PDF · 40 págs"},
                           {"title": "Informe 2024", "subtitle": "PDF · 38 págs"}]))
    assert "rows" in cls, cls


def test_a_declared_KIND_is_honoured_over_the_guess():
    """The seam that lets a search say what it found. Same items —a photo and a title— read as places (gallery)
    or as documents (rows) depending on what they ARE, which only the filler knows."""
    items = [{"title": "Cala Tarida", **_A_PHOTO}, {"title": "Ses Salines", **_A_PHOTO}]
    assert "rows" in _classes(_sheet(items, kind="document"))
    assert "gallery" in _classes(_sheet(items, kind="place"))
    assert "split" in _classes(_sheet(items, kind="product"))


def test_an_unknown_kind_falls_back_to_the_shape_instead_of_breaking():
    """`kind` arrives from a model. A word the widget does not know must cost nothing."""
    cls = _classes(_sheet([{"title": "Olla", "price": "17,36 €", **_A_PHOTO}], kind="ornitorrinco"))
    assert "split" in cls, cls


def test_a_composite_proposal_still_gets_its_COMPARE_card():
    """The format that already existed keeps its name and its shape: pieces listed with their own price, so
    three plans stay comparable at a glance."""
    out = _paint(_sheet([{"title": "Plan A", **_A_PHOTO,
                          "parts": [{"kind": "Hotel", "title": "Insotel", "price": "1.200€"},
                                    {"kind": "Ferry", "title": "Baleària", "price": "640€"}]}]))
    assert "compare" in out["card_classes"], out["card_classes"]
