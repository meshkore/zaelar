"""Live observation console — watch the tester and zaelar talk in real time in a browser.

A tiny aiohttp server: GET / serves a self-contained page that streams conversation events over SSE (GET /sse)
and renders them as a two-column live transcript (tester ↔ zaelar) with per-turn latency. The orchestrator
(run.py) pushes events here as they happen. This is the headline deliverable: see one speak, the other receive.
"""
from __future__ import annotations

import asyncio
import json
import os
import re

from aiohttp import web

_HTML = """<!doctype html><html><head><meta charset=utf-8><title>zaelar · voice tester</title>
<style>
 :root{--bg:#0d1117;--pane:#161b22;--ink:#e6edf3;--muted:#8b949e;--tester:#58a6ff;--zaelar:#3fb950;--line:#30363d;--warn:#d29922}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,system-ui,sans-serif}
 header{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;position:sticky;top:0;background:var(--bg)}
 header b{font-size:15px} #status{color:var(--muted)} .pill{padding:2px 8px;border:1px solid var(--line);border-radius:999px;font-size:12px}
 #lat{margin-left:auto;color:var(--muted)} #lat b{color:var(--ink)}
 #log{max-width:900px;margin:0 auto;padding:16px;display:flex;flex-direction:column;gap:8px}
 .row{display:flex} .row.tester{justify-content:flex-start} .row.zaelar{justify-content:flex-end}
 .msg{max-width:70%;padding:8px 12px;border-radius:12px;border:1px solid var(--line);white-space:pre-wrap}
 .tester .msg{background:#0b2a4a;border-color:#1f6feb;border-bottom-left-radius:3px}
 .zaelar .msg{background:#0f2f1a;border-color:#238636;border-bottom-right-radius:3px}
 .who{font-size:11px;color:var(--muted);margin:0 4px 2px} .tester .who{text-align:left}.zaelar .who{text-align:right}
 .meta{font-size:11px;color:var(--muted);margin-top:3px} .sys{align-self:center;color:var(--muted);font-size:12px;font-style:italic}
 .err{align-self:center;color:#f85149;font-size:12px}
</style></head><body>
<header><b>🎙 zaelar voice tester</b><span id=status class=pill>connecting…</span><span id=lat>latency: <b>—</b></span></header>
<div id=log></div>
<script>
 const log=document.getElementById('log'), statusEl=document.getElementById('status'), latEl=document.getElementById('lat').querySelector('b');
 function row(side,who,text,meta){const r=document.createElement('div');r.className='row '+side;
   const w=document.createElement('div');w.className='who';w.textContent=who;
   const m=document.createElement('div');m.className='msg';m.textContent=text;
   const box=document.createElement('div');box.appendChild(w);box.appendChild(m);
   if(meta){const md=document.createElement('div');md.className='meta';md.textContent=meta;md.style.textAlign=side==='zaelar'?'right':'left';box.appendChild(md);}
   r.appendChild(box);log.appendChild(r);window.scrollTo(0,document.body.scrollHeight);}
 function sys(t,cls){const d=document.createElement('div');d.className=cls||'sys';d.textContent=t;log.appendChild(d);window.scrollTo(0,document.body.scrollHeight);}
 const es=new EventSource('/sse');
 es.onopen=()=>statusEl.textContent='live';
 es.onmessage=e=>{const ev=JSON.parse(e.data);const k=ev.kind,t=ev.text||'';
   if(k==='say') row('tester','🧑 tester (Alex)',t);
   else if(k==='zaelar_turn'){row('zaelar','🤖 zaelar',t||'(no reply — timeout)', ev.latency_ms!=null?('↩ '+ev.latency_ms+' ms'):'↩ timeout');
     if(ev.latency_ms!=null) latEl.textContent=ev.latency_ms+' ms';}
   else if(k==='status') statusEl.textContent=t||'live';
   else if(k==='verdict') sys('⚖ '+t);
   else if(k==='error'||k==='alert') sys('⚠ '+(ev.label||'')+' '+t,'err');
   else if(k==='bot_speech'&&ev.label==='EMPIEZA') statusEl.textContent='zaelar speaking…';
   else if(k==='user_speech') statusEl.textContent='listening…';
 };
 es.onerror=()=>statusEl.textContent='disconnected';
</script></body></html>"""


class Observer:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._history: list[dict] = []
        self._runner = None
        self.port: int | None = None   # the actual bound port (OS-assigned when started with 0)
        self._platform = None
        if run_dir := os.getenv("ZAELAR_TEST_RUN_DIR"):
            try:
                from tests.platform.events import EventWriter
                self._platform = EventWriter(run_dir, run_id=os.getenv("ZAELAR_TEST_RUN_ID"))
            except Exception:
                self._platform = None

    def push(self, ev: dict) -> None:
        self._history.append(ev)
        if self._platform is not None:
            kind = ev.get("kind", "observer")
            event_type = {
                "say": "interaction.input",
                "zaelar_turn": "interaction.output",
                "verdict": "judge.verdict",
                "error": "observer.error",
                "alert": "observer.error",
            }.get(kind, f"voice.{kind}")
            score = None
            if kind == "verdict" and (match := re.search(r"([0-5](?:\.\d+)?)\s*/\s*5", ev.get("text", ""))):
                score = {"value": float(match.group(1)), "scale": 5, "source": "judge"}
            self._platform.emit(
                event_type,
                suite="voice",
                kind=kind,
                label=ev.get("label", ""),
                text=ev.get("text", ""),
                latency_ms=ev.get("latency_ms"),
                score=score,
            )
        for q in list(self._subs):
            try:
                q.put_nowait(ev)
            except Exception:
                pass

    async def _index(self, request):
        return web.Response(text=_HTML, content_type="text/html")

    async def _sse(self, request):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache",
                                           "X-Accel-Buffering": "no"})
        await resp.prepare(request)
        q: asyncio.Queue = asyncio.Queue()
        for ev in self._history:      # replay so a late-opened browser sees the whole conversation
            q.put_nowait(ev)
        self._subs.add(q)
        try:
            while True:
                ev = await q.get()
                await resp.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8"))
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            self._subs.discard(q)
        return resp

    async def start(self, port: int = 0) -> int:
        """Bind the console. port=0 → the OS picks a free port (kept in self.port). Returns the actual port."""
        app = web.Application()
        app.add_routes([web.get("/", self._index), web.get("/sse", self._sse)])
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", port).start()
        self.port = self._runner.addresses[0][1]
        return self.port
