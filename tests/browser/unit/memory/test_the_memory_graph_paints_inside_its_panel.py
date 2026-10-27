"""The memory viewer's graph PAINTS inside its panel, centred, at desktop and phone width (V2-808, V2-814, V2-815).
Rendered.

The operator's screenshot of the old 🧠 map: the concept maps («Corto plazo» / «Largo plazo») sat pushed into the
bottom-right corner of the panel instead of filling it. The old map scaled a DOM world once, at open time, against
whatever size the panel had then. The new graph is one <canvas> sized to its section and fitted with
`fitTransform` every time the layout moves or the section resizes; these tests read the canvas PIXELS — a computed
style or a node count would be green on a graph drawn off-screen.

Also rendered here, because each is a claim about what reaches the screen or the server:
  * the overview is ONE plain page — totals, charts, breakdown — that prints each store total exactly once, lets the
    document scroll (no fixed layer, no inner scroller: a full-page capture stitches it) and says nothing about the
    machine (V2-814, V2-816). Disarm in-file: a breakdown that repeats a total is caught;
  * the «Cards» tab paints exactly the cards the server sent, says «shown / total» when the store is bigger,
    and its concept maps paint one circle per concept (V2-815);
  * past the budget the graph says it shows only its top level; «Image» saves a PNG of the view (V2-815);
  * the graph asks the server for the DEVICE's node budget, and the layout worker reports it has settled;
  * the device tier rule (phone / laptop / big screen).

Disarm (in this file, `test_a_fit_that_ignores_the_panel_is_caught`): the module is served with `fitTransform`
anchoring the drawing by its top-left corner at the panel's middle — the reported bottom-right symptom — and the
paint check must fail on it. The test asserts the replacement landed before measuring. (A first disarm, «origin
at the middle, scale 1», stayed GREEN: the layout gravitates to the origin, so that is centred by accident. It
indicted the disarm, not the check.)
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_ES = json.loads((ENGINE / "i18n/genesis/es/ui.json").read_text(encoding="utf-8"))

pytest.importorskip("playwright.sync_api")

_CONCEPTS = ["viajes", "trabajo", "familia", "ocio", "finanzas", "salud", "comida", "deporte", "vivienda",
             "agenda", "estudios", "mascotas"]


def _cards() -> dict:
    card = lambda i, lv: {"id": i, "level": lv, "kind": "fact", "text": f"recuerdo {i}", "importance": 0.5,  # noqa: E731
                          "weight": 0.4, "access_count": 2, "last_access": 1793000000, "ttl_days": None,
                          "pinned": 0, "created": 1793000000, "updated": 1793000000}
    ring = {"nodes": [{"key": c, "label": c, "count": 20 - i} for i, c in enumerate(_CONCEPTS[:8])],
            "links": [{"a": _CONCEPTS[i], "b": _CONCEPTS[i + 1], "weight": 2} for i in range(7)], "total": 31}
    return {"state": {"language": "es"}, "layers": {"short": [card(i, "short") for i in range(12)],
                                                    "long": [card(100 + i, "long") for i in range(40)]},
            "counts": {"short": 12, "long": 5000, "concepts": 31, "edges": 90, "total": 5043},
            "concept_graph": {"short": ring, "long": ring}}


def _graph(budget: int) -> dict:
    concepts = [{"key": c, "label": c, "count": 40 - 3 * i, "short": 5, "last": 1793000000}
                for i, c in enumerate(_CONCEPTS)]
    links = [{"a": _CONCEPTS[i], "b": _CONCEPTS[(i * 5 + 3) % 12], "w": 1 + i % 6} for i in range(12)]
    links += [{"a": _CONCEPTS[i], "b": _CONCEPTS[i + 1], "w": 2} for i in range(11)]
    # Half of the memories hang from ONE concept: a hub with ~300 springs is what overshot the first layout
    # into Infinity (measured on a real-ish store), so the fixture carries one.
    mems = [{"id": 1000 + i, "c": [_CONCEPTS[0] if i % 2 == 0 else _CONCEPTS[i % 12]]
             + ([_CONCEPTS[(i + 4) % 12]] if i % 5 == 0 else []),
             "level": "short" if i % 4 == 0 else "long", "kind": "fact", "w": (i % 10) / 10}
            for i in range(min(600, budget - 12))]
    return {"concepts": concepts, "links": links, "memories": mems,
            "total": {"concepts": 12, "memories": 900, "nodes": 912},
            "shown": {"concepts": 12, "memories": len(mems), "nodes": 12 + len(mems)}, "budget": budget,
            "scanned": 900, "capped": False, "collapsed": False, "layer_counts": {"short": 120, "long": 780, "messages": 600}}


_DAILY = [d % 9 for d in range(30)]
_STATS = {"counted_at": 1793000000,
          "stores": [{"key": "memories", "total": 239, "week": 12, "daily": _DAILY,
                      "parts": {"concepts": 32, "relations": 446, "short": 14, "long": 225}},
                     {"key": "conversation", "total": 112, "since": 1792900000, "daily": _DAILY,
                      "parts": {"days": 9, "turns": 40}},
                     {"key": "messages", "total": 179456, "bytes": 91226112, "week": 3120, "daily": _DAILY,
                      "parts": {"telegram": 165511, "whatsapp": 13564, "email": 381}},
                     {"key": "files", "total": 1440, "bytes": 2254857830, "daily": _DAILY,
                      "types": {"images": {"n": 1013, "bytes": 170000000}, "videos": {"n": 300, "bytes": 2000000000},
                                "audio": {"n": 90, "bytes": 9000000}, "documents": {"n": 37, "bytes": 75857830}}},
                     {"key": "contacts", "total": 2}, {"key": "agenda", "total": 396,
                      "parts": {"meetings": 369, "todo": 1, "errands": 26}},
                     {"key": "apps", "total": 1932735, "unit": "bytes", "pending": False,
                      "apps": [{"key": "agenda", "title": "Agenda", "bytes": 1100000, "sheets": 0},
                               {"key": "results", "title": "", "bytes": 832735, "sheets": 98}]},
                     {"key": "rules", "total": 3}, {"key": "phrases", "total": 2453, "parts": {"paraphrases": 174}},
                     {"key": "events", "total": 17255, "week": 900, "daily": _DAILY}, {"key": "vault", "total": 0}]}
#: What an older or misbehaving server could still send for a concept: the viewer must never paint it.
_MEMORY_TEXT = "Quiere un road trip a Alsacia en diciembre."


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _api(route, asked: list):
    url = route.request.url
    asked.append(url)
    path = url.split("/api/memory/viewer/")[-1].split("?")[0]
    q = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")) if "?" in url else {}
    body = {"stats": _STATS, "cards": _cards(), "graph": _graph(int(q.get("budget", 300))),
            "timeline": {"days": [{"day": f"2026-10-{d:02d}", "own": d % 7, "messages": 3} for d in range(1, 27)]},
            "concept": {"key": q.get("key", ""), "label": q.get("key", ""), "count": 24, "short": 6, "last": 1793000000,
                        "related": [{"key": "finanzas", "count": 5}],
                        "items": [{"id": 9, "text": _MEMORY_TEXT, "kind": "intent",
                                   "level": "long", "source": "voice", "created": 1792900000}],
                        "more": True, "next": 9}}.get(path, {"items": [], "more": False, "next": 0})
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def _open(browser, port, *, width=1440, height=940, mutate=None, mutate_glob="**/components/memory/graph-view.js*"):
    pg = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    asked: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/memory/viewer/**", lambda r: _api(r, asked))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _ES})))
    if mutate:
        pg.route(mutate_glob, mutate)
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/components.css',
                         '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('es'); await i18n.applyLang('es');
        const store = await import('/frontend/app/core/store.js?v=2');
        const mm = await import('/frontend/app/components/MemoryMap.js?v=6');
        document.body.append(mm.MemoryMap());
        store.setMemOpen(true);
        window.__store = store;
    }""")
    pg.wait_for_selector(".memmap.open .mv-row", timeout=8000)
    pg._errors, pg._asked = errors, asked
    return pg


