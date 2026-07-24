// Serpiente (Snake) — juego clásico, 100% cliente, autónomo y pasivo. Contrato: render(el, data, ctx).
// No red, no store: todo el estado del juego vive en memoria del cliente (y el récord en localStorage).
// Rejilla DOM (no canvas) para que el cambio de tema (☾/☀) re-pinte al instante vía CSS, sin tocar JS.
// Control por flechas del teclado (foco en el propio widget, no secuestra las flechas de la página).

const COLS = 18, ROWS = 18, TICK_MS = 130, BEST_KEY = "hb-snake-best";

function injectStyles(){
  if(document.getElementById("hb-snake-css"))return;
  const s=document.createElement("style"); s.id="hb-snake-css"; s.textContent=`
  .hb-snake{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(420px,88vw);outline:none}
  .hb-snake .snk-hd{display:flex;align-items:baseline;gap:10px;margin:0 0 10px}
  .hb-snake .snk-hd b{font-size:16px}
  .hb-snake .snk-score{margin-left:auto;font-family:ui-monospace,Menlo,monospace;font-size:13px;color:var(--hb-muted,#5b6b82)}
  .hb-snake .snk-score .snk-v{color:var(--hb-accent,#3D6FE0);font-weight:600}
  .hb-snake .snk-best{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-snake .snk-wrap{position:relative}
  .hb-snake .snk-grid{display:grid;grid-template-columns:repeat(${COLS},1fr);gap:1px;
    background:var(--hb-line,#eef1f6);border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:1px;
    aspect-ratio:1/1;width:100%}
  .hb-snake .snk-cell{background:var(--hb-bg-soft,#fbfdff);border-radius:2px}
  .hb-snake .snk-cell.body{background:var(--hb-accent,#3D6FE0)}
  .hb-snake .snk-cell.head{background:var(--hb-accent2,#16B8A6)}
  .hb-snake .snk-cell.food{background:var(--hb-risk,#e5484d);border-radius:50%}
  .hb-snake .snk-over{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
    gap:10px;background:color-mix(in srgb,var(--hb-bg,#fff) 82%,transparent);border-radius:12px;text-align:center;padding:14px}
  .hb-snake .snk-over .big{font-size:18px;font-weight:600}
  .hb-snake .snk-over .sm{font-size:13px;color:var(--hb-muted,#5b6b82);max-width:80%}
  .hb-snake .snk-btn{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:9px;
    padding:8px 16px;font-size:13px;cursor:pointer;color:var(--hb-accent,#3D6FE0);font-weight:600}
  .hb-snake .snk-btn:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-snake .snk-hint{margin-top:9px;font-size:12px;color:var(--hb-muted-2,#9aa7b8);text-align:center}
  `; document.head.appendChild(s);
}

function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=String(text); return e; }

