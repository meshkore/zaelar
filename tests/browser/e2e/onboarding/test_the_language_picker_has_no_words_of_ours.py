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
    assert [p["lang"] for p in m["pinned"]] == ["en-US", "en-GB", "es-ES", "es-419"], m["pinned"]
    assert [p["name"] for p in m["pinned"]] == ["English (US)", "English (UK)",
                                                "Español (España)", "Español (Latinoamérica)"]
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


# ── one mark, one language (V2-730) ───────────────────────────────────────────────────────────────────────

# Read the ACCENT as the browser resolves it, then ask every row what colour its border actually is. A
# class check would pass with the rule deleted from the stylesheet; this measures the paint.
_MARK_READ = """() => {
  const probe = document.createElement("span");
  probe.style.color = getComputedStyle(document.documentElement).getPropertyValue("--hb-accent").trim();
  document.body.appendChild(probe);
  const accent = getComputedStyle(probe).color;
  probe.remove();
  const rows = [...document.querySelectorAll(".lang-onb-row")];
  return {
    accent,
    marked: rows.filter(b => getComputedStyle(b).borderTopColor === accent).map(b => b.getAttribute("lang")),
    pressed: rows.filter(b => b.getAttribute("aria-pressed") === "true").map(b => b.getAttribute("lang")),
    pinnedBorders: [...document.querySelectorAll(".lang-onb-pinned .lang-onb-row")]
      .map(b => [b.getAttribute("lang"), getComputedStyle(b).borderTopColor]),
  };
}"""


def _run_mark(steps=()):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            for step in steps:
                await step(pg)
            out = await pg.evaluate(_MARK_READ)
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(go())


def test_the_first_screen_marks_NOTHING_and_a_click_marks_exactly_one(playwright_available):
    """The operator, on a fresh install (2026-09-20): *«te quedan seleccionados los dos idiomas. Tienes que
    seleccionar solo uno»* — so V2-730 marked ONE row, the engine's running language. And after his reset of
    2026-09-24 (V2-765): *«no quiero que ninguno esté seleccionado por defecto. El usuario tiene que hacer
    clic»*. A row already marked on the first screen reads as a choice made for him, on the one screen
    whose point is that nothing is chosen until he chooses. The accent appears on the row he clicks, and
    moves if he clicks another; it never accumulates.
    """
    m = _run_mark()
    assert not m["errors"], f"page errors: {m['errors']}"
    assert m["marked"] == [], f"no language may wear the accent before a click, got {m['marked']}"
    assert m["pressed"] == [], f"and none may say so to a screen reader, got {m['pressed']}"
    borders = dict(m["pinnedBorders"])
    assert borders["en-US"] == borders["es-ES"], (
        "the two shipped rows must look the same until one is clicked — neither is chosen yet")

    async def click_spanish(pg):
        # keep step two out of the way: since V2-732 the folder question appears as soon as the server says
        # this deployment may choose a folder, and this test is about the picker.
        await pg.route("http://zaelar.test/api/library/base", lambda r: asyncio.ensure_future(
            r.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "can_choose": False}))))
        await pg.click('.lang-onb-pinned .lang-onb-row[lang="es-ES"]')
        await pg.wait_for_function(
            '() => document.querySelector(\'.lang-onb-row[lang="es-ES"]\').classList.contains("sel")')

    m = _run_mark([click_spanish])
    assert m["marked"] == ["es-ES"], (
        f"the mark must MOVE, never accumulate — got {m['marked']} after clicking Espanol")
    assert m["pressed"] == ["es-ES"], m["pressed"]
    assert not m["errors"], f"page errors: {m['errors']}"


# ── the preparing screen, RENDERED (V2-731) ───────────────────────────────────────────────────────────────

_BAR_READ = """() => {
  const bar = document.querySelector(".lang-onb-bar");
  const fill = document.querySelector(".lang-onb-bar-fill");
  const text = document.querySelector(".lang-onb-loading-text");
  const rb = bar ? bar.getBoundingClientRect() : null;
  const rf = fill ? fill.getBoundingClientRect() : null;
  const probe = document.createElement("span");
  probe.style.color = getComputedStyle(document.documentElement).getPropertyValue("--hb-accent").trim();
  document.body.appendChild(probe);
  const accent = getComputedStyle(probe).color;
  probe.remove();
  return {
    spinner: !!document.querySelector(".lang-onb-spinner"),
    barInk: !!rb && rb.width > 100 && rb.height >= 4,
    fillRatio: rb && rf && rb.width > 0 ? Math.round((rf.width / rb.width) * 100) : null,
    fillPainted: !!fill && getComputedStyle(fill).backgroundColor === accent,
    indeterminate: !!bar && bar.classList.contains("indet"),
    text: text ? text.textContent : "",
    cardOnScreen: (() => { const c = document.querySelector(".lang-onb-card");
                           return !!c && c.getBoundingClientRect().height > 40; })(),
  };
}"""


