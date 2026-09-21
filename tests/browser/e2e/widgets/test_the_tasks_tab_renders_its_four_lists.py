"""V2-728 — the «Tareas» tab RENDERS, with its four sub-tabs, and the counter counts his commissions.

Why a real browser and not a source-text contract. Everything about this tab is a wiring question between
four files — the store's one door that normalises the tab name, the CSS rule that decides whether the panel
is visible at all, the sub-tab bar, and the rail's counter — and every one of those fails the same way when
it is wrong: nothing errors, the panel is simply empty or invisible. A grep over the source cannot tell a
tab that shows from one whose `display` rule still names the class it had yesterday (V2-690: a computed
style does not prove something is painted, and a source string proves even less).

The api is stubbed at `window.fetch` so the four lists are DECIDED HERE: what is measured is that each
sub-tab asks for its own scope and paints what comes back, not what a live engine happens to be doing.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI(); app.include_router(pages.router); app.include_router(i18n_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

# The four lists the stub serves, one per scope. Deliberately different shapes: a live commission, a finished
# one with its outcome, a weekly job and a one-shot — the row for each is a different function.
ROWS = {
    "live": [{"id": "a1", "title": "piso de alquiler en Gràcia", "goal": "búscame piso", "kind": "web",
              "state": "running", "visible": True, "started_at": 1700000000, "phase": "revisando idealista",
              "pct": 40, "mode": "now"},
             {"id": "a2", "title": "mesa para 4 el sábado", "goal": "resérvame mesa", "kind": "encargo",
              "state": "waiting", "visible": True, "started_at": 1700000000,
              "phase": "esperando respuesta · quedan 2 h", "mode": "now"}],
    # …and one of the two finished rows HAS a stored report while the other does not (`has_results`), which
    # is what decides whether «Ver resultados» is drawn at all. Both shapes, because a button drawn always
    # and a button drawn never both pass a test that only looks at one row.
    "done": [{"id": "b1", "title": "informe de la empresa", "goal": "investígame esta empresa", "kind": "web",
              "state": "done", "visible": True, "finished_at": 1700000000, "has_results": True,
              "outcome": "5 fuentes, sin incidencias", "mode": "now"},
             {"id": "b2", "title": "entradas del concierto", "goal": "búscame entradas", "kind": "web",
              "state": "failed", "visible": True, "finished_at": 1700000000, "outcome": "agotadas",
              "has_results": False, "mode": "now"}],
    "recurring": [{"id": "c1", "title": "conciertos de Shakira", "goal": "avísame si hay concierto",
                   "kind": "web", "state": "pending", "visible": True, "mode": "recurring",
                   "schedule": {"display": "cada semana", "next_run": 1700600000, "type": "interval"}}],
    "scheduled": [{"id": "d1", "title": "llamar al dentista", "goal": "recuérdame llamar al dentista",
                   "kind": "reminder", "state": "pending", "visible": True, "mode": "scheduled",
                   "schedule": {"display": "2026-09-28 09:00", "next_run": 1701000000, "type": "once"}}],
}

# The stub. It RECORDS every scope asked for, so «the sub-tab fetches its own list» is measured and not assumed.
STUB = """(rows) => {
  window.__asked = [];
  window.__reopened = [];
  window.__opened = [];
  document.addEventListener('hb:open-card', e => window.__opened.push((e.detail || {}).id));
  const real = window.fetch.bind(window);
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (u.startsWith('/api/tasks')) {
      const sc = new URL(u, location.origin).searchParams.get('scope') || 'live';
      const all = new URL(u, location.origin).searchParams.get('all') === '1';
      window.__asked.push(sc + (all ? ':all' : ''));
      if (u.startsWith('/api/tasks/reopen')) {
        window.__reopened.push(JSON.parse((opts && opts.body) || '{}').id);
        return { ok: true, json: async () => ({ ok: true, instance: 'results::b1' }) };
      }
      return { ok: true, json: async () => ({ tasks: rows[sc] || [], scope: sc }) };
    }
    return real(url, opts);
  };
}"""

READ = """() => {
  const wall = document.querySelector('#chatwall, .chatwall');
  const cs = wall ? getComputedStyle(wall) : null;
  const panel = document.querySelector('.cw-tasks');
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect();
                      const s = getComputedStyle(el);
                      return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden'; };
  return {
    wallClass: wall ? wall.className : '',
    panelVisible: vis(panel),
    tabs: [...document.querySelectorAll('.cw-tab .cw-tab-label')].map(e => e.textContent.trim()),
    activeTab: (document.querySelector('.cw-tab.on .cw-tab-label') || {}).textContent || '',
    subtabs: [...document.querySelectorAll('.cw-subtab')].map(e => e.textContent.trim()),
    activeSub: (document.querySelector('.cw-subtab.on') || {}).textContent || '',
    rowTitles: [...document.querySelectorAll('.cw-tasklist .cw-proc-goal')].map(e => e.textContent.trim()),
    rowNotes: [...document.querySelectorAll('.cw-tasklist .cw-proc-note')].map(e => e.textContent.trim()),
    rowMetas: [...document.querySelectorAll('.cw-tasklist .cw-proc-meta')].map(e => e.textContent.trim()),
    glyphs: [...document.querySelectorAll('.cw-tasklist .cw-proc-dot')].map(e => e.textContent.trim()),
    empty: (document.querySelector('.cw-tasks .cw-empty') || {}).textContent || '',
    railCount: (document.querySelector('.wr-proc-n') || {}).textContent || '',
    asked: window.__asked || [],
    resultBtns: [...document.querySelectorAll('.cw-tasklist .cw-proc-row.hist .cron-b')].map(e => e.textContent.trim()),
    reopened: window.__reopened || [],
    opened: window.__opened || [],
    // V2-738 — the form for creating one BY HAND lives under these two sub-tabs, and it is the one piece of
    // this panel that is not a list. Counted rather than assumed: it is built by a conditional whose two
    // branches look identical from the source.
    cronInputs: document.querySelectorAll('.cw-tasks .cron-add .cron-in').length,
    cronButton: !!document.querySelector('.cw-tasks .cron-create'),
    // …and the failure mode that put this here: a function handed to the DOM layer where a node was expected
    // is converted with String(), so the panel paints its SOURCE CODE. Nothing throws, so `errors` stays
    // empty and every list above still passes — the operator is the one who finds it, on screen.
    sourceLeak: (() => {
      const txt = ((panel && panel.innerText) || '');
      // Two signatures that cannot occur in a task's title, note or cadence but appear in the FIRST LINE of
      // any of this file's render functions: an arrow, and a call to the hyperscript factory.
      const m = txt.match(/(\\(\\s*\\)\\s*=>|\\bh\\(\"\\w)[^]{0,100}/);
      return m ? m[0].replace(/\\s+/g, ' ') : '';
    })(),
  };
}"""


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def run():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
        except OSError:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate(); pytest.skip("preview server never came up")
    time.sleep(1.0)
    yield f"http://127.0.0.1:{port}/"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


@pytest.fixture(scope="module")
def seen(run):
    """One browser, one pass through the four sub-tabs, reading the DOM after each."""
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        pg = b.new_context(viewport={"width": 1280, "height": 800}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(run, wait_until="domcontentloaded")
        pg.wait_for_timeout(2200)
        pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
        pg.evaluate(STUB, ROWS)

        # The OLD name arrives — from the voice router, the action map, or a stored localStorage tab. It has
        # to land on «Tareas», which is the whole reason the store normalises instead of each caller.
        pg.evaluate("""async () => {
          const s = await import('/static/app/core/store.js?v=2');
          s.setChatTab('procesos'); s.setChatOpen(true);
        }""")
        pg.wait_for_timeout(700)
        out["live"] = pg.evaluate(READ)

        for scope in ("done", "recurring", "scheduled"):
            pg.evaluate("""async (sc) => {
              const s = await import('/static/app/core/store.js?v=2');
              s.setTaskScope(sc); await s.fetchTaskScope(sc);
            }""", scope)
            pg.wait_for_timeout(400)
            out[scope] = pg.evaluate(READ)
            if scope == "done":
                # …and the button is CLICKED, because a drawn button that calls nothing looks identical.
                btn = pg.query_selector(".cw-tasklist .cw-proc-row.hist .cron-b")
                if btn:
                    btn.click()
                    pg.wait_for_timeout(300)
                out["done"]["reopened"] = pg.evaluate("() => window.__reopened || []")
                out["done"]["opened"] = pg.evaluate("() => window.__opened || []")

        # …and an empty list must SAY something rather than leave a blank panel. Emptied at the SERVER and
        # then refetched, not by writing the signal: an effect refreshes the visible scope whenever the live
        # set changes, so a store written by hand is repopulated before anything is painted — which is how
        # this very case first passed against a list it had not actually emptied.
        pg.evaluate(STUB, {"live": [], "done": [], "recurring": [], "scheduled": []})
        pg.evaluate("""async () => {
          const s = await import('/static/app/core/store.js?v=2');
          s.setTaskScope('live'); await s.fetchTaskScope('live');
        }""")
        pg.wait_for_timeout(400)
        out["blank"] = pg.evaluate(READ)
        out["errors"] = errors
        b.close()
    return out


# ── it is THERE, and it is the tab the old name asks for ────────────────────────────────────────────────
def test_the_page_has_no_errors(seen):
    assert seen["errors"] == [], seen["errors"]


def test_the_old_name_lands_on_the_new_tab(seen):
    """`setChatTab('procesos')` — what the voice router still answers — must open «Tareas», not «Chat»."""
    assert "tab-tareas" in seen["live"]["wallClass"], seen["live"]["wallClass"]


def test_the_panel_is_actually_PAINTED(seen):
    """The CSS rule names the panel's class. Rename one and not the other and the tab exists, is selected,
    and shows nothing — with no error anywhere. That is what this line is for."""
    assert seen["live"]["panelVisible"], json.dumps(seen["live"])[:400]


def test_there_are_four_top_tabs_and_crons_is_not_one_of_them(seen):
    tabs = [x.lower() for x in seen["live"]["tabs"]]
    assert len(tabs) == 4, tabs
    assert any("tarea" in x or "task" in x for x in tabs), tabs
    assert not any(x.startswith("cron") for x in tabs), tabs


def test_the_four_sub_tabs_are_rendered_in_order(seen):
    """Four buttons AND four names. Counting nodes alone passes on four blank labels, which is exactly what
    a missing i18n key produces — `t()` answers "" and the bar renders as four empty boxes."""
    subs = [x for x in seen["live"]["subtabs"] if x != "⚙"]
    assert len(subs) == 4, subs
    assert all(x.strip() for x in subs), f"a sub-tab rendered with no label: {subs}"
    assert len(set(subs)) == 4, f"two sub-tabs share a label: {subs}"
    assert seen["live"]["activeSub"].strip() and seen["live"]["activeSub"] in subs


# ── each sub-tab asks for ITS OWN list and paints it ────────────────────────────────────────────────────
def test_each_sub_tab_fetches_its_own_scope(seen):
    asked = seen["scheduled"]["asked"]
    for scope in ("live", "done", "recurring", "scheduled"):
        assert scope in asked, f"nobody ever asked for the «{scope}» list: {asked}"


def test_the_live_list_shows_what_is_running_with_its_hour(seen):
    titles = seen["live"]["rowTitles"]
    assert "piso de alquiler en Gràcia" in titles, titles
    assert "mesa para 4 el sábado" in titles, titles
    assert any("desde" in m or "since" in m.lower() for m in seen["live"]["rowMetas"]), seen["live"]["rowMetas"]


def test_a_finished_task_says_HOW_it_ended_and_a_failure_is_not_a_tick(seen):
    """The outcome line is the thing a finished row was missing — and ✕ must not be ✓."""
    assert "5 fuentes, sin incidencias" in seen["done"]["rowNotes"], seen["done"]["rowNotes"]
    assert "agotadas" in seen["done"]["rowNotes"], seen["done"]["rowNotes"]
    assert "✓" in seen["done"]["glyphs"] and "✕" in seen["done"]["glyphs"], seen["done"]["glyphs"]


def test_only_a_finished_task_WITH_a_report_offers_to_reopen_it(seen):
    """«Se va a esa lista, le da el botón y ve los datos derivados» (operator, 2026-09-20).

    ONE button for two finished rows: the one whose report was kept. A button that opens nothing is worse
    than no button, and before the task owned its result that was every older row — the 8-sheet cap had
    already deleted it. Drawn off `has_results`, which the board answers per row."""
    btns = seen["done"]["resultBtns"]
    assert len(btns) == 1, f"one row has a report and the other does not; buttons drawn: {btns}"
    assert btns[0].strip(), "the button has no label — a missing i18n key renders as an empty button"


def test_and_clicking_it_asks_the_server_to_reopen_THAT_task(seen):
    """The other half. A rendered button that calls nothing looks exactly like one that works, which is the
    V2-690 lesson with a mouse: it is clicked here, and what the page SENT is what is asserted."""
    assert seen["done"].get("reopened") == ["b1"], (
        f"the click did not reach POST /api/tasks/reopen with the row's own id: {seen['done'].get('reopened')}")
    # …and the CARD is asked for. The server deliberately emits no `show` (a click is the operator's hands,
    # and the presentation door collapses `results::b1` and `results::b2` into one «results», which would
    # suppress the second report while the first is open). The wall asks the desktop through the house
    # `hb:*` document event instead — asserted here, because a POST that opens nothing is a dead button
    # with a green network tab.
    assert seen["done"].get("opened") == ["results::b1"], (
        f"the reply came back and no card was asked for: {seen['done'].get('opened')}")


def test_a_recurring_task_shows_its_cadence_and_its_next_moment(seen):
    """«¿sigue esto en pie, y cuándo?» is the only pair of facts a periodic row has to answer."""
    assert "conciertos de Shakira" in seen["recurring"]["rowTitles"], seen["recurring"]["rowTitles"]
    meta = " ".join(seen["recurring"]["rowMetas"])
    assert "cada semana" in meta, meta
    assert "róxima" in meta or "next" in meta.lower(), meta


def test_a_scheduled_task_waits_in_its_own_list(seen):
    """A one-shot is NOT a cron. Until these were two lists there was no way to ask for this one."""
    assert seen["scheduled"]["rowTitles"] == ["llamar al dentista"], seen["scheduled"]["rowTitles"]
    assert "conciertos de Shakira" not in seen["scheduled"]["rowTitles"]


def test_an_empty_list_says_so_instead_of_showing_a_blank_panel(seen):
    assert seen["blank"]["empty"].strip(), "an empty sub-tab shows nothing at all"
    assert seen["blank"]["rowTitles"] == []


# ── the counter counts HIS commissions ──────────────────────────────────────────────────────────────────
def test_the_rail_counter_matches_the_live_list(seen):
    assert seen["live"]["railCount"] == "2", seen["live"]["railCount"]


# ── V2-738: the panel that paints its own source ────────────────────────────────────────────────────────
# What the operator saw on 2026-09-21 02:22, on the «En curso» sub-tab, filling the bottom of the panel:
#
#     () => (store.taskScope() === "recurring" || store.taskScope() === "scheduled" ? h("div", { class: …
#
# `dom.js` accepts a function as a child and treats it as a reactive binding — but only as a DIRECT child of
# `h()`. Returned inside an ARRAY from a reactive child, each item goes through `toNode`, whose last line is
# `document.createTextNode(String(v))`: a function becomes its own source. It throws nothing, it logs nothing,
# and every assertion above this line stayed green while it was on his screen.
def test_the_panel_never_paints_its_own_source(seen):
    for scope in ("live", "done", "recurring", "scheduled", "blank"):
        assert not seen[scope]["sourceLeak"], (
            f"the «{scope}» sub-tab is painting JavaScript at the operator: {seen[scope]['sourceLeak']!r}. "
            "A function reached the DOM layer where a node was expected and was String()-ed.")


def test_creating_a_periodic_task_BY_HAND_is_reachable(seen):
    """And the other half of the same defect: what the stringified function was SUPPOSED to build. The form
    is offered only under the two sub-tabs that have a clock, which is why «it is drawn» and «it is drawn in
    the right place» are one assertion and not two."""
    for scope in ("recurring", "scheduled"):
        assert seen[scope]["cronInputs"] == 3, (
            f"«{scope}» must offer when / name / prompt, got {seen[scope]['cronInputs']} fields")
        assert seen[scope]["cronButton"], f"«{scope}» draws no button to create it"
    for scope in ("live", "done"):
        assert seen[scope]["cronInputs"] == 0, f"«{scope}» has no clock and must not offer a schedule form"