_PAINT = """() => {
  const c = document.querySelector('.mv-canvas'); const w = c.width, h = c.height;
  const d = c.getContext('2d').getImageData(0, 0, w, h).data;
  let x0 = w, y0 = h, x1 = -1, y1 = -1, n = 0;
  for (let y = 0; y < h; y += 2) for (let x = 0; x < w; x += 2) {
    if (d[(y * w + x) * 4 + 3] > 40) { n++; if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y; }
  }
  const r = c.getBoundingClientRect(), s = c.parentElement.getBoundingClientRect();
  return {w, h, x0, y0, x1, y1, n, canvas: [r.left, r.top, r.width, r.height], section: [s.left, s.top, s.width, s.height]};
}"""


def _graph_painted(pg) -> dict:
    pg.click(".mv-tabs .hb-tab[data-tab=graph]")
    pg.wait_for_selector(".mv-canvas-wrap[data-state=settled]", timeout=15000)
    pg.wait_for_timeout(120)                    # one animation frame after the last position
    return pg.evaluate(_PAINT)


def _assert_fills_and_centred(p: dict) -> None:
    assert p["n"] > 500, f"the graph painted almost nothing: {p}"
    assert all(abs(a - b) < 1 for a, b in zip(p["canvas"], p["section"])), f"the canvas is the size of its panel: {p}"
    cx, cy = (p["x0"] + p["x1"]) / 2 / p["w"], (p["y0"] + p["y1"]) / 2 / p["h"]
    assert abs(cx - 0.5) < 0.12 and abs(cy - 0.5) < 0.12, f"the graph is not centred in its panel: {cx:.2f},{cy:.2f} {p}"
    span = max((p["x1"] - p["x0"]) / p["w"], (p["y1"] - p["y0"]) / p["h"])
    assert span > 0.55, f"the graph does not fill its panel (span {span:.2f}): {p}"


