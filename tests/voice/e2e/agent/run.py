"""Orchestrator — starts everything at once against a running zaelar: the interlocutor (speaks/types), the live
observation console (watch in a browser), and the judge (writes improvement reports to tester/runs/).

Run (zaelar up on the LiveKit engine):
    ./.venv/bin/python -m tester.run                      # all scenarios, opens the console, writes a report
    ./.venv/bin/python -m tester.run --scenario agenda    # just one
    ./.venv/bin/python -m tester.run --goal "..." --turns 6   # a free-form conversation

Independent: talks to zaelar only over LiveKit + HTTP + data channel. Imports no zaelar core code.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
import urllib.request

from livekit.agents.utils import http_context

from . import config, scenarios as SC
from .interlocutor import providers
from .interlocutor import trace as tracemod
from .interlocutor.brain import TesterBrain
from .interlocutor.voice_link import VoiceLink
from .judge import judge as judgemod, report as reportmod
from .observe import Observer


def _token() -> dict:
    url = f"{config.ZAELAR_URL}/api/token?identity={config.TESTER_IDENTITY}"
    return json.loads(urllib.request.urlopen(url, timeout=10).read())


def _dispatch_looks_dead(run_data: dict) -> bool:
    """Total silence signature of a LiveKit dispatch failure (INI-013, 2026-07-07: zaelar's agent never joined the
    room at all — NOT a slow/wrong turn) — every single zaelar transcript entry is empty/missing, across the WHOLE
    scenario. A real content/quality problem still gets at least SOME text back; this is specifically "nobody home"."""
    zaelar_turns = [t for t in run_data.get("transcript", []) if t.get("who") == "zaelar"]
    return bool(zaelar_turns) and all(not (t.get("text") or "").strip() for t in zaelar_turns)


def _probe_websocket() -> dict:
    """Black-box: read zaelar's /api/status and report the MeshKore cluster websocket item."""
    try:
        st = json.loads(urllib.request.urlopen(f"{config.ZAELAR_URL}/api/status", timeout=10).read())
        item = next((it for it in st.get("items", []) if it.get("key") == "cluster"), None)
        txt = json.dumps(item, ensure_ascii=False) if item else "no cluster item in /api/status"
    except Exception as e:
        txt = f"probe failed: {e}"
    return {"transcript": [{"who": "tester", "text": "probe /api/status → cluster websocket"},
                           {"who": "zaelar", "text": txt}], "latency_ms": {}}


async def _dialog(link: VoiceLink, scenario, obs: Observer, tr=None) -> dict:
    """Run one voice/chat/paste scenario. Returns {transcript, latency_ms}.

    Reply TEXT comes from zaelar's OWN transcript on the observability stream (via `tr`, the /events trace) when
    available — it's the authoritative record of what zaelar said and is immune to the tester's Deepgram STT dropping
    zaelar's audio (which caused false timeouts → false all-1s). The tester's STT still provides the audio LATENCY."""
    transcript: list[dict] = []
    lats: list[int] = []

    def note(who, text, lat=None):
        row = {"who": who, "text": text, "at": round(time.time(), 2)}
        if lat is not None:
            row["latency_ms"] = lat
        transcript.append(row)

    async def zaelar_reply(stt_reply: dict, mark: int) -> str:
        """Prefer zaelar's OWN transcript (from the trace) over the tester's STT of zaelar's audio. If it's not in
        the slice yet — the observability event can arrive a beat after wait_reply returns (SSE lag) and the tester's
        Deepgram STT frequently drops zaelar's audio — POLL the trace briefly instead of declaring a false timeout."""
        stt_text = (stt_reply.get("text") or "").strip()
        if tr is not None:
            for _ in range(8):  # up to ~4s waiting for zaelar's reply event to land in the trace
                texts = tracemod.zaelar_texts(tr.slice_from(mark))
                if texts:
                    return " ".join(texts).strip()
                if stt_text:   # STT already captured it → no need to wait for the trace
                    break
                await asyncio.sleep(0.5)
        return stt_text

    brain = TesterBrain(persona="curious_user", behavior="neutral", goal=scenario.goal)
    speak = (scenario.channel == "voice")
    long_paste = (scenario.channel == "paste")

    # zaelar greets on connect for EVERY channel (the kickoff runs regardless). Wait for it on ALL channels: it also
    # confirms zaelar's session + data handler are READY before we send chat/paste text (else it was dropped).
    gm = tr.mark() if tr is not None else 0
    g = await link.wait_reply(timeout=20)
    gtext = await zaelar_reply(g, gm)
    if gtext:
        brain.hears(gtext); note("zaelar", gtext, g.get("latency_ms"))
    # For chat/paste the reply text can come from the trace (brain event) the instant zaelar GENERATES the greeting,
    # while its TTS is still PLAYING. Sending the first text then races a busy session → generate_reply dropped
    # (intermittent chat/paste no-reply). Give zaelar a moment to finish speaking the greeting before sending. (2026-07-07)
    if not speak:
        await asyncio.sleep(2.5)

    for _ in range(max(1, scenario.turns)):
        utterance = brain.reply()
        if long_paste:
            utterance = ("Te pego una nota, resúmemela en una línea: " + utterance + " "
                         "Además hoy saqué al perro, pagué dos facturas y reservé un vuelo a Lisboa para el mes que viene.")
        note("tester", utterance)
        tm = tr.mark() if tr is not None else 0
        if speak:
            await link.say(utterance)
        else:
            await link.send_text(utterance, kind=scenario.channel)
        reply = await link.wait_reply(timeout=25)
        rtext = await zaelar_reply(reply, tm)
        note("zaelar", rtext, reply.get("latency_ms"))
        brain.hears(rtext or "(no reply)")
        if isinstance(reply.get("latency_ms"), int):
            lats.append(reply["latency_ms"])
        if any(b in utterance.lower() for b in ("bye", "adiós", "adios", "hasta luego")):
            break

    avg = round(sum(lats) / len(lats)) if lats else None
    return {"transcript": transcript,
            "latency_ms": {"n": len(lats), "avg": avg, "max": max(lats) if lats else None, "samples": lats}}


