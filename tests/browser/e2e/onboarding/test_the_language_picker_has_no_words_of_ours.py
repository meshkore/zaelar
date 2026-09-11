"""The first-run language picker, RENDERED (V2-672, operator 2026-09-11).

His brief: *«pondría un símbolo de una persona hablando para que alguien que no es capaz de leer lo que pone
en la pantalla entienda que tiene que seleccionar el país. Y entonces debajo pondría la bandera y el nombre
del idioma… los 40 idiomas más populares»*, with English and Spanish *«destacados arriba»*.

RENDERED and not read, for the reason this repo keeps paying for: the source can say `grid-template-columns`
and the rows can still be clipped, and it can say `SPEAKING_ICON` while the SVG paints nothing. What is
measured here is what a person would see — the mark has ink, the two shipped languages are the first two
rows and look different from the rest, every row carries a flag and a native name, the list actually scrolls
instead of overflowing the card, and a click posts the code the row stands for.

The REAL modules are served from disk (dom.js, reactive.js, store.js, the component), so this drives the
product and not a copy of it.
"""
import asyncio
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
FRONT = ROOT / "frontend"

_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/app/core/palette.css">
<link rel="stylesheet" href="/app/core/shared-surfaces.css">
<style>html,body{margin:0;height:100%;background:#0a1017}</style>
</head><body><div id="root"></div>
<script type="module">
  import { LanguageOnboarding } from "/app/components/LanguageOnboarding.js";
  // The SAME specifier the component uses, cache-buster included: "/app/core/store.js" and
  // "/app/core/store.js?v=2" are two different modules to an ES loader, so dropping the query would give
  // the test its own copy of the store and `setLangOnboardOpen` would move nothing on screen.
  import * as store from "/app/core/store.js?v=2";
  window.__store = store;
  const el = LanguageOnboarding();
  document.getElementById("root").appendChild(el);
  store.setLangOnboardOpen(true);
  window.__ready = true;
</script></body></html>"""

_READ = """() => {
  const rows = [...document.querySelectorAll(".lang-onb-row")];
  const mark = document.querySelector(".lang-onb-mark svg");
  const list = document.querySelector(".lang-onb-list");
  const card = document.querySelector(".lang-onb-card");
  const pinned = [...document.querySelectorAll(".lang-onb-pinned .lang-onb-row")];
  const cs = mark ? getComputedStyle(mark) : null;
  return {
    total: rows.length,
    pinned: pinned.map(b => ({
      flag: b.querySelector(".lang-onb-flag").textContent,
      name: b.querySelector(".lang-onb-name").textContent,
      lang: b.getAttribute("lang"),
      weightPx: Math.round(parseFloat(getComputedStyle(b).fontSize)),
      border: getComputedStyle(b).borderTopColor,
    })),
    firstRest: (() => {
      const b = document.querySelector(".lang-onb-list .lang-onb-row");
      return b ? { flag: b.querySelector(".lang-onb-flag").textContent,
                   name: b.querySelector(".lang-onb-name").textContent,
                   border: getComputedStyle(b).borderTopColor } : null;
    })(),
    everyRowHasFlagAndName: rows.every(b => {
      const f = b.querySelector(".lang-onb-flag"), n = b.querySelector(".lang-onb-name");
      return !!f && !!n && f.textContent.trim().length > 0 && n.textContent.trim().length > 0;
    }),
    markInk: !!mark && mark.getBoundingClientRect().width > 20 && cs.display !== "none",
    listScrolls: !!list && list.scrollHeight > list.clientHeight + 4,
    listInsideCard: !!list && !!card &&
      Math.round(list.getBoundingClientRect().bottom) <= Math.round(card.getBoundingClientRect().bottom) + 1,
    cardOnScreen: !!card && card.getBoundingClientRect().bottom <= window.innerHeight + 1
                        && card.getBoundingClientRect().top >= -1,
    visibleText: document.querySelector(".lang-onb-card").innerText,
    posted: window.__posted || [],
  };
}"""


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def _serve(route, url: str):
    """Serve the REAL frontend tree from disk, so the component under test is the shipped one."""
    path = url.split("?", 1)[0].split("http://zaelar.test", 1)[-1].lstrip("/")
    f = FRONT / path
    if not f.is_file():
        return asyncio.ensure_future(route.fulfill(status=404, body="no"))
    ctype = {"js": "text/javascript", "css": "text/css"}.get(f.suffix.lstrip("."), "text/plain")
    return asyncio.ensure_future(
        route.fulfill(status=200, content_type=ctype, body=f.read_text(encoding="utf-8")))


async def _boot(pw, viewport=None):
    from i18n import catalog
    b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = await b.new_page(viewport=viewport or {"width": 1400, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))

    await pg.route("http://zaelar.test/api/i18n/state", lambda r: asyncio.ensure_future(
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"chosen": False, "picker": catalog.picker()}))))
    await pg.route("http://zaelar.test/api/i18n/choose/**", lambda r: asyncio.ensure_future(
        r.fulfill(status=200, content_type="application/json", body='{"ok": true}')))
    await pg.route("http://zaelar.test/api/library/base", lambda r: asyncio.ensure_future(
        r.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": True, "base": "/Users/x", "root": "/Users/x/library",
             "can_choose": True, "has_dialog": True}))))
    await pg.route("http://zaelar.test/", lambda r: asyncio.ensure_future(
        r.fulfill(status=200, content_type="text/html", body=_HTML)))
    await pg.route("http://zaelar.test/app/**", lambda r: _serve(r, r.request.url))

    await pg.goto("http://zaelar.test/")
    await pg.wait_for_function("() => window.__ready === true")
    # record every choose POST the picker makes, so a click can be asserted end to end
    await pg.evaluate("""() => {
      window.__posted = [];
      const f = window.fetch;
      window.fetch = (u, o) => { if (String(u).includes('/api/i18n/choose/')) window.__posted.push(String(u)); return f(u, o); };
    }""")
    await pg.wait_for_function("() => document.querySelectorAll('.lang-onb-row').length > 30")
    return b, pg, errors


def _run(steps=(), viewport=None):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw, viewport)
            for step in steps:
                await step(pg)
            out = await pg.evaluate(_READ)
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(go())


def test_the_screen_says_what_it_wants_without_a_single_word(playwright_available):
    m = _run()
    assert not m["errors"], f"page errors: {m['errors']}"
    assert m["markInk"], "the speaking mark must actually paint — it is the whole instruction"
    assert m["total"] >= 40, f"expected the full catalog on screen, got {m['total']}"
    assert m["everyRowHasFlagAndName"], "every row is a flag plus the language's own name"
    text = m["visibleText"]
    for prose in ("language", "Language", "select", "Select", "choose", "Choose"):
        assert prose not in text, f"the screen must instruct in no language at all — found {prose!r}"


def test_the_two_shipped_languages_are_the_first_rows_and_look_different(playwright_available):
    m = _run()
    assert [p["lang"] for p in m["pinned"]] == ["en", "es"], m["pinned"]
    assert [p["name"] for p in m["pinned"]] == ["English", "Español"]
    assert all(p["flag"].strip() for p in m["pinned"])
    rest = m["firstRest"]
    assert rest, "the rest of the catalog must render below"
    assert m["pinned"][0]["border"] != rest["border"], (
        "«destacados arriba»: a pinned row has to be visibly different, not merely first")
    assert m["pinned"][0]["weightPx"] > 0


def test_forty_rows_scroll_inside_the_card_instead_of_running_off_the_screen(playwright_available):
    m = _run()
    assert m["listScrolls"], "40 rows must scroll — a list that grows the card pushes it off screen"
    assert m["listInsideCard"], "the list must stay inside the card"
    assert m["cardOnScreen"], "the card must fit the viewport"


def test_it_fits_a_phone(playwright_available):
    m = _run(viewport={"width": 390, "height": 780})
    assert m["cardOnScreen"] and m["listInsideCard"], m
    assert m["total"] >= 40
    assert not m["errors"], f"page errors: {m['errors']}"


def test_typing_narrows_the_list_and_clicking_a_row_locks_that_language(playwright_available):
    async def filter_and_click(pg):
        await pg.fill(".lang-onb-input", "deu")
        await pg.wait_for_function("() => document.querySelectorAll('.lang-onb-row').length === 1")
        await pg.click(".lang-onb-row")
        await pg.wait_for_function("() => (window.__posted || []).length === 1")
    m = _run([filter_and_click])
    assert [u.split("zaelar.test")[-1] for u in m["posted"]] == ["/api/i18n/choose/de"], m["posted"]
    assert not m["errors"], f"page errors: {m['errors']}"


# ── step two: where the files go (V2-672) ─────────────────────────────────────────────────────────────────

_FOLDER_READ = """() => {
  const card = document.querySelector(".lang-onb-card");
  const veil = document.querySelector(".lang-onb");
  const btns = [...document.querySelectorAll(".lang-onb-fbtn")];
  return {
    showing: !!document.querySelector(".lang-onb-folder"),
    markInk: (() => { const m = document.querySelector(".lang-onb-folder svg");
                      return !!m && m.getBoundingClientRect().width > 20; })(),
    title: (document.querySelector(".lang-onb-ftitle") || {}).textContent || "",
    path: (document.querySelector(".lang-onb-fpath") || {}).textContent || "",
    buttons: btns.map(b => b.textContent),
    problem: (document.querySelector(".lang-onb-fproblem") || {}).textContent || "",
    gone: !!veil && veil.classList.contains("gone"),
    onScreen: !!card && card.getBoundingClientRect().bottom <= window.innerHeight + 1,
    loading: !!document.querySelector(".lang-onb-loading"),
  };
}"""


async def _choose_language_then_detected(pg):
    """Click a language, then play the SSE 'detected' event the way services/sse.js does — including the
    already-translated strings the priority pass sends with it."""
    await pg.fill(".lang-onb-input", "deu")
    await pg.wait_for_function("() => document.querySelectorAll('.lang-onb-row').length === 1")
    await pg.click(".lang-onb-row")
    await pg.evaluate("""() => {
      window.__store.setLangOnboardPhase("detected");
      window.__store.setLangOnboardLoading("Wird vorbereitet…");
      window.__store.setLangOnboardStrings({
        "onboarding.folder.title": "Wo sollen die Dateien liegen?",
        "onboarding.folder.choose": "Ordner wählen",
        "onboarding.folder.skip": "Überspringen",
        "onboarding.folder.problem": "Dieser Ordner geht nicht.",
      });
    }""")
    await pg.wait_for_function("() => !!document.querySelector('.lang-onb-folder')")


def _run_folder(steps=()):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            await _choose_language_then_detected(pg)
            for step in steps:
                await step(pg)
            out = await pg.evaluate(_FOLDER_READ)
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(go())


def test_the_wait_is_spent_asking_where_the_files_go_in_the_language_just_chosen(playwright_available):
    """«Eso podría ser el paso número dos, en el idioma correspondiente… mientras se está haciendo la
    traducción.» The words come from the SSE event, already translated — so this step is never in English
    just because the full bundle is not built yet."""
    m = _run_folder()
    assert m["showing"], "the folder step must replace the bare spinner"
    assert m["markInk"], "a folder mark, so the step reads before its words do"
    assert m["title"] == "Wo sollen die Dateien liegen?", m["title"]
    assert m["buttons"] == ["Ordner wählen", "Überspringen"], m["buttons"]
    assert m["path"] == "/Users/x/library", "it has to say where the files go TODAY"
    assert m["onScreen"] and not m["errors"], m


def test_the_language_being_ready_does_not_snatch_the_question_away(playwright_available):
    """The bundle finishing is not permission to close: he may be half-way through choosing a folder."""
    async def ready(pg):
        await pg.evaluate("""() => { window.__store.setLangOnboardPhase("ready");
                                     window.__store.requestLangOnboardClose(); }""")
    m = _run_folder([ready])
    assert m["showing"], "«ready» must not remove an unanswered question"
    assert not m["gone"], "and must not fade the card out from under it"


def test_skip_is_a_real_way_out(playwright_available):
    """«También hay que poner un botón de skip por si alguien no quiere hacer eso.»"""
    async def ready_then_skip(pg):
        await pg.evaluate("""() => { window.__store.setLangOnboardPhase("ready");
                                     window.__store.requestLangOnboardClose(); }""")
        await pg.click(".lang-onb-fbtn.ghost")
        await pg.wait_for_function("() => document.querySelector('.lang-onb').classList.contains('gone')")
    m = _run_folder([ready_then_skip])
    assert m["gone"] and not m["showing"], m


def test_a_folder_that_cannot_be_used_says_so_instead_of_failing_silently(playwright_available):
    async def refuse(pg):
        await pg.route("http://zaelar.test/api/library/base", lambda r: asyncio.ensure_future(
            r.fulfill(status=400, content_type="application/json",
                      body='{"ok": false, "reason": "system_directory"}'))
            if r.request.method == "POST" else asyncio.ensure_future(r.fallback()))
        await pg.fill(".lang-onb-folder .lang-onb-input", "/etc")
        await pg.press(".lang-onb-folder .lang-onb-input", "Enter")
        await pg.wait_for_function("() => !!document.querySelector('.lang-onb-fproblem')")
    m = _run_folder([refuse])
    assert m["problem"] == "Dieser Ordner geht nicht.", m["problem"]
    assert m["showing"], "a refusal leaves him on the step, able to try again"