#: Each store total the fixture carries, as the Spanish page prints it. Each must appear on the overview ONCE.
_TOTALS = ["239", "112", "179.456", "1440", "396", "17.255", "2453"]


def _overview_text(pg) -> str:
    return pg.locator(".mv-overview").inner_text()


def _duplicates(text: str) -> dict:
    import re
    return {n: c for n in _TOTALS if (c := len(re.findall(rf"(?<![\d.]){re.escape(n)}(?![\d.])", text))) != 1}


def test_the_overview_is_one_plain_page_that_says_each_figure_once(browser_and_port):
    b, port = browser_and_port
    pg = _open(b, port)
    assert pg.locator(".mv-tabs .hb-tab").all_inner_texts() == ["Resumen", "Tarjetas", "Grafo"]
    assert pg.locator(".mv-totals .mv-kpi").count() == 7
    assert pg.locator(".mv-act-col").count() == 30, "the activity chart has one column per day"
    assert "Viajes" in pg.locator(".mv-charts").inner_text(), "the concepts most present are listed"
    assert pg.locator(".mv-split > i").count() == 3, "the space is split between messages, files and apps"
    text = _overview_text(pg)
    assert "Telegram" in text and "165.511" in text and "Vídeos" in text, "the breakdown says what each store is made of"
    assert not _duplicates(text), f"a figure is printed more than once (or not at all): {_duplicates(text)}"
    # a plain page: the DOCUMENT scrolls, nothing is fixed, no inner scroller — a full-page capture stitches it
    flow = pg.evaluate("""() => ({doc: document.documentElement.classList.contains('mv-doc'),
        pos: getComputedStyle(document.querySelector('.memmap')).position,
        tall: document.documentElement.scrollHeight > window.innerHeight,
        scrollers: [...document.querySelectorAll('.memmap *')].filter((e) => { const o = getComputedStyle(e).overflowY;
          return (o === 'auto' || o === 'scroll') && e.scrollHeight > e.clientHeight + 1 && e.offsetParent; }).length})""")
    assert flow == {"doc": True, "pos": "absolute", "tall": True, "scrollers": 0}, flow
    pg.click(".mv-tabs .hb-tab[data-tab=graph]")
    assert pg.evaluate("() => document.documentElement.classList.contains('mv-doc')") is False, "the graph keeps the overlay"
    lower = text.lower()
    for word in ("dispositivo", "núcleos", "nodos", "navegador", "data\n"):
        assert word not in lower, f"the overview speaks of {word!r}"
    assert "null" not in lower and "undefined" not in lower
    assert not pg._errors, pg._errors
    pg.close()


def test_a_breakdown_that_repeats_a_total_is_caught(browser_and_port):
    """The disarm: serve overview.js with the messages panel printing the store total again — the check must see it."""
    b, port = browser_and_port
    src = (ENGINE / "frontend/app/components/memory/overview.js").read_text(encoding="utf-8")
    good = '.map(([k, v]) => row(platform(k), num(v), share(v, msg.total), ACCENT.messages)), "messages"),'
    assert src.count(good) == 1, "the line this disarm replaces moved — update the disarm"
    bad = src.replace(good, '.map(([k, v]) => row(platform(k), num(v), share(v, msg.total), ACCENT.messages))'
                            '.concat([row("total", num(msg.total))]), "messages"),')
    landed = []

    def mutate(route):
        landed.append(route.request.url)
        route.fulfill(status=200, content_type="text/javascript", body=bad)

    pg = _open(b, port, mutate=mutate, mutate_glob="**/components/memory/overview.js*")
    assert landed, "the mutated module was never served"
    assert "179.456" in _duplicates(_overview_text(pg))
    pg.close()