export function render(el, data, ctx){
  injectStyles();
  // limpieza defensiva: el host puede re-llamar a render con datos frescos → nunca dejar dos bucles/listeners vivos
  if(el._snkStop) el._snkStop();

  el.className="hb-snake";
  el.tabIndex=0;                       // foco propio → capturamos flechas sin robárselas a la página
  el.textContent="";

  const hd=el2("div","snk-hd");
  const scoreEl=el2("span","snk-score"); scoreEl.append(document.createTextNode("Puntos "), el2("span","snk-v","0"));
  let best=0; try{ best=parseInt(localStorage.getItem(BEST_KEY)||"0",10)||0; }catch(_){ best=0; }
  const bestEl=el2("span","snk-best","récord "+best);
  hd.append(el2("b",null,"🐍 Serpiente"), scoreEl, bestEl);
  el.appendChild(hd);

  const wrap=el2("div","snk-wrap");
  const grid=el2("div","snk-grid");
  const cells=[];                      // rejilla de celdas reutilizadas (índice y*COLS+x)
  for(let i=0;i<COLS*ROWS;i++){ const c=el2("div","snk-cell"); grid.appendChild(c); cells.push(c); }
  wrap.appendChild(grid);
  el.appendChild(wrap);
  el.appendChild(el2("div","snk-hint","Usa las flechas ← ↑ ↓ → para moverte."));

  // ---- estado del juego ----
  let snake, dir, nextDir, food, score, timer=null, alive=false;

  const idx=(x,y)=>y*COLS+x;
  function randFood(){
    const free=[];
    for(let y=0;y<ROWS;y++) for(let x=0;x<COLS;x++)
      if(!snake.some(s=>s.x===x&&s.y===y)) free.push({x,y});
    return free.length ? free[Math.floor(Math.random()*free.length)] : null;
  }

  function paint(){
    for(let i=0;i<cells.length;i++) cells[i].className="snk-cell";
    if(food) cells[idx(food.x,food.y)].classList.add("food");
    snake.forEach((s,i)=> cells[idx(s.x,s.y)].classList.add(i===0?"head":"body"));
    scoreEl.querySelector(".snk-v").textContent=String(score);
  }

  function reset(){
    const cx=Math.floor(COLS/2), cy=Math.floor(ROWS/2);
    snake=[{x:cx,y:cy},{x:cx-1,y:cy},{x:cx-2,y:cy}];
    dir={x:1,y:0}; nextDir={x:1,y:0}; score=0; food=randFood(); paint();
  }

  function gameOver(){
    alive=false; if(timer){clearInterval(timer);timer=null;}
    if(score>best){ best=score; try{ localStorage.setItem(BEST_KEY,String(best)); }catch(_){}
      bestEl.textContent="récord "+best; }
    showOverlay(false);
  }

  function step(){
    dir=nextDir;
    const head={x:snake[0].x+dir.x, y:snake[0].y+dir.y};
    // choque con la pared
    if(head.x<0||head.x>=COLS||head.y<0||head.y>=ROWS){ gameOver(); return; }
    // choque consigo misma (la cola se libera este turno salvo que comamos)
    const grows = food && head.x===food.x && head.y===food.y;
    const body = grows ? snake : snake.slice(0,-1);
    if(body.some(s=>s.x===head.x&&s.y===head.y)){ gameOver(); return; }
    snake.unshift(head);
    if(grows){ score+=1; food=randFood(); if(!food){ paint(); gameOver(); return; } } // rejilla llena = victoria
    else snake.pop();
    paint();
  }

  function start(){
    clearOverlay(); reset(); alive=true;
    if(timer)clearInterval(timer);
    timer=setInterval(step, TICK_MS);
    el.focus();
  }

  // ---- overlay (inicio / game over) ----
  let overlay=null;
  function clearOverlay(){ if(overlay){overlay.remove();overlay=null;} }
  function showOverlay(isStart){
    clearOverlay();
    overlay=el2("div","snk-over");
    if(isStart){
      overlay.append(el2("div","big","🐍 Serpiente"),
        el2("div","sm","Come, crece y no choques. Flechas del teclado para moverte."));
    } else {
      overlay.append(el2("div","big","¡Game over!"),
        el2("div","sm","Puntuación: "+score+(score>=best&&score>0?" · ¡nuevo récord!":" · récord "+best)));
    }
    const btn=el2("button","snk-btn",isStart?"Jugar":"Jugar de nuevo");
    btn.onclick=(e)=>{ e.stopPropagation(); start(); };
    overlay.appendChild(btn);
    wrap.appendChild(overlay);
  }

  // ---- controles ----
  const DIRS={ArrowLeft:{x:-1,y:0},ArrowRight:{x:1,y:0},ArrowUp:{x:0,y:-1},ArrowDown:{x:0,y:1},
              a:{x:-1,y:0},d:{x:1,y:0},w:{x:0,y:-1},s:{x:0,y:1}};
  function onKey(e){
    const nd=DIRS[e.key];
    if(!nd)return;
    e.preventDefault();
    if(!alive) return;
    if(nd.x===-dir.x && nd.y===-dir.y) return;   // no giro de 180°
    nextDir=nd;
  }
  el.addEventListener("keydown", onKey);

  // pantalla inicial
  reset(); showOverlay(true);

  // el host guarda esto y lo llama antes de re-renderizar → sin fugas de intervalos/listeners
  el._snkStop=()=>{ if(timer)clearInterval(timer); el.removeEventListener("keydown",onKey); el._snkStop=null; };
}