async def run(args) -> None:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    obs = Observer()
    bound = await obs.start(args.port)
    console = f"http://127.0.0.1:{bound}"
    print(f"▶ observation console: {console}")
    if not args.no_open:
        try:
            subprocess.Popen(["open", console])
        except Exception:
            pass
        await asyncio.sleep(1.2)

    # pick scenarios
    if args.goal:
        chosen = [SC.Scenario("adhoc", "voice", args.goal, "free-form conversation", turns=args.turns)]
    elif args.scenario == "all":
        chosen = SC.SCENARIOS
    else:
        chosen = [SC.BY_ID[args.scenario]]

    # OBSERVABILITY: subscribe to zaelar's /events once; slice per scenario so the judge sees the frontend/brain.
    tr = tracemod.Trace()
    await tr.start()
    await asyncio.sleep(0.3)

    results: list[dict] = []
    for scenario in chosen:
        obs.push({"kind": "verdict", "text": f"▶ scenario: {scenario.id} ({scenario.channel})"})
        t_idx = tr.mark()
        if scenario.channel == "websocket":
            run_data = _probe_websocket()
            for t in run_data["transcript"]:
                obs.push({"kind": "say" if t["who"] == "tester" else "zaelar_turn",
                          "label": "", "text": t["text"], "role": "assistant" if t["who"] == "zaelar" else "user"})
        else:
            def on_ev(kind, label, **f):
                obs.push({"kind": kind, "label": label, **f})
            # RETRY ONCE on total silence (INI-013, 2026-07-07): LiveKit's embedded worker sometimes registers fine
            # but never gets OFFERED the job for a specific new room (a still-open dispatch race, distinct from the
            # earlier "worker never registers" bug scripts/run-livekit.sh's settle-wait already covers) — the room
            # sits open with zaelar's agent never joining at all, so EVERY turn times out and the report reads
            # "sistema completamente mudo" for what's actually a transient per-room dispatch miss, not a real
            # regression. A fresh room+token is a new dispatch attempt; if THAT also comes back silent, it's very
            # likely a real problem and we report it as such (with a note distinguishing the two).
            for attempt in (1, 2):
                t_idx = tr.mark()
                tok = _token()
                async with http_context.open():
                    tts, stt = providers.build_tts(), providers.build_stt()
                    link = VoiceLink(tts, stt, on_event=on_ev,
                                     wav_path=str(config.RUNS_DIR / f"audio_{scenario.id}.wav"))
                    await link.connect(tok["url"], tok["token"])
                    run_data = await _dialog(link, scenario, obs, tr)
                    await link.aclose()
                await asyncio.sleep(0.5)   # let the room fully tear down before the next attempt/scenario joins
                if not _dispatch_looks_dead(run_data):
                    break
                if attempt == 1:
                    obs.push({"kind": "status", "text": (
                        f"⚠️ {scenario.id}: silencio total (posible fallo de dispatch de LiveKit, no de zaelar) "
                        f"— reintentando UNA vez con una sala nueva antes de dar el veredicto por bueno")})
                else:
                    run_data["dispatch_dead_after_retry"] = True
                    obs.push({"kind": "status", "text": (
                        f"⚠️ {scenario.id}: silencio total TAMBIÉN tras reintentar — probablemente un fallo real "
                        f"(dispatch de LiveKit o zaelar), no ruido de un solo intento")})

        # attach the observability slice (frontend actions + brain/LLM trace) for THIS scenario
        run_data["trace"] = tracemod.summary(tr.slice_from(t_idx))
        acts = run_data["trace"]["frontend_actions"]
        obs.push({"kind": "status", "text": f"frontend: {', '.join(acts) if acts else '(sin acciones de canvas)'}"})

        obs.push({"kind": "status", "text": f"judging {scenario.id}…"})
        verdict = judgemod.judge(scenario, run_data, model=args.model or None)
        results.append({"scenario": scenario.id, "channel": scenario.channel, "run": run_data, "verdict": verdict})
        obs.push({"kind": "verdict",
                  "text": f"{scenario.id}: {verdict.get('overall','—')}/5 · {(verdict.get('veredicto','') or '')[:80]}"})

    await tr.aclose()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    report_path = reportmod.build(results, stamp, config.RUNS_DIR)
    obs.push({"kind": "verdict", "text": f"✓ informe → {report_path.name} (en tester/runs/)"})
    print(f"✓ report → {report_path}")

    print(f"▶ console live at {console} for {args.hold}s")
    try:
        await asyncio.sleep(args.hold)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="zaelar voice tester — interlocutor + judge + live console")
    ap.add_argument("--scenario", default="all", help="'all', a scenario id, or use --goal for free-form")
    ap.add_argument("--goal", default="", help="free-form conversation goal (overrides --scenario)")
    ap.add_argument("--turns", type=int, default=6, help="turns for the free-form --goal conversation")
    ap.add_argument("--model", default="", help="judge model override (default: TESTER_JUDGE_MODEL)")
    ap.add_argument("--port", type=int, default=0, help="0 = pick a free random port and keep it (default)")
    ap.add_argument("--hold", type=int, default=90, help="seconds to keep the console alive after the run")
    ap.add_argument("--no-open", action="store_true")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
