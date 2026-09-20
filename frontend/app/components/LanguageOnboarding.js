// LanguageOnboarding — the first-run language picker (V2-101, redesigned by V2-672). Sits ABOVE the boot
// veil (z-index above .boot-ovl's 100010) and follows it: main.js opens this one only once store.bootReady()
// is true AND GET /api/i18n/state says no language has EVER been explicitly chosen (`chosen:false`).
//
// THE SCREEN CARRIES NO WORDS OF OURS, and that is the whole design. It used to read «Hi! What language
// would you like to use?» while the agent asked the same thing OUT LOUD in English — so the one sentence
// somebody could not understand was the one asking which language they understand. The operator's brief:
// *«pondría un símbolo de una persona hablando para que alguien que no es capaz de leer lo que pone en la
// pantalla entienda que tiene que seleccionar el país, y debajo la bandera y el nombre del idioma»*. The
// speaking mark says what the screen is for; every row is a flag plus the language's own native name, which
// is the only label its speaker is guaranteed to read. The agent stays SILENT until a language exists
// (voice/engine/pipeline/agent.py's onboarding branch).
//
// The rows come from GET /api/i18n/state's `picker` (i18n/catalog.py) — the two we SHIP first, the rest
// alphabetical by native name. A spoken answer still works: the mic is live and the server classifies it the
// same as any turn (i18n/init/detect.py), which is why this modal is an escape hatch and not the only door.
//
// Phases (store.langOnboardPhase): "ask" → "detected" → "ready". The phase is the ENGINE's account of
// where the language is; what is on the card is decided by `view()` below, and since V2-732 the two are
// not the same thing — a language that is already initialized runs through all three phases without ever
// drawing a preparing screen, because there is nothing to prepare.
//
// Once a language is chosen the bundle and the alias pack generate in the background — instant for en/es, a
// real wait for anything else. V2-672 puts the SECOND question in that gap, which is the operator's own
// sequencing: *«eso podría ser el paso número dos, en el idioma correspondiente… y eso sucedería mientras se
// está haciendo la traducción»*. So the wait is spent asking where his files should live (self-host only —
// a cloud account's Volume IS the storage) instead of watching a spinner, and its words arrive ALREADY
// TRANSLATED on the same SSE event (i18n/init/detect.py's priority pass).
//
// Which means "ready" can no longer close this on its own: it may land with an unanswered question on
// screen. The veil closes when the language is ready AND nothing is still asking — `store.holdLangOnboard`
// is the second half of that handshake.
import { h } from "../core/dom.js?v=2";
import { createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/language-onboarding-api.js?v=1";

// A person speaking. Not a globe and not a flag: the screen is asking you to pick the language you SPEAK,
// and a globe reads as "worldwide" rather than as an instruction.
const SPEAKING_ICON = `<svg viewBox="0 0 48 48" width="56" height="56" fill="none" stroke="currentColor"
  stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <circle cx="19" cy="14" r="6.5"/>
  <path d="M7.5 34c0-5.8 5.1-9.5 11.5-9.5s11.5 3.7 11.5 9.5v5.5h-23z"/>
  <path d="M35.5 15.5c2.2 2.2 2.2 6.8 0 9"/>
  <path d="M40 11c4.2 4.2 4.2 13.8 0 18"/>
</svg>`;

// Fallback rows if /api/i18n/state could not be read at all: the two languages the product ships. Better a
// two-row picker than a blocking modal with nothing in it — this veil is in front of the whole UI.
const FALLBACK = [
  { code: "en", native: "English", flag: "\u{1F1FA}\u{1F1F8}", pinned: true },
  { code: "es", native: "Español", flag: "\u{1F1EA}\u{1F1F8}", pinned: true },
];

// A folder. Same language as the speaking mark: a picture, so the step reads before its words do.
const FOLDER_ICON = `<svg viewBox="0 0 48 48" width="44" height="44" fill="none" stroke="currentColor"
  stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M5 14a3 3 0 0 1 3-3h10l4 5h15a3 3 0 0 1 3 3v18a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3z"/>
</svg>`;

export function LanguageOnboarding() {
  let filterEl, pathEl;
  const [busy, setBusy] = createSignal(false);
  const [rows, setRows] = createSignal(FALLBACK);
  const [filter, setFilter] = createSignal("");
  const [folder, setFolder] = createSignal(null);     // null = not asked yet / not applicable
  const [problem, setProblem] = createSignal("");
  // V2-730 — which row wears the accent. ONE, always: the language the engine is actually running in
  // ("en" until /api/i18n/state says otherwise). Until this signal existed the accent was baked into
  // `.pinned`, so the first screen of a fresh install showed English AND Spanish already chosen, and
  // there was no way to tell which one a click had just changed.
  const [active, setActive] = createSignal("en");

  // The catalog is fetched once, when the component is built. main.js only mounts this after bootReady(),
  // and the same endpoint already had to answer for the modal to open at all.
  fetch("/api/i18n/state", { cache: "no-store" })
    .then(r => r.json())
    .then(s => {
      if (s && Array.isArray(s.picker) && s.picker.length) setRows(s.picker);
      // V2-734 — the row is a regional variant now, so the mark follows the full code («en-GB»), and the
      // region comes from the same answer rather than being guessed from the language.
      if (s && s.active) setActive(String(s.active).toLowerCase() + (s.region ? "-" + s.region : ""));
    })
    .catch(() => {});

  // The early strings travel with the SSE "detected" event, already in the chosen language. `k` is the
  // fallback so a generation that failed shows the key's English rather than an empty button.
  const s = (key, fallbackText) => (store.langOnboardStrings() || {})[key] || fallbackText;

  const pick = async (code) => {
    if (busy()) return;
    setActive(code);                                  // the mark follows the finger, not the round-trip
    setBusy(true);
    await api.chooseLanguage(code).catch(() => {});
    setBusy(false);
    // Ask the SERVER whether this deployment may choose a folder at all — a cloud account may not, and the
    // answer also says whether a native picker can be drawn on this machine. Holding the veil BEFORE the
    // answer arrives is deliberate: the "ready" event can beat this round-trip on a preset language.
    store.holdLangOnboard(true);
    const st = await fetch("/api/library/base", { cache: "no-store" }).then(r => r.json()).catch(() => null);
    if (st && st.ok && st.can_choose) setFolder(st);
    else store.holdLangOnboard(false);                // nothing to ask — the language's own readiness decides
  };

  const saveFolder = async (path) => {
    setBusy(true);
    const res = await fetch("/api/library/base", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base: path }),
    }).then(r => r.json()).catch(() => ({ ok: false }));
    setBusy(false);
    if (!res.ok) { setProblem(s("onboarding.folder.problem", "That folder cannot be used.")); return; }
    setProblem("");
    store.holdLangOnboard(false);
  };

  const browseFolder = async () => {
    setBusy(true);
    const res = await fetch("/api/library/base/browse", { method: "POST" })
      .then(r => r.json()).catch(() => ({ ok: false, reason: "unavailable" }));
    setBusy(false);
    if (res.ok && res.path) return saveFolder(res.path);
    // "cancelled" is an answer, not a failure — he opened the picker and closed it. Only a real problem
    // with a folder is worth a message; anything else leaves the typed field as the way through.
    if (res.reason && res.reason !== "cancelled" && res.reason !== "unavailable") {
      setProblem(s("onboarding.folder.problem", "That folder cannot be used."));
    }
  };

  const folderView = () => {
    const st = folder() || {};
    return h("div", { class: "lang-onb-folder" },
      h("div", { class: "lang-onb-mark", html: FOLDER_ICON }),
      h("div", { class: "lang-onb-ftitle" }, s("onboarding.folder.title", "Where should your files go?")),
      h("div", { class: "lang-onb-fhint" }, s("onboarding.folder.hint", "")),
      h("div", { class: "lang-onb-fpath" }, st.root || ""),
      h("div", { class: "lang-onb-search" },
        h("input", {
          class: "lang-onb-input", ref: el => (pathEl = el), "aria-label": "folder",
          onKeydown: e => {
            if (e.key !== "Enter") return;
            e.preventDefault();
            const v = (pathEl?.value || "").trim();
            if (v) saveFolder(v);
          },
        }),
      ),
      () => (problem() ? h("div", { class: "lang-onb-fproblem" }, problem()) : null),
      h("div", { class: "lang-onb-factions" },
        st.has_dialog
          ? h("button", { class: "lang-onb-fbtn primary", disabled: () => busy(), onClick: browseFolder },
              s("onboarding.folder.choose", "Choose a folder"))
          : h("button", {
              class: "lang-onb-fbtn primary", disabled: () => busy(),
              onClick: () => { const v = (pathEl?.value || "").trim(); if (v) saveFolder(v); },
            }, s("onboarding.folder.choose", "Choose a folder")),
        h("button", {
          class: "lang-onb-fbtn ghost", disabled: () => busy(),
          onClick: () => { setProblem(""); store.holdLangOnboard(false); },
        }, s("onboarding.folder.skip", "Skip")),
      ),
    );
  };

  // Typing FILTERS the list rather than submitting free text. The old typed fallback ran the server's
  // language classifier over whatever was written, which needed a prompt telling you to write something —
  // in a language you may not read. Narrowing 40 rows to the one you recognise needs no instructions.
  const matches = () => {
    const q = filter().trim().toLowerCase();
    const all = rows();
    if (!q) return all;
    return all.filter(r => (r.native || "").toLowerCase().includes(q) ||
                           (r.name || "").toLowerCase().includes(q) ||
                           (r.code || "").toLowerCase() === q);
  };

  // Which row wears the mark. The active language may be a bare code («en») while every row it could
  // match is a variant («en-US», «en-GB»): on a fresh install nobody has chosen a region yet, and marking
  // nothing at all is how V2-730's fix would quietly come undone. So an exact match wins, and failing
  // that the language's FIRST variant carries it — which is also the one whose voice is the default.
  const markedCode = () => {
    const want = String(active() || "").toLowerCase();
    const all = rows();
    if (all.some(r => String(r.code).toLowerCase() === want)) return want;
    const base = want.split("-")[0];
    const hit = all.find(r => String(r.base || r.code).toLowerCase() === base);
    return hit ? String(hit.code).toLowerCase() : want;
  };

  const row = (r) => h("button", {
    // A function, so moving the mark repaints two borders instead of re-rendering forty rows.
    class: () => "lang-onb-row" + (r.pinned ? " pinned" : "") +
                 (markedCode() === String(r.code).toLowerCase() ? " sel" : ""),
    disabled: () => busy(),
    lang: r.code,
    "aria-pressed": () => (markedCode() === String(r.code).toLowerCase() ? "true" : "false"),
    title: r.name || r.native,
    onClick: () => pick(r.code),
  },
    h("span", { class: "lang-onb-flag" }, r.flag || ""),
    h("span", { class: "lang-onb-name" }, r.native || r.code),
  );

  const askView = () => {
    const all = matches();
    const pinned = all.filter(r => r.pinned);
    const rest = all.filter(r => !r.pinned);
    return h("div", { class: "lang-onb-ask" },
      // `html`, not `innerHTML`: dom.js's h() knows the prop by that name and would set any other spelling
      // as a plain ATTRIBUTE — the mark rendered as nothing at all, which the rendered test caught and a
      // source read never would have.
      h("div", { class: "lang-onb-mark", html: SPEAKING_ICON }),
      pinned.length ? h("div", { class: "lang-onb-pinned" }, ...pinned.map(row)) : null,
      pinned.length && rest.length ? h("div", { class: "lang-onb-sep" }) : null,
      h("div", { class: "lang-onb-search" },
        h("span", { class: "lang-onb-mag" }, "\u{1F50D}"),
        h("input", {
          class: "lang-onb-input", ref: el => (filterEl = el), "aria-label": "filter",
          onInput: () => setFilter(filterEl ? filterEl.value : ""),
          onKeydown: e => {
            if (e.key !== "Enter") return;
            e.preventDefault();
            const only = matches();
            if (only.length === 1) pick(only[0].code);
          },
        }),
      ),
      h("div", { class: "lang-onb-list" }, ...rest.map(row)),
    );
  };

  // V2-731 — how full the bar is. The server counts its OWN steps (bundle, alias pack, phrasebook) and
  // sends them; `null` means it said nothing, and then the bar sweeps instead of inventing a number.
  // "ready" is 100 by definition — the last step and the ready event are the same instant, and a bar that
  // stops at two thirds on a screen that says it is done is a screen that lies.
  const pct = () => {
    if (store.langOnboardPhase() === "ready") return 100;
    const p = store.langOnboardProgress();
    if (!p || !(p.total > 0)) return null;
    return Math.max(8, Math.min(100, Math.round((p.done / p.total) * 100)));
  };

  // The spinner it replaces said only «something is happening», and for a preset language it said it for
  // about 200 ms. The operator: *«si hay un loader o una pantalla tiene que tener un progress bar o algo,
  // pero como mínimo debe durar dos segundos para que la gente lo vea»*. The floor is the store's
  // (LANG_LOADER_FLOOR_MS); this is the part he can read while it lasts.
  const loadingView = () => h("div", { class: "lang-onb-loading" },
    h("div", { class: "lang-onb-loading-text" }, () => store.langOnboardLoading() || "…"),
    h("div", { class: () => "lang-onb-bar" + (pct() === null ? " indet" : "") },
      h("div", { class: "lang-onb-bar-fill",
                 style: { width: () => (pct() === null ? "" : pct() + "%") } }),
    ),
  );

  // V2-732 — WHAT IS ON THE CARD, in order of who has the better claim to it.
  //
  // The order used to be keyed on the PHASE, which meant the folder question could only appear once the
  // engine had said "detected" — an accident, not a rule — and, worse, that anything past "ask" fell
  // through to the preparing screen. An already-initialized language has nothing to prepare, so that
  // screen had nothing to say and said it anyway. Now: the question if it is ours to ask, the preparing
  // screen only when there is real work to watch, and otherwise the picker he is already looking at, with
  // his choice marked, until the veil fades. Nothing new is ever shown for nothing.
  const view = () => {
    if (store.langOnboardHold() && folder()) return folderView();
    if (store.langOnboardPreparing()) return loadingView();
    return askView();
  };

  return h("div", {
    class: () => "lang-onb" + (store.langOnboardOpen() ? " open" : "") +
                 // NOT `phase === "ready"` alone: a bundle finishing while the folder question is on screen
                 // would fade the card out from under it.
                 (store.langOnboardPhase() === "ready" && !store.langOnboardHold() ? " gone" : ""),
    "aria-hidden": "true",
  },
    h("div", { class: "lang-onb-card" }, view),
  );
}
