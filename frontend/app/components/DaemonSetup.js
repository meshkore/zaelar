// DaemonSetup — the full-screen surface behind the 🖥 icon (V2-575 · P1).
//
// It answers three different questions depending on where it is opened, and they are genuinely different
// screens rather than one screen with fields greyed out:
//
//   CONNECTED    which folders may Zaelar read, and how to change that. The only destructive control here is
//                "stop reading this folder", which is the safe direction.
//   NOT THERE    here is the installer for your computer, and here is the one command that installs it. The
//                screen then waits: `services/daemon.js` polls, and the moment the daemon answers this turns
//                into the connected screen on its own. Nobody has to press "check again" — that button exists
//                anyway, because a person watching a screen that says "waiting" wants something to press.
//   FROM CLOUD   the daemon runs on the user's own computer and a cloud engine cannot reach it. The download
//                is still the useful thing, and it is said plainly rather than dressed up.
//
// WHY A FULL SCREEN AND NOT A MODAL, copying `LanguageOnboarding.js` rather than `WizardModal.js`: this asks
// somebody to grant access to their documents. A dialog that vanishes when you click slightly off it is the
// wrong instrument for that — half-granted permissions are exactly the state the permission circuit exists to
// avoid. It closes on the ✕ and on Escape, both deliberate gestures.
//
// EVERY REFUSAL IS SHOWN WITH THE DAEMON'S OWN WORDS. `daemon/fs/roots.py` goes to real trouble to say "that
// is your entire home folder — choose the folders you actually want me to work with", and replacing that with
// "could not add folder" would throw away the only part the user can act on.
import { h, raw } from "../core/dom.js?v=2";
import { createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import * as daemon from "../services/daemon.js?v=1";
import { t } from "../core/i18n.js?v=1";
import { CLOSE_ICON, REFRESH_ICON, DESKTOP_ICON } from "../lib/icons.js?v=2";

// The poll starts with the surface, which is mounted for the whole life of the page (system-surfaces.js) —
// the icon has to be coloured correctly whether or not anybody ever opens this screen.
daemon.start();

const PLATFORM_LABEL = { macos: "macOS", windows: "Windows" };

// The install command, per platform. It is shown as text to copy rather than run for the user, because the
// one thing this screen must never do is make an executable land and run without the person choosing it.
function installCommand(platform) {
  if (platform === "windows") {
    return 'powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\\Downloads\\zaelar-daemon-install-windows.ps1"';
  }
  return 'bash ~/Downloads/zaelar-daemon-install-macos.sh';
}

export function DaemonSetup() {
  const [problem, setProblem] = createSignal("");
  const [busy, setBusy] = createSignal("");
  const [chosen, setChosen] = createSignal("");      // which platform's instructions are showing
  let pathEl;

  const close = () => { store.setDaemonSetupOpen(false); setProblem(""); };

  // Escape closes. Registered once on the window rather than on the overlay, because the overlay does not
  // hold focus when the user has been typing into the path field.
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && store.daemonSetupOpen()) close();
  });

  const act = async (fn, path) => {
    if (!path) return;
    setBusy(path); setProblem("");
    const r = await fn(path);
    setBusy("");
    if (!r.ok) setProblem(r.message || t("daemon.err.generic"));
    else if (pathEl) pathEl.value = "";
  };

  const platform = () => chosen() || (daemon.status() || {}).platform || "macos";

  // ── the download block, shared by the "not there" and "from cloud" screens ──────────────────────────────
  const downloads = () => {
    const all = daemon.platforms();
    const names = Object.keys(all);
    if (!names.length) return h("p", { class: "dsx-note" }, () => t("daemon.download.unavailable"));
    return h("div", { class: "dsx-dl" },
      h("div", { class: "dsx-dl-row" }, ...names.map((name) =>
        h("a", {
          class: () => "dsx-dl-btn" + (platform() === name ? " on" : ""),
          href: all[name].artifact, download: "",
          onClick: () => { setChosen(name); api.uiEvent("daemon:download", { platform: name }); },
        }, PLATFORM_LABEL[name] || name))),
      h("ol", { class: "dsx-steps" },
        h("li", {}, () => t("daemon.step.download"),
          h("a", { class: "dsx-link", href: () => (all[platform()] || {}).installer || "#", download: "" },
            () => t("daemon.step.installer"))),
        h("li", {}, () => t("daemon.step.run"),
          h("code", { class: "dsx-cmd" }, () => installCommand(platform()))),
        h("li", {}, () => t("daemon.step.wait"))),
      h("p", { class: "dsx-note" }, () => t("daemon.note.noadmin")),
      h("p", { class: "dsx-note" }, () => t("daemon.note.checksums"),
        h("a", { class: "dsx-link", href: () => (all[platform()] || {}).checksums || "#" },
          () => t("daemon.note.checksums_link"))),
    );
  };

  // ── connected: the folders ──────────────────────────────────────────────────────────────────────────────
  const folders = () => {
    const s = daemon.status() || {};
    const roots = s.roots || [];
    const candidates = (s.candidates || []).filter((c) => !c.allowed);
    return h("div", { class: "dsx-folders" },
      h("h3", { class: "dsx-h3" }, () => t("daemon.folders.title")),
      h("p", { class: "dsx-note" }, () => t("daemon.folders.body")),
      roots.length
        ? h("ul", { class: "dsx-list" }, ...roots.map((path) =>
            h("li", { class: "dsx-item" },
              h("span", { class: "dsx-path" }, path),
              h("button", {
                class: "dsx-mini", disabled: () => busy() === path,
                onClick: () => act(daemon.revoke, path),
              }, () => t("daemon.folders.revoke")))))
        : h("p", { class: "dsx-empty" }, () => t("daemon.folders.none")),
      candidates.length
        ? h("div", { class: "dsx-cands" },
            h("p", { class: "dsx-note" }, () => t("daemon.folders.suggested")),
            h("div", { class: "dsx-dl-row" }, ...candidates.map((c) =>
              h("button", {
                class: "dsx-chip", disabled: () => busy() === c.path,
                onClick: () => act(daemon.grant, c.path),
              }, "+ " + (c.label || c.path)))))
        : null,
      h("div", { class: "dsx-add" },
        h("input", { class: "dsx-input", type: "text", ref: (el) => (pathEl = el),
                     placeholder: () => t("daemon.folders.placeholder") }),
        h("button", { class: "dsx-btn",
                      onClick: () => act(daemon.grant, (pathEl && pathEl.value || "").trim()) },
          () => t("daemon.folders.add"))),
    );
  };

  // ── the three screens ───────────────────────────────────────────────────────────────────────────────────
  const body = () => {
    const s = daemon.status();
    if (!s) return h("p", { class: "dsx-note" }, () => t("daemon.loading"));
    if (s.state === "remote") {
      return h("div", {},
        h("p", { class: "dsx-lead" }, () => t("daemon.remote.lead")),
        // Said out loud rather than implied. The daemon gives files and a real browser to the Zaelar running
        // on that same computer; wiring it to a CLOUD agent is the relay, and it is not built. Shipping a
        // download whose screen implies otherwise is how a product earns "it doesn't work".
        h("p", { class: "dsx-warn" }, () => t("daemon.remote.limit")),
        downloads());
    }
    if (!s.reachable) {
      return h("div", {},
        h("p", { class: "dsx-lead" }, () => t("daemon.absent.lead")),
        downloads(),
        h("p", { class: "dsx-waiting" }, () => t("daemon.absent.waiting")));
    }
    return h("div", {},
      h("p", { class: "dsx-lead" }, () => t("daemon.ok.lead")),
      () => s.outdated
        ? h("p", { class: "dsx-warn" }, () => t("daemon.ok.outdated"), " ",
            h("span", { class: "dsx-mono" }, () => `${s.version} → ${s.expected_version}`))
        : null,
      folders());
  };

  return h("div", { class: () => "ovl dsx-ovl" + (store.daemonSetupOpen() ? " on" : "") },
    h("div", { class: "dsx-box" },
      h("div", { class: "dsx-head" },
        h("span", { class: "dsx-mark" }, raw(DESKTOP_ICON)),
        h("h2", { class: "dsx-title" }, () => t("daemon.title")),
        h("button", { class: "dsx-icon", title: () => t("daemon.refresh"),
                      onClick: () => daemon.check() }, raw(REFRESH_ICON)),
        h("button", { class: "dsx-icon", title: () => t("daemon.close"), onClick: close }, raw(CLOSE_ICON))),
      // `body` and not `body()`: passed as a FUNCTION it is a reactive child, so the screen becomes the
      // connected one by itself the moment the daemon answers — which is the whole "install it and watch this
      // turn green" step. Called, it would render once and never change again.
      h("div", { class: "dsx-scroll" },
        body,
        () => problem() ? h("p", { class: "dsx-problem" }, problem()) : null),
    ),
  );
}