def _run_bar(after_detected="", can_choose=False):
    """Drive a PRESET language the way the engine does: detected (with its denominator), then whatever
    `after_detected` replays. `can_choose=False` keeps the folder question out of the way — this is the
    loading screen, not step two."""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            # registered last, so it wins over _boot's handler
            await pg.route("http://zaelar.test/api/library/base", lambda r: asyncio.ensure_future(
                r.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "can_choose": can_choose}))))
            await pg.click('.lang-onb-pinned .lang-onb-row[lang="es-ES"]')
            await pg.evaluate("""() => {
              window.__store.setLangOnboardPhase("detected");
              window.__store.setLangOnboardLoading("Preparando espanol…");
              window.__store.setLangOnboardProgress({ done: 0, total: 3 });
              window.__store.setLangOnboardPreparing(true);   // sse.js does this only when total > 0
            }""")
            await pg.wait_for_function("() => !!document.querySelector('.lang-onb-bar')")
            if after_detected:
                await pg.evaluate(after_detected)
            await pg.wait_for_timeout(450)          # let the width transition land
            out = await pg.evaluate(_BAR_READ)
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(go())


def test_a_language_with_nothing_to_prepare_shows_no_screen_at_all(playwright_available):
    """The operator's correction, once the screen had a floor and a bar (2026-09-20): *«si no hay que hacer
    nada para idiomas inicializados, mejor no mostrar NADA en ese caso»*.

    The engine counts ZERO steps for a language it does not have to generate, and then nothing new is
    drawn: he keeps looking at the picker, with the choice he just made marked on it, until the veil fades.
    """
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            await pg.route("http://zaelar.test/api/library/base", lambda r: asyncio.ensure_future(
                r.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "can_choose": False}))))
            await pg.click('.lang-onb-pinned .lang-onb-row[lang="es-ES"]')
            # exactly what sse.js does for total 0: the phases move, nothing is armed, nothing is set
            await pg.evaluate("""() => {
              window.__store.setLangOnboardPhase("detected");
              window.__store.setLangOnboardPhase("ready");
            }""")
            await pg.wait_for_timeout(300)
            out = await pg.evaluate("""() => ({
              bar: !!document.querySelector(".lang-onb-bar"),
              spinner: !!document.querySelector(".lang-onb-spinner"),
              loading: !!document.querySelector(".lang-onb-loading"),
              folder: !!document.querySelector(".lang-onb-folder"),
              rows: document.querySelectorAll(".lang-onb-row").length,
              marked: [...document.querySelectorAll(".lang-onb-row")]
                        .filter(x => x.classList.contains("sel")).map(x => x.getAttribute("lang")),
            })""")
            out["errors"] = errors
            await b.close()
            return out
    m = asyncio.run(go())
    assert not m["errors"], f"page errors: {m['errors']}"
    assert not m["bar"] and not m["spinner"] and not m["loading"], (
        f"nothing to prepare must show NO preparing screen: {m}")
    assert not m["folder"], "and this deployment cannot choose a folder either"
    assert m["rows"] >= 40, "he is still looking at the picker — nothing new appeared and nothing vanished"
    assert m["marked"] == ["es-ES"], "with the choice he just made still marked on it"


def test_the_preparing_screen_carries_a_bar_that_paints_and_fills(playwright_available):
    """«Si hay un loader o una pantalla tiene que tener un progress bar o algo.» The spinner it replaces
    said only that something was happening — and on a preset language it said it for about 200 ms."""
    m = _run_bar()
    assert not m["errors"], f"page errors: {m['errors']}"
    assert not m["spinner"], "the bare spinner is gone — it is what he could not read"
    assert m["barInk"], "the bar has to actually paint, not merely exist in the source"
    assert m["fillPainted"], "an unpainted fill is a bar that never moves"
    assert m["text"] == "Preparando espanol…", "and the screen says what it is doing, in his language"
    assert not m["indeterminate"], "the engine sent a denominator — the bar must be determinate"
    # 0 of 3 is a visible sliver, not an empty track: `pct()` floors at 8 so the bar reads as started
    # rather than broken. What it must never be is full.
    assert 4 <= m["fillRatio"] <= 15, f"0 of 3 steps: {m['fillRatio']}%"

    m = _run_bar('() => window.__store.setLangOnboardProgress({ done: 2, total: 3 })')
    assert 55 <= m["fillRatio"] <= 75, f"two of three steps: {m['fillRatio']}%"

    m = _run_bar('() => window.__store.setLangOnboardPhase("ready")')
    assert m["fillRatio"] >= 96, (
        f"a bar stopped short on a screen that says it is done is a screen that lies: {m['fillRatio']}%")
    assert m["cardOnScreen"], "and «ready» does not snatch it away — the floor is still holding it"


def test_with_no_word_from_the_engine_the_bar_sweeps_instead_of_inventing_a_number(playwright_available):
    """An older engine, or a lost event: `null` progress is «I cannot say how far», and a made-up
    percentage would be the kind of state that lies this codebase keeps paying for."""
    m = _run_bar('() => window.__store.setLangOnboardProgress(null)')
    assert m["indeterminate"], "with nothing to count, the bar must sweep"
    assert m["barInk"] and m["fillPainted"], m


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
