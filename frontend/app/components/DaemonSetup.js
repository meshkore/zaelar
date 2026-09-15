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

// How a SELF-HOSTER starts it. Not a download: they already have the daemon — it is a Python package in this
// repository, it has no dependencies at all, and the launcher starts it beside the engine on both platforms.
// These are the repo's own verbs, so they live here rather than in a translation bundle: `./zaelar restart` is
// not a phrase, it is a command, and translating it would break it.
const SOURCE_COMMANDS = {
  macos: "./zaelar restart",
  windows: ".\\zaelar.ps1 restart",
};

export function DaemonSetup() {
  const [problem, setProblem] = createSignal("");
  const [busy, setBusy] = createSignal("");
  const [chosen, setChosen] = createSignal("");      // which platform's instructions are showing
  const [copied, setCopied] = createSignal(false);
  let pathEl;

  // `navigator.clipboard` needs a secure context, and this app is served over plain http on 43917 as well as
  // https on 44317 — so on the http origin the modern API simply is not there. The old `execCommand` path is
  // the fallback, and the button says what happened either way: a copy button that silently does nothing is
  // worse than no button, because the user walks away believing they have the command.
  const copy = async (text) => {
    if (!text) return;
    let ok = false;
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); ok = true; }
    } catch (_) { ok = false; }
    if (!ok) {
      try {
        const ta = document.createElement("textarea");
        ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        ok = document.execCommand("copy");
        document.body.removeChild(ta);
      } catch (_) { ok = false; }
    }
    if (ok) { setCopied(true); setTimeout(() => setCopied(false), 1800); }
    api.uiEvent("daemon:copy_command", { ok });
  };

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
    const current = () => all[platform()] || {};
    return h("div", { class: "dsx-dl" },
      // Which machine, not which file. The tabs pick the platform; the command below is the whole install.
      h("div", { class: "dsx-dl-row" }, ...names.map((name) =>
        h("button", {
          class: () => "dsx-dl-btn" + (platform() === name ? " on" : ""),
          onClick: () => { setChosen(name); api.uiEvent("daemon:platform", { platform: name }); },
        }, PLATFORM_LABEL[name] || name))),
      h("p", { class: "dsx-note" }, () => t("daemon.cmd.lead")),
      h("div", { class: "dsx-cmd-row" },
        h("code", { class: "dsx-cmd" }, () => current().command || ""),
        h("button", { class: "dsx-copy",
          onClick: () => copy(current().command || ""),
        }, () => copied() ? t("daemon.cmd.copied") : t("daemon.cmd.copy"))),
      h("p", { class: "dsx-note" }, () => t("daemon.cmd.why")),
      h("p", { class: "dsx-note" }, () => t("daemon.note.noadmin")),
      // The direct file stays reachable for somebody who would rather look at it first — and it is the path
      // that COSTS a security dialog, because a browser is what marks a download as quarantined. Said here,
      // quietly, instead of being the button everybody presses by default.
      h("details", { class: "dsx-more" },
        h("summary", {}, () => t("daemon.manual.summary")),
        h("p", { class: "dsx-note" }, () => t("daemon.manual.body")),
        h("p", { class: "dsx-note" },
          h("a", { class: "dsx-link", href: () => current().artifact || "#", download: "" },
            () => t("daemon.manual.artifact")), " · ",
          h("a", { class: "dsx-link", href: () => current().installer || "#", download: "" },
            () => t("daemon.manual.installer")), " · ",
          h("a", { class: "dsx-link", href: () => current().checksums || "#" },
            () => t("daemon.note.checksums_link"))),
        h("p", { class: "dsx-note" }, () => t("daemon.manual.arch"))),
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
    // ⚠️ A SELF-HOSTER IS NEVER OFFERED A DOWNLOAD. They cloned the repository; the daemon is already on their
    // disk as a Python package with no dependencies, and the launcher starts it. Handing them an installer for
    // a binary would be telling somebody who owns the source to go and fetch a copy of it — and it would put a
    // second, differently-versioned daemon on the machine, competing for the same port. The download exists
    // for exactly one audience: somebody whose Zaelar runs in the cloud, on a computer that is not theirs.
    if (!s.reachable) {
      return h("div", {},
        h("p", { class: "dsx-lead" }, () => t("daemon.local.lead")),
        h("div", { class: "dsx-dl-row" }, ...Object.keys(SOURCE_COMMANDS).map((name) =>
          h("button", {
            class: () => "dsx-dl-btn" + (platform() === name ? " on" : ""),
            onClick: () => { setChosen(name); api.uiEvent("daemon:platform", { platform: name }); },
          }, PLATFORM_LABEL[name] || name))),
        h("p", { class: "dsx-note" }, () => t("daemon.local.body")),
        h("div", { class: "dsx-cmd-row" },
          h("code", { class: "dsx-cmd" }, () => SOURCE_COMMANDS[platform()] || SOURCE_COMMANDS.macos),
          h("button", { class: "dsx-copy",
            onClick: () => copy(SOURCE_COMMANDS[platform()] || SOURCE_COMMANDS.macos),
          }, () => copied() ? t("daemon.cmd.copied") : t("daemon.cmd.copy"))),
        h("p", { class: "dsx-note" }, () => t("daemon.local.hint")),
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
