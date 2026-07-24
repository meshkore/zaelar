// Clock widget — reloj digital grande y centrado. Hora local del navegador, refresco cada segundo.
// data viene del servidor pero solo se usa como fallback inicial; el reloj real lo pinta el cliente.

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

const DAYS = ["domingo","lunes","martes","miércoles","jueves","viernes","sábado"];
const MONTHS = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];

function pad(n){ return String(n).padStart(2,"0"); }

function fmtDate(d){
  return `${DAYS[d.getDay()]}, ${d.getDate()} de ${MONTHS[d.getMonth()]} de ${d.getFullYear()}`;
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
    hm.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    sec.textContent = `:${pad(d.getSeconds())}`;
    const dn = DAYS[d.getDay()];
    dow.textContent = dn.charAt(0).toUpperCase() + dn.slice(1);
    date.textContent = fmtDate(d);
  }
  try {
    const tzName = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    tz.textContent = tzName;
  } catch(_) { tz.textContent = ""; }

  tick();
  el._clockTimer = setInterval(tick, 1000);
}