def test_the_graph_fills_its_panel_and_is_centred_on_a_desktop(browser_and_port):
    b, port = browser_and_port
    pg = _open(b, port)
    _assert_fills_and_centred(_graph_painted(pg))
    graph_calls = [u for u in pg._asked if "/viewer/graph" in u]
    assert graph_calls and all("budget=" in u for u in graph_calls), graph_calls
    assert "Viajes" in pg.locator(".mv-detail-title").inner_text(), "the biggest concept is selected"
    pg.wait_for_selector(".mv-related", timeout=5000)
    assert "Finanzas" in pg.locator(".mv-detail").inner_text(), "a concept shows what it is related to"
    assert "Alsacia" not in pg.locator(".memmap").inner_text(), "a memory's text is never painted"
    assert pg.evaluate("() => document.querySelector('.mv-canvas-wrap').dataset.nodes") == str(12 + 600)
    assert not pg._errors, pg._errors
    pg.close()


def test_the_graph_fills_its_panel_at_phone_width_without_a_horizontal_scroll(browser_and_port):
    b, port = browser_and_port
    pg = _open(b, port, width=375, height=812)
    _assert_fills_and_centred(_graph_painted(pg))
    assert any("budget=300" in u for u in pg._asked), "a phone asks for the phone's budget"
    over = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    assert over <= 0, f"the page scrolls sideways by {over}px at 375px"
    assert not pg._errors, pg._errors
    pg.close()


def test_the_device_tier_rule(browser_and_port):
    b, port = browser_and_port
    pg = b.new_page()
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    got = pg.evaluate("""async () => {
        const m = await import('/frontend/app/components/memory/budget.js?v=1');
        return [m.deviceTier({width: 375, deviceMemory: 4, hardwareConcurrency: 8}).tier,
                m.deviceTier({width: 1440, deviceMemory: 2, hardwareConcurrency: 8}).tier,
                m.deviceTier({width: 1440, deviceMemory: 8, hardwareConcurrency: 10}).tier,
                m.deviceTier({width: 1920}).tier,
                m.deviceTier({width: 2560, deviceMemory: 8, hardwareConcurrency: 12}).tier,
                m.deviceTier({width: 2560, deviceMemory: 8, hardwareConcurrency: 12}).nodes];
    }""")
    assert got == ["phone", "phone", "laptop", "laptop", "big", 3000], got
    pg.close()


def test_a_fit_that_ignores_the_panel_is_caught(browser_and_port):
    """The disarm: serve graph-view.js with the old placement (no centring) and the paint check must fail."""
    b, port = browser_and_port
    src = (ENGINE / "frontend/app/components/memory/graph-view.js").read_text(encoding="utf-8")
    good = "return { k, tx: W / 2 - ((box.x0 + box.x1) / 2) * k, ty: H / 2 - ((box.y0 + box.y1) / 2) * k };"
    assert src.count(good) == 1, "the fit this disarm replaces moved — update the disarm"
    # the reported symptom: the drawing anchored by its top-left corner at the panel's middle → bottom-right
    bad = src.replace(good, "return { k, tx: W / 2 - box.x0 * k, ty: H / 2 - box.y0 * k };")
    landed = []

    def mutate(route):
        landed.append(route.request.url)
        route.fulfill(status=200, content_type="text/javascript", body=bad)

    pg = _open(b, port, mutate=mutate)
    p = _graph_painted(pg)
    assert landed, "the mutated module was never served"
    with pytest.raises(AssertionError):
        _assert_fills_and_centred(p)
    pg.close()


# ── the layout worker: finite, and it STOPS ─────────────────────────────────────────────────────────────────
_WORKER = (ENGINE / "frontend/app/components/memory/force-worker.js").read_text(encoding="utf-8")
_SPLIT = "vx[i] += dx * f * (1 - b); vy[i] += dy * f * (1 - b); vx[j] -= dx * f * b; vy[j] -= dy * f * b;"
_RUN = """async (src) => {
  // A store's shape: 13 concepts with real-ish counts, every memory hanging from one to two of them.
  const counts = [287, 266, 230, 177, 166, 162, 161, 142, 126, 115, 101, 75, 20];
  const nodes = counts.map((c) => ({ hub: true, r: 9 + 17 * Math.sqrt(c / 287) }));
  const links = [];
  for (let a = 0; a < 13; a++) for (let b = a + 1; b < 13; b++) if ((a * 7 + b) % 3 === 0) links.push({ s: a, t: b, len: 150, k: 0.03 });
  let seed = 7; const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  for (let h = 0; h < 13; h++) for (let i = 0; i < counts[h]; i++) {
    const m = nodes.length; nodes.push({ hub: false, r: 2.6 + 3 * rnd() });
    links.push({ s: h, t: m, len: nodes[h].r + 26, k: 0.12 });
    if (rnd() < 0.3) links.push({ s: (h + 1 + Math.floor(rnd() * 12)) % 13, t: m, len: 140, k: 0.004 });
  }
  const w = new Worker(URL.createObjectURL(new Blob([src], { type: "text/javascript" })));
  const msgs = [];
  const done = new Promise((res) => { w.onmessage = (e) => { msgs.push(e.data); if (e.data.type === "settled") res(); }; });
  w.postMessage({ nodes, links });
  await Promise.race([done, new Promise((r) => setTimeout(r, 15000))]);
  await new Promise((r) => setTimeout(r, 300));          // nothing may arrive after «settled»
  w.terminate();
  const firstBad = msgs.findIndex((m) => Array.from(m.pos).some((v) => !Number.isFinite(v)));
  return { n: msgs.length, last: msgs.length ? msgs[msgs.length - 1].type : "", firstBad };
}"""


