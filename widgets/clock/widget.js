// Clock widget: large centered digital clock. Browser-local time, refreshed every second.
// Data comes from the server but is used only as an initial fallback; the client renders the real clock.

function injectStyles(){
  if(document.getElementById("hb-clock-css"))return;
  const s=document.createElement("style"); s.id="hb-clock-css"; s.textContent=`
  .hb-clock{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);
            width:min(520px,90vw);background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);border-radius:18px;
            padding:28px 24px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:10px}
  .hb-clock .time{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:72px;font-weight:600;
                  color:var(--hb-ink,#0d1622);letter-spacing:.02em;line-height:1;font-variant-numeric:tabular-nums}
  .hb-clock .time .sec{color:var(--hb-accent2,#16B8A6);font-size:54px;margin-left:4px}
  .hb-clock .dow{font-size:13px;color:var(--hb-muted,#5b6b82);letter-spacing:.02em}
  .hb-clock .date{font-size:15px;color:var(--hb-muted,#3a4757);text-transform:capitalize;letter-spacing:.01em}
  .hb-clock .tz{font-size:11px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace;margin-top:2px}
  @media(max-width:480px){.hb-clock .time{font-size:54px}.hb-clock .time .sec{font-size:40px}}
  `; document.head.appendChild(s);
}

function pad(n){ return String(n).padStart(2,"0"); }

// V2-613: this is a SYSTEM widget, so day/month names follow the operator's language — but a hand-built
// template of translated WORDS cannot also reorder "January 5, 2026" into "5 de enero de 2026" (English and
// Spanish put the day and month in different places, and other languages differ further still). `Intl` already
// solves the whole shape — order, connectors, capitalization — for any locale, from `ctx.lang` alone; no bundle
// keys needed for this widget at all.
function fmtDow(d, lang){
  const s = new Intl.DateTimeFormat(lang || "en", {weekday:"long"}).format(d);
  return s.charAt(0).toUpperCase() + s.slice(1);
}
function fmtDate(d, lang){
  return new Intl.DateTimeFormat(lang || "en", {day:"numeric", month:"long", year:"numeric"}).format(d);
}

export function render(el, data, ctx){
  injectStyles();
  if(el._clockTimer){ clearInterval(el._clockTimer); el._clockTimer=null; }

  el.className="hb-clock";
  el.textContent="";
  const time = document.createElement("div"); time.className="time";
  const hm = document.createElement("span"); hm.className="hm";
  const sec = document.createElement("span"); sec.className="sec";
  time.appendChild(hm); time.appendChild(sec);
  const dow = document.createElement("div"); dow.className="dow";
  const date = document.createElement("div"); date.className="date";
  const tz = document.createElement("div"); tz.className="tz";
  el.appendChild(time); el.appendChild(dow); el.appendChild(date); el.appendChild(tz);

  function tick(){
    const d = new Date();
    const lang = ctx && ctx.lang;
    hm.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    sec.textContent = `:${pad(d.getSeconds())}`;
    dow.textContent = fmtDow(d, lang);
    date.textContent = fmtDate(d, lang);
  }
  try {
    const tzName = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    tz.textContent = tzName;
  } catch(_) { tz.textContent = ""; }

  tick();
  el._clockTimer = setInterval(tick, 1000);
}
