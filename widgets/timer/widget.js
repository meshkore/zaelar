// Timer/countdown widget — cronómetro grande y clarísimo (el "horno" de Ricard)
// El brain fija el tiempo via backend; el widget pinta la cuenta atrás en vivo.
// Persiste en localStorage del navegador para que sobreviva a refrescos.

function injectStyles() {
  if (document.getElementById("hb-timer-css")) return;
  const s = document.createElement("style"); s.id = "hb-timer-css"; s.textContent = `
  .hb-timer{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
            width:min(520px,90vw);background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);
            border-radius:18px;padding:28px 24px;text-align:center;
            display:flex;flex-direction:column;align-items:center;gap:8px}
  .hb-timer .ht-label{font-size:14px;font-weight:500;color:var(--hb-muted,#5b6b82);text-transform:uppercase;
                      letter-spacing:.06em;margin-bottom:2px}
  .hb-timer .ht-digits{font-family:ui-monospace,Menlo,Consolas,monospace;font-weight:600;
                       color:var(--hb-ink,#0d1622);line-height:1;letter-spacing:.02em;font-variant-numeric:tabular-nums;
                       transition:color .3s}
  .hb-timer .ht-digits.lg{font-size:76px}
  .hb-timer .ht-digits.md{font-size:60px}
  .hb-timer .ht-digits.sm{font-size:44px}
  .hb-timer .ht-digits.finished{color:var(--hb-accent2,#16B8A6)}
  .hb-timer .ht-digits .unit{font-size:30%;color:var(--hb-muted-2,#9aa7b8);vertical-align:super;margin-left:2px}
  .hb-timer .ht-sub{font-size:13px;color:var(--hb-muted,#5b6b82);min-height:1.4em}
  .hb-timer .ht-actions{display:flex;gap:10px;margin-top:10px;flex-wrap:wrap;justify-content:center}
  .hb-timer .ht-btn{font-family:inherit;font-size:13px;font-weight:500;padding:8px 22px;border-radius:40px;
                    border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);
                    color:var(--hb-ink,#0d1622);cursor:pointer;transition:all .15s;min-width:72px}
  .hb-timer .ht-btn:hover{background:var(--hb-bg-soft,#f0f3f8);border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-timer .ht-btn.primary{background:var(--hb-accent,#3D6FE0);color:#fff;border-color:var(--hb-accent,#3D6FE0)}
  .hb-timer .ht-btn.primary:hover{opacity:.88}
  .hb-timer .ht-btn.danger{color:var(--hb-risk,#e5484d);border-color:var(--hb-risk,#e5484d)}
  .hb-timer .ht-btn.danger:hover{background:var(--hb-risk,#e5484d);color:#fff}
  .hb-timer .ht-empty{color:var(--hb-muted-2,#9aa7b8);font-size:14px;padding:20px 0;font-style:italic}
  @media(max-width:480px){.hb-timer .ht-digits.lg{font-size:56px}.hb-timer .ht-digits.md{font-size:44px}.hb-timer .ht-digits.sm{font-size:34px}}
  `; document.head.appendChild(s);
}

