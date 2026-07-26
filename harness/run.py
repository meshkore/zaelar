#
# E2E reasoning harness: a synthetic PERSON (user_sim) holds a conversation with the zaelar assistant brain,
# then a strong judge scores it and proposes prompt fixes. Text-level (voice is already solved) so we iterate on
# logic/reasoning/prompts fast and cheaply. Faithful to the deployed assistant: SAME system prompt (prompt.py),
# SAME model + token cap as the live app.
#
#   ./.venv/bin/python harness/run.py                  # all personas, judged, writes a report
#   ./.venv/bin/python harness/run.py skeptic 8        # one persona, 8 user turns, no judge
#
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ZAELAR = os.path.dirname(HERE)
if ZAELAR not in sys.path:
    sys.path.insert(0, ZAELAR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ZAELAR, ".env"), override=True)

from voice import llm  # noqa: E402
from voice.prompt import build_system_prompt  # noqa: E402
from user_sim import UserSim  # noqa: E402  (same dir on path via HERE below)
sys.path.insert(0, HERE)

ALL_PERSONAS = ["busy_pro", "skeptic", "venter", "tasker", "curveball"]
ASSISTANT_MODEL = os.getenv("ASSISTANT_LLM_MODEL", os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash"))
ASSISTANT_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "120"))
MAX_USER_TURNS = int(os.getenv("SIM_MAX_TURNS", "9"))

# Mirrors voice_agent.kickoff: the first assistant turn is a short greeting that asks the name + invites use.
KICKOFF = ("I just connected. This is the FIRST turn and it must be SHORT: say a warm hello, tell me who you are "
           "in one line, and ASK my name, and invite me to tell you what you can help with today. Just that — "
           "don't list everything you can do yet. Then stop and wait for me.")


def assistant_reply(history: list) -> tuple[str, float]:
    """One zaelar turn. history is zaelar's POV (system + alternating user/assistant). Returns (text, latency_s)."""
    t = time.perf_counter()
    txt = llm.call_llm(history, model=ASSISTANT_MODEL, temperature=0.7, max_tokens=ASSISTANT_MAX_TOKENS)
    return (txt or "").strip(), time.perf_counter() - t


def run_conversation(persona: str, max_user_turns: int = MAX_USER_TURNS) -> dict:
    brain = (os.getenv("BRAIN", "direct").lower())
    print(f"\n=== conversation · persona={persona} · brain={brain} · model={ASSISTANT_MODEL} ===", flush=True)
    a_hist = [{"role": "system", "content": build_system_prompt()}]   # no-name: what a first-time tester hits
    sim = UserSim(persona, model=ASSISTANT_MODEL)
    transcript = []
    lat = []

    # v2 «Colmena» (V2-009): el harness conversacional habla con el modelo de asistente directamente (no hay
    # agente ACP externo que primar). La adaptación completa del arnés al cerebro propio es V2-010.
    def reply(history):
        return assistant_reply(history)

    t0 = time.perf_counter()

    # zaelar greets first (kickoff).
    a_hist.append({"role": "user", "content": KICKOFF})
    greet, dt = reply(a_hist)
    a_hist.append({"role": "assistant", "content": greet})
    lat.append(dt)
    transcript.append({"turn": 0, "who": "zaelar", "text": greet, "t_s": round(time.perf_counter() - t0, 2),
                       "latency_s": round(dt, 2)})
    print(f"  zaelar: {greet}", flush=True)
    sim.hears(greet)

    for i in range(1, max_user_turns + 1):
        u = sim.say()
        ended = "<END>" in u
        u = u.replace("<END>", "").strip()
        if u:
            transcript.append({"turn": i, "who": "user", "text": u, "t_s": round(time.perf_counter() - t0, 2)})
            print(f"  user:   {u}", flush=True)
            a_hist.append({"role": "user", "content": u})
        if ended:
            print("  (user ended the conversation)", flush=True)
            break
        a, dt = reply(a_hist)
        a_hist.append({"role": "assistant", "content": a})
        lat.append(dt)
        transcript.append({"turn": i, "who": "zaelar", "text": a, "t_s": round(time.perf_counter() - t0, 2),
                           "latency_s": round(dt, 2)})
        print(f"  zaelar: {a}", flush=True)
        sim.hears(a)

    metrics = {
        "assistant_turns": len(lat),
        "avg_reply_latency_s": round(sum(lat) / len(lat), 2) if lat else None,
        "max_reply_latency_s": round(max(lat), 2) if lat else None,
        "model": ASSISTANT_MODEL, "max_tokens": ASSISTANT_MAX_TOKENS,
    }
    return {"persona": persona, "transcript": transcript, "metrics": metrics}


def _runid() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def main():
    args = sys.argv[1:]
    # Single-persona quick mode (no judge): `run.py <persona> [turns]` (one persona, optional turn count).
    if args and args[0] in ALL_PERSONAS and (len(args) == 1 or args[1].isdigit()):
        turns = int(args[1]) if len(args) > 1 else MAX_USER_TURNS
        run = run_conversation(args[0], turns)
        print("\nMETRICS:", json.dumps(run["metrics"], ensure_ascii=False))
        return

    personas = ALL_PERSONAS if not args else [p for p in args if p in ALL_PERSONAS] or ALL_PERSONAS
    from judge import judge
    runid = _runid()
    outdir = os.path.join(HERE, "runs", runid)
    os.makedirs(outdir, exist_ok=True)
    results = []
    for p in personas:
        run = run_conversation(p)
        print(f"  judging {p}…", flush=True)
        try:
            verdict = judge(run)
        except Exception as e:
            verdict = {"error": str(e)}
        run["judge"] = verdict
        results.append(run)
        json.dump(run, open(os.path.join(outdir, f"{p}.json"), "w"), ensure_ascii=False, indent=2)
        ov = verdict.get("overall", "?")
        print(f"  → {p}: overall={ov} · {verdict.get('verdict','')}", flush=True)

    _write_report(outdir, results)
    print(f"\nReport: {os.path.join(outdir, 'report.md')}", flush=True)


def _write_report(outdir: str, results: list):
    lines = ["# zaelar — simulated conversation review", "", f"Run: {os.path.basename(outdir)}", ""]
    dims = ["naturalness", "reasoning", "helpfulness", "persona", "honesty", "responsiveness", "memory", "name"]
    lines.append("| persona | overall | " + " | ".join(dims) + " | avg lat |")
    lines.append("|" + "---|" * (len(dims) + 3))
    for r in results:
        j = r.get("judge", {}) or {}
        sc = j.get("scores", {}) or {}
        row = [r["persona"], str(j.get("overall", "?"))] + [str(sc.get(d, "-")) for d in dims]
        row.append(str(r["metrics"].get("avg_reply_latency_s", "-")))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    for r in results:
        j = r.get("judge", {}) or {}
        lines += [f"## {r['persona']} — verdict: {j.get('verdict','(n/a)')}", ""]
        if j.get("findings"):
            lines.append("**Findings:**")
            for f in j["findings"]:
                lines.append(f"- [{f.get('severity','?')}] {f.get('turn','')}: {f.get('problem','')}")
        if j.get("improvements"):
            lines.append("\n**Proposed prompt fixes:**")
            for im in j["improvements"]:
                lines.append(f"- `{im.get('target','')}` → {im.get('change','')}  _({im.get('why','')})_")
        if j.get("user_sim_realism"):
            lines.append(f"\n_user-sim realism: {j['user_sim_realism']}_")
        lines.append("")
    open(os.path.join(outdir, "report.md"), "w", encoding="utf-8").write("\n".join(lines))


if __name__ == "__main__":
    main()
