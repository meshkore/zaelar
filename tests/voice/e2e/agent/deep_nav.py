#!/usr/bin/env python3
"""Harness for REAL deep-navigation EXECUTION (V2-057 · INI-013): escalates a MARKETPLACE objective
(Idealista/coches.net/AutoScout/Wallapop/Milanuncios/Amazon) through the PROBE channel with execute=true → the server
launches a REAL Brain Worker that DRIVES the browser (the owner's Chromium) against the live site → we observe the
timeline: recorded escalation · browser card · phases (cookies/navigate/extract) · extracted listings ·
final delivery · VERIFICATION signals (V2-057: does it meet the constraint? did it sort/filter? did it provide real data?).

Unlike the sea of domains (routing, fast, hundreds), this is SLOW and touches LIVE sites (1–3 min each,
CAPTCHA/blocking may occur) → only a FEW are run, as an e2e test. Usage:
  PYTHONPATH=. .venv/bin/python tests/voice/e2e/agent/deep_nav.py <sitio|all> [timeout_s]
  sitios: idealista coches autoscout wallapop milanuncios amazon
Requires zaelar to be running (make run) with the live backed browser."""
import json
import os
import sys
import time
import urllib.request

BASE = "http://localhost:43917"
TL = ".meshkore/logs/timeline-latest.jsonl"

# REAL objective per site (natural language, as the operator would say it) + words confirming that it TOUCHED the site
GOALS = {
    "idealista":  ("Busca en Idealista pisos de alquiler en Barcelona por menos de 1200 euros al mes y dime los 3 mejores.", "idealista"),
    "coches":     ("Mira en coches.net un Volkswagen Golf diésel de segunda mano por menos de 15.000 euros.", "coches.net"),
    "autoscout":  ("Busca en AutoScout24 un BMW Serie 3 familiar de 2019 en adelante y enséñame las mejores opciones.", "autoscout"),
    "wallapop":   ("Búscame en Wallapop una bici de montaña de menos de 300 euros cerca de Barcelona.", "wallapop"),
    "milanuncios":("En Milanuncios busca un sofá de segunda mano en Madrid por menos de 200 euros.", "milanuncios"),
    "amazon":     ("Busca en Amazon unos auriculares con cancelación de ruido por menos de 100 euros.", "amazon"),
}


def _post(path, body, t=180):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=t).read().decode())


def _tasks():
    try:
        return _post("/api/tasks", {}) if False else json.loads(
            urllib.request.urlopen(BASE + "/api/tasks", timeout=10).read().decode())
    except Exception:
        return {}


def _wait_idle(max_s=90):
    """Waits for NO live worker before starting → prevents the escalation from being DEDUPED against an in-
    progress task (lesson 2026-07-21: launching coches.net while the Idealista worker was still alive deduped it → phases=0)."""
    t = time.time()
    while time.time() - t < max_s:
        tk = _tasks()
        if isinstance(tk, dict) and not tk.get("sessions"):
            return True
        try: urllib.request.urlopen(BASE + "/api/status", timeout=3).read()
        except Exception: pass
    return False


def run_site(site, timeout_s=180):
    goal, needle = GOALS[site]
    print(f"\n{'='*70}\n== {site.upper()} == «{goal}»")
    sess = f"deepnav-{site}"
    _post("/api/flash/reset", {"session": sess})
    if not _wait_idle():
        print("  ⚠️ había un worker vivo; sigo igual (puede deduparse)")
    start = os.path.getsize(TL)
    t0 = time.time()
    # Actually EXECUTES: launches the worker that drives the browser
    r = _post("/api/flash/say", {"text": goal, "session": sess, "ingest": False, "execute": True})
    print(f"  escalada: action={r.get('action')} · reply={ (r.get('reply') or '')[:70] }")

    # Observe the timeline until the task finishes (or times out)
    phases, hitos, delivered, extracted_n, saw_site, saw_verify = [], [], "", 0, False, False
    deadline = t0 + timeout_s
    last_sz = start
    while time.time() < deadline:
        # Waiting tick WITHOUT foreground sleep: an inexpensive network call sets the pace
        try:
            urllib.request.urlopen(BASE + "/api/status", timeout=3).read()
        except Exception:
            pass
        sz = os.path.getsize(TL)
        if sz == last_sz:
            continue
        last_sz = sz
        with open(TL) as f:
            f.seek(start)
            rows = [json.loads(l) for l in f if l.strip()]
        for d in rows:
            lab, txt, kind = (d.get("label") or ""), (d.get("text") or ""), d.get("kind")
            blob = (lab + " " + txt).lower()
            if kind == "task" and lab == "phase" and txt not in phases:
                phases.append(txt); print(f"    · fase: {txt[:80]}")
            if needle in blob and not saw_site:
                saw_site = True; print(f"    ✓ tocó {needle}")
            if "extract" in blob or "anuncios" in blob or "listings" in blob:
                extracted_n = max(extracted_n, 1)
            if any(k in blob for k in ("verific", "más reciente", "de hoy", "cumple", "ordena")):
                saw_verify = True
            # Worker's final delivery (SYSTEM / proactive note)
            if kind in ("notify", "tts") or "tarea completada" in blob or "brain worker · tarea" in blob:
                if txt and len(txt) > 20:
                    delivered = txt
        # Finished? No live sessions and escalation has already occurred
        tk = _tasks()
        if isinstance(tk, dict) and tk.get("sessions") == [] and (time.time() - t0) > 20 and delivered:
            break

    dur = round(time.time() - t0)
    print(f"  -- {site}: {dur}s · fases={len(phases)} · tocó_sitio={saw_site} · extrajo={'sí' if extracted_n else 'no'} "
          f"· verificó_señal={saw_verify}")
    print(f"     entrega: {delivered[:160] or '(sin entrega capturada)'}")
    ok = saw_site and bool(delivered)
    print(f"     VEREDICTO: {'PASS (navegó el sitio y entregó)' if ok else 'PARCIAL/REVISAR (mira el timeline)'}")
    return {"site": site, "dur": dur, "phases": len(phases), "site_touched": saw_site,
            "extracted": bool(extracted_n), "verify": saw_verify, "delivered": delivered[:200], "ok": ok}


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "idealista"
    tmo = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    sites = list(GOALS) if which == "all" else which.split(",")
    results = [run_site(s, tmo) for s in sites if s in GOALS]
    print(f"\n{'='*70}\nRESUMEN: {sum(1 for r in results if r['ok'])}/{len(results)} PASS")
    for r in results:
        print(f"  {r['site']:12} {'PASS' if r['ok'] else 'REV '} · {r['dur']}s · sitio={r['site_touched']} extrajo={r['extracted']}")