function fmtTime(secs, short) {
  if (secs <= 0) return "0:00";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  if (short && m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}:${String(m % 60).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}min ${s}s`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

function sizeClass(secs) {
  if (secs <= 0) return "lg";
  if (secs > 900) return "lg";      // > 15 min
  if (secs > 120) return "md";      // 2-15 min
  return "sm";                       // < 2 min — smaller, shows seconds
}

function showSecs(secs) {
  if (secs <= 0) return true;
  return secs <= 300;  // < 5 min → show seconds
}

function timeParts(secs) {
  const neg = secs < 0;
  secs = Math.abs(secs);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return { neg, h, m, s };
}

function fmtDigits(parts, showSecsFlag) {
  const { neg, h, m, s } = parts;
  let text = "";
  if (h > 0) text += `${neg ? "-" : ""}${h}:${String(m).padStart(2, "0")}`;
  else text += `${neg ? "-" : ""}${m}`;
  if (showSecsFlag) text += `:${String(s).padStart(2, "0")}`;
  return text;
}

function fmtDigitsHTML(parts, showSecsFlag) {
  const { neg, h, m, s } = parts;
  let html = "";
  if (h > 0) {
    html += `<span class="ht-num">${neg ? "-" : ""}${h}</span><span class="unit">h</span> `;
    html += `<span class="ht-num">${String(m).padStart(2, "0")}</span><span class="unit">min</span>`;
  } else {
    html += `<span class="ht-num">${neg ? "-" : ""}${m}</span>`;
  }
  if (showSecsFlag) {
    if (h > 0) html += ` <span class="ht-num">${String(s).padStart(2, "0")}</span><span class="unit">s</span>`;
    else html += `<span class="unit">min</span> <span class="ht-num">${String(s).padStart(2, "0")}</span><span class="unit">s</span>`;
  } else if (h === 0) {
    html += `<span class="unit">min</span>`;
  }
  return html;
}

// ── localStorage backup (survives page refreshes, syncs with server on render) ──

function lsKey() { return "hb_timer_state"; }

function lsSave(data) {
  try { localStorage.setItem(lsKey(), JSON.stringify({
    remaining: data.remaining,
    running: data.running,
    target_seconds: data.target_seconds,
    label: data.label,
    saved_at: Date.now()
  })); } catch(_) {}
}

function lsLoad() {
  try {
    const raw = localStorage.getItem(lsKey());
    if (!raw) return null;
    const d = JSON.parse(raw);
    const elapsed = (Date.now() - (d.saved_at || Date.now())) / 1000;
    if (d.running) d.remaining = Math.max(0, d.remaining - elapsed);
    return d;
  } catch(_) { return null; }
}

function lsClear() { try { localStorage.removeItem(lsKey()); } catch(_) {} }

// ── Poll the backend for fresh data ──
function fetchData() {
  // The data comes from the server on the initial render call. We keep ticking client-side.
  // If we ever need a mid-life refresh, this could fetch via SSE or a simple GET.
  // For now, the initial data + client tick + localStorage is enough.
  return null;
}

export function render(el, data, ctx) {
  injectStyles();
  if (el._timerTick) { clearInterval(el._timerTick); el._timerTick = null; }
  if (el._finishTimeout) { clearTimeout(el._finishTimeout); el._finishTimeout = null; }

  // Merge server data + localStorage backup
  data = data || {};
  let remaining = data.remaining !== undefined ? data.remaining : 0;
  let running = !!data.running;
  let target = data.target_seconds !== undefined ? data.target_seconds : 0;
  let label = data.label || "";
  let finished = !!data.finished;

  // If server says nothing running but localStorage has a running timer, use it
  const ls = lsLoad();
  if ((!target || !running) && ls && ls.remaining > 0 && !finished) {
    remaining = Math.round(ls.remaining);
    running = ls.running;
    target = target || ls.target_seconds || remaining;
    label = label || ls.label || "";
  }

  // Build DOM
  el.className = "hb-timer";
  el.textContent = "";

  // Label row
  const labelEl = document.createElement("div"); labelEl.className = "ht-label";
  labelEl.textContent = label || "TEMPORIZADOR";
  el.appendChild(labelEl);

  // Digits
  const digits = document.createElement("div");
  digits.className = "ht-digits lg";
  el.appendChild(digits);

  // Subtext (e.g. "pausado" / "¡Tiempo cumplido!")
  const sub = document.createElement("div"); sub.className = "ht-sub";
  el.appendChild(sub);

  // Action buttons
  const acts = document.createElement("div"); acts.className = "ht-actions";
  el.appendChild(acts);

  // ── State ──
  let state = { remaining, running, target, label, finished };

  // Save initial state
  if (state.remaining > 0) lsSave(state);

  function renderDisplay() {
    const s = state.remaining;
    const parts = timeParts(s);
    const showS = showSecs(s);
    const sc = s <= 0 ? "lg" : sizeClass(s);

    digits.className = `ht-digits ${sc}`;
    if (state.finished || (state.target > 0 && s <= 0)) {
      digits.classList.add("finished");
      digits.innerHTML = "¡LISTO!";
      sub.textContent = label ? `⏰ ${label} cumplido` : "⏰ ¡Tiempo cumplido!";
      state.running = false;
      state.finished = true;
      renderActions();
      lsClear();
      return;
    }
    digits.classList.remove("finished");
    digits.innerHTML = fmtDigitsHTML(parts, showS);

    if (!state.running && state.remaining > 0) sub.textContent = "⏸ Pausado";
    else if (state.remaining > 0) sub.textContent = "";
    else sub.textContent = "· · ·";

    renderActions();
  }

  function renderActions() {
    acts.textContent = "";
    if (state.remaining <= 0 && !state.finished) {
      const empty = document.createElement("div"); empty.className = "ht-empty";
      empty.textContent = "Pídele a zaelar que ponga un tiempo";
      acts.appendChild(empty);
      return;
    }
    if (state.finished) {
      const btn = document.createElement("button"); btn.className = "ht-btn danger";
      btn.textContent = "✕ Cerrar";
      btn.addEventListener("click", () => { ctx.close(); });
      acts.appendChild(btn);
      return;
    }
    if (state.running) {
      const pause = document.createElement("button"); pause.className = "ht-btn";
      pause.textContent = "⏸ Pausar";
      pause.addEventListener("click", () => {
        ctx.action("pause", {});
        state.running = false;
        lsSave(state);
      });
      acts.appendChild(pause);
    } else {
      const start = document.createElement("button"); start.className = "ht-btn primary";
      start.textContent = "▶ Reanudar";
      start.addEventListener("click", () => {
        ctx.action("start", {});
        state.running = true;
        // Recalculate started_at from remaining
        lsSave(state);
      });
      acts.appendChild(start);
    }
    const reset = document.createElement("button"); reset.className = "ht-btn danger";
    reset.textContent = "✕ Cancelar";
    reset.addEventListener("click", () => {
      ctx.action("reset", {});
      state.remaining = 0;
      state.running = false;
      state.target = 0;
      state.finished = false;
      lsClear();
      renderDisplay();
    });
    acts.appendChild(reset);
  }

  renderDisplay();

  // Tick
  if (state.running && state.remaining > 0) {
    // Haptic tick: every second until completion
    el._timerTick = setInterval(() => {
      if (!state.running || state.remaining <= 0) {
        clearInterval(el._timerTick);
        el._timerTick = null;
        return;
      }
      state.remaining = Math.max(0, state.remaining - 1);
      lsSave(state);
      if (state.remaining <= 0) {
        state.finished = true;
        state.running = false;
        renderDisplay();
        clearInterval(el._timerTick);
        el._timerTick = null;
        // Play haptic tick / visual flash — rely on CSS transition
      } else {
        renderDisplay();
      }
    }, 1000);
  }
}

// Cleanup
export function destroy(el) {
  if (el._timerTick) { clearInterval(el._timerTick); el._timerTick = null; }
  if (el._finishTimeout) { clearTimeout(el._finishTimeout); el._finishTimeout = null; }
}