def _run_worker(browser, port, src):
    pg = browser.new_page()
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    got = pg.evaluate(_RUN, src)
    pg.close()
    return got


def test_the_layout_stays_finite_and_stops_when_it_settles(browser_and_port):
    """A hub with ~300 memories is the shape of a real store. The first layout pulled every hub with all of its
    springs at full strength: it overshot into Infinity within forty ticks, and the canvas refused to draw
    (measured on a real-ish store: `createRadialGradient … non-finite`). Now the pull is split by degree and the
    velocity is capped — and after «settled» the worker sends nothing more."""
    b, port = browser_and_port
    got = _run_worker(b, port, _WORKER)
    assert got["firstBad"] == -1, got
    assert got["last"] == "settled" and got["n"] < 200, got


def test_a_layout_that_pulls_a_hub_with_every_spring_at_once_is_caught(browser_and_port):
    """The disarm: the original spring (full force on both ends) and no velocity cap must go non-finite here."""
    b, port = browser_and_port
    assert _WORKER.count(_SPLIT) == 1, "the spring this disarm replaces moved — update the disarm"
    bad = _WORKER.replace(_SPLIT, "vx[i] += dx * f; vy[i] += dy * f; vx[j] -= dx * f; vy[j] -= dy * f;")
    lines = [ln for ln in bad.split("\n") if "< 400))" not in ln]
    assert len(lines) == len(bad.split("\n")) - 2, "the velocity cap this disarm removes moved"
    got = _run_worker(b, port, "\n".join(lines))
    assert got["firstBad"] >= 0, f"the disarmed layout stayed finite — the check proves nothing: {got}"


def test_the_cards_tab_paints_what_the_server_sent_and_says_how_much_more_there_is(browser_and_port):
    b, port = browser_and_port
    pg = _open(b, port)
    pg.click(".mv-tabs .hb-tab[data-tab=cards]")
    pg.wait_for_selector(".mv-cards .mm-node[data-mid]", timeout=8000)
    assert pg.locator(".mv-cards .mm-node[data-mid]").count() == 52, "12 short + 40 long, no more"
    heads = pg.locator(".mv-cards .mm-zcount").all_inner_texts()
    assert "40 / 5000" in heads, f"a capped layer says shown / total: {heads}"
    assert any("cards?" in u and "limit=" in u for u in pg._asked), "the device's row limit reaches the server"
    pg.click(".mv-cards .mm-mode:nth-child(2)")
    assert pg.locator(".mv-cards .mm-cnode").count() == 16, "one circle per concept, both layers"
    assert not pg._errors, pg._errors
    pg.close()


def test_the_graph_says_when_it_shows_only_its_top_level_and_saves_an_image(browser_and_port):
    b, port = browser_and_port
    pg = _open(b, port)
    _graph_painted(pg)
    assert "recuerdos" in pg.locator(".mv-showing").inner_text()
    with pg.expect_download(timeout=8000) as dl:
        pg.get_by_role("button", name="Imagen").click()
    assert dl.value.suggested_filename.endswith(".png")
    pg.route("**/api/memory/viewer/graph*", lambda r: r.fulfill(status=200, content_type="application/json",
             body=json.dumps({**_graph(300), "memories": [], "collapsed": True,
                              "shown": {"concepts": 12, "memories": 0, "nodes": 12}})))
    pg.click(".mv-seg button[data-days='7']")
    pg.wait_for_function("() => document.querySelector('.mv-showing').textContent.includes('nivel superior')",
                         timeout=8000)
    assert not pg._errors, pg._errors
    pg.close()
