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
    swatches: ["#0B0D10", "#12151A", "#9B7CFF", "#EFC75E"],
    vars: { dark: {}, light: {} },
  },
  // Today's navy look, kept whole so an operator who prefers it loses nothing on upgrade. These are the
  // exact pre-V2-617 palette.css values.
  clasico: {
    label: "Clásico",
    swatches: ["#0a0f16", "#141d29", "#3D6FE0", "#16B8A6"],
    vars: {
      dark: {
        "--canvas": "#0a0f16", "--canvas-glow": "#111a24", "--chrome-line": "rgba(255,255,255,.10)",
        "--hb-bg": "#141d29", "--hb-bg-soft": "#1a2634", "--hb-bg-a": "rgba(20,29,41,.88)",
        "--hb-sidebar": "#0d141d",
        "--hb-bubble": "#213040", "--hb-hover": "#28394c",
        "--hb-ink": "#e8edf5", "--hb-muted": "#93a1b6", "--hb-muted-2": "#7b8ca3",
        "--hb-line": "rgba(255,255,255,.10)", "--hb-line-subtle": "rgba(255,255,255,.06)",
        "--hb-line-strong": "rgba(255,255,255,.18)", "--hb-neutral": "#3a4a5c",
        "--hb-accent": "#3D6FE0", "--hb-accent2": "#16B8A6", "--hb-ok": "#1f9d55", "--hb-warn": "#c98a00",
        "--hb-risk": "#e5484d", "--hb-risk-soft": "rgba(229,72,77,.14)",
        "--hb-shadow-1": "0 1px 2px rgba(0,0,0,.30), 0 4px 12px rgba(0,0,0,.22)",
        "--hb-shadow-2": "0 2px 6px rgba(0,0,0,.34), 0 16px 40px rgba(0,0,0,.40)",
        "--hb-shadow-focus": "0 2px 8px rgba(0,0,0,.38), 0 22px 52px rgba(0,0,0,.48)",
        "--hb-line-win": "rgba(255,255,255,.14)", "--hb-line-win-focus": "rgba(255,255,255,.22)",
        "--hb-shadow-win": "0 0 0 1px rgba(0,0,0,.45), 0 2px 5px rgba(0,0,0,.26), 0 12px 30px rgba(0,0,0,.24)",
        "--hb-shadow-win-focus": "0 0 0 1px rgba(0,0,0,.55), 0 4px 10px rgba(0,0,0,.32), 0 22px 50px rgba(0,0,0,.40)",
        "--hb-warn-bg": "#2a2013", "--hb-warn-border": "#5c4420", "--hb-warn-ink": "#e8b673",
        "--hb-console-bg": "#0d1622", "--hb-console-line": "#1d2735",
        "--hb-console-ink": "#e8edf5", "--hb-console-muted": "#8ba0bc",
        "--hb-update": "#f59e0b", "--hb-update2": "#f97316",
        "--desk-grid-a": "0", "--desk-halo": "transparent", "--desk-ember": "transparent",
      },
      light: {
        "--canvas": "#f7f9fc", "--canvas-glow": "#ffffff", "--chrome-line": "rgba(13,22,34,.10)",
        "--hb-bg": "#fff", "--hb-bg-soft": "#f5f8fc", "--hb-bg-a": "rgba(255,255,255,.88)",
        "--hb-sidebar": "#eef2f8",
        "--hb-bubble": "#e9eef6", "--hb-hover": "#e0e7f1",
        "--hb-ink": "#0d1622", "--hb-muted": "#5f6b7c", "--hb-muted-2": "#707d8f",
        "--hb-line": "rgba(13,22,34,.10)", "--hb-line-subtle": "rgba(13,22,34,.06)",
        "--hb-line-strong": "rgba(13,22,34,.20)", "--hb-neutral": "#c2ccda",
        "--hb-accent": "#3D6FE0", "--hb-accent2": "#0E8FA8", "--hb-ok": "#1f9d55", "--hb-warn": "#c98a00",
        "--hb-risk": "#d93a45", "--hb-risk-soft": "rgba(217,58,69,.10)",
        "--hb-shadow-1": "0 1px 2px rgba(13,22,34,.06), 0 4px 12px rgba(13,22,34,.07)",
        "--hb-shadow-2": "0 2px 6px rgba(13,22,34,.08), 0 16px 40px rgba(13,22,34,.12)",
        "--hb-shadow-focus": "0 2px 8px rgba(13,22,34,.10), 0 22px 52px rgba(13,22,34,.18)",
        "--hb-line-win": "rgba(13,22,34,.14)", "--hb-line-win-focus": "rgba(13,22,34,.24)",
        "--hb-shadow-win": "0 0 0 1px rgba(13,22,34,.10), 0 2px 5px rgba(13,22,34,.07), 0 12px 30px rgba(13,22,34,.10)",
        "--hb-shadow-win-focus": "0 0 0 1px rgba(13,22,34,.16), 0 4px 10px rgba(13,22,34,.10), 0 22px 50px rgba(13,22,34,.16)",
        "--hb-warn-bg": "#fff7ed", "--hb-warn-border": "#fed7aa", "--hb-warn-ink": "#9a5b1b",
        "--hb-update": "#f59e0b", "--hb-update2": "#f97316",
        "--desk-grid-a": "0", "--desk-halo": "transparent", "--desk-ember": "transparent",
      },
    },
  },
  // Grafito with the two tints swapped: amber does the interactive work, the heliotrope highlights.
  ambar: {
    label: "Ámbar",
    swatches: ["#0B0D10", "#12151A", "#EFC75E", "#9B7CFF"],
    vars: {
      dark: {
        "--hb-accent": "#EFC75E", "--hb-update": "#9B7CFF", "--hb-update2": "#8B74F5",
        "--desk-halo": "rgba(239,199,94,.05)", "--desk-ember": "rgba(155,124,255,.04)",
      },
      light: {
        "--hb-accent": "#B4821A", "--hb-update": "#7A5AF5", "--hb-update2": "#8B74F5",
        "--desk-halo": "rgba(180,130,26,.05)", "--desk-ember": "rgba(122,90,245,.04)",
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
