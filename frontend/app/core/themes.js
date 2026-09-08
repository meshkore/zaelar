// themes.js — the DESIGN PROFILE catalog (V2-617). A profile is a map of token OVERRIDES per theme
// (dark/light) that services/theme.js writes as inline custom properties on <html>. Inline beats the
// stylesheet, so the default profile («grafito») is simply the palette.css values with NO overrides —
// one source of truth, not two copies that drift.
//
// The contract that makes this integral rather than cosmetic: the whole desktop AND every widget read the
// same `--hb-*` tokens (palette.css's opening comment), so a profile swap repaints everything at once —
// including user-generated widgets, which the generator's contract (widgets/AGENTS.md) already binds to the
// tokens. A widget that wants its own look opts OUT explicitly; nothing is half-skinned by omission.
//
// Adding a profile = one entry here (id, label, swatches for the ⚙ card, per-theme var maps). Custom knobs
// (accent color, base font size, font family) are separate — they layer ON TOP of any profile (theme.js).

export const THEMES = {
  // The default skin: warm graphite + heliotrope. Values live in palette.css; this entry only carries
  // the ⚙ card's preview swatches.
  grafito: {
    label: "Grafito",
    swatches: ["#0B0B0E", "#18181D", "#A48FFF", "#E8A33D"],
    vars: { dark: {}, light: {} },
  },
  // Today's navy look, kept whole so an operator who prefers it loses nothing on upgrade. These are the
  // exact pre-V2-617 palette.css values.
  clasico: {
    label: "Clásico",
    swatches: ["#0a0f16", "#141d29", "#3D6FE0", "#16B8A6"],
    vars: {
      dark: {
        "--canvas": "#0a0f16", "--canvas-glow": "#111a24", "--chrome-line": "#1d2735",
        "--hb-bg": "#141d29", "--hb-bg-soft": "#101720", "--hb-bg-a": "rgba(14,20,28,.82)",
        "--hb-bubble": "#1b2530", "--hb-hover": "#1c2733",
        "--hb-ink": "#e8edf5", "--hb-muted": "#93a1b6", "--hb-muted-2": "#64758c",
        "--hb-line": "#232e3d", "--hb-neutral": "#3a4a5c",
        "--hb-accent": "#3D6FE0", "--hb-ok": "#1f9d55", "--hb-warn": "#c98a00",
        "--hb-shadow-1": "0 8px 30px rgba(0,0,0,.45)", "--hb-shadow-2": "0 20px 60px rgba(0,0,0,.55)",
        "--hb-warn-bg": "#2a2013", "--hb-warn-border": "#5c4420", "--hb-warn-ink": "#e8b673",
        "--hb-console-bg": "#0d1622", "--hb-console-line": "#1d2735",
        "--hb-console-ink": "#e8edf5", "--hb-console-muted": "#8ba0bc",
        "--hb-update": "#f59e0b", "--hb-update2": "#f97316",
        "--desk-grid-a": "0", "--desk-halo": "transparent", "--desk-ember": "transparent",
      },
      light: {
        "--canvas": "#f7f9fc", "--canvas-glow": "#ffffff", "--chrome-line": "#e3e8f0",
        "--hb-bg": "#fff", "--hb-bg-soft": "#fbfdff", "--hb-bg-a": "rgba(255,255,255,.82)",
        "--hb-bubble": "#f1f4f9", "--hb-hover": "#eef3f9",
        "--hb-ink": "#0d1622", "--hb-muted": "#5f6b7c", "--hb-muted-2": "#9aa7b8",
        "--hb-line": "#e3e8f0", "--hb-neutral": "#c2ccda",
        "--hb-accent": "#3D6FE0", "--hb-ok": "#1f9d55", "--hb-warn": "#c98a00",
        "--hb-shadow-1": "0 8px 30px rgba(13,22,34,.12)", "--hb-shadow-2": "0 20px 60px rgba(13,22,34,.22)",
        "--hb-warn-bg": "#fff7ed", "--hb-warn-border": "#fed7aa", "--hb-warn-ink": "#9a5b1b",
        "--hb-update": "#f59e0b", "--hb-update2": "#f97316",
        "--desk-grid-a": "0", "--desk-halo": "transparent", "--desk-ember": "transparent",
      },
    },
  },
  // Grafito with the two tints swapped: amber does the interactive work, the heliotrope highlights.
  ambar: {
    label: "Ámbar",
    swatches: ["#0B0B0E", "#18181D", "#E8A33D", "#A48FFF"],
    vars: {
      dark: {
        "--hb-accent": "#E8A33D", "--hb-update": "#A48FFF", "--hb-update2": "#8B74F5",
        "--desk-halo": "rgba(232,163,61,.05)", "--desk-ember": "rgba(164,143,255,.04)",
      },
      light: {
        "--hb-accent": "#B97A16", "--hb-update": "#7A5FF0", "--hb-update2": "#8B74F5",
        "--desk-halo": "rgba(185,122,22,.05)", "--desk-ember": "rgba(122,95,240,.04)",
      },
    },
  },
};

export const DEFAULT_PROFILE = "grafito";

// Custom knobs — each maps a small, validated choice to token overrides. They apply AFTER the profile,
// so «Clásico + my green accent + large type» is a legal combination, not a fourth profile.
export const FONT_STACKS = {
  system: "",   // empty = keep the profile/palette default (--sans as shipped)
  rounded: 'ui-rounded,"SF Pro Rounded","Nunito","Segoe UI",system-ui,sans-serif',
  serif: '"Iowan Old Style","Palatino","Georgia","Times New Roman",serif',
};
export const FONT_SIZES = { s: "16px", m: "17px", l: "18.5px" };   // --hb-fs-base steps

export function customVars(custom) {
  const v = {};
  const c = custom || {};
  if (/^#[0-9a-fA-F]{6}$/.test(c.accent || "")) v["--hb-accent"] = c.accent;
  if (FONT_SIZES[c.fs]) v["--hb-fs-base"] = FONT_SIZES[c.fs];
  if (FONT_STACKS[c.font]) v["--sans"] = FONT_STACKS[c.font];
  return v;
}
