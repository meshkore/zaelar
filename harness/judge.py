#
# Judge — a strong model (Opus 4.8 via the AI/ML router) reads a simulated conversation between a person and
# zaelar, PLUS zaelar's actual system prompt, and scores it like a demanding human reviewer: is the assistant
# natural, logical, helpful, honest (no fabricated private data), responsive, and on-persona? It also flags
# whether the synthetic USER felt realistic. It diagnoses and proposes concrete prompt fixes — it does NOT edit.
#
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ZAELAR = os.path.dirname(HERE)
if ZAELAR not in sys.path:
    sys.path.insert(0, ZAELAR)

from voice import llm  # noqa: E402

RUBRIC = """Score 1-5 (5 = excellent) each dimension, judging the ASSISTANT (zaelar):
- naturalness: sounds like a warm real person, not a robot? (spoken rhythm, contractions, no repetition)
- reasoning: does it actually understand intent, connect to what the user said, and respond logically?
- helpfulness: does it move the user forward, take initiative appropriately, behave like a capable life-assistant?
- persona: stays the personal-LIFE assistant (agenda, memory, messages) — warm, a bit charming, NOT a techy/search tool?
- honesty: does it AVOID inventing private data or live facts it can't have, while staying useful? (fabrication = low)
- responsiveness: are turns short and voice-appropriate (no monologues), so the conversation feels fast and fluid?
- memory: does it remember and reuse what the user said earlier in the conversation, and not re-ask?
- name: if it didn't know the name, did it ask and then use it naturally (sparingly)?"""

SCHEMA = """Return ONLY a JSON object:
{
 "scores": {"naturalness":n,"reasoning":n,"helpfulness":n,"persona":n,"honesty":n,"responsiveness":n,"memory":n,"name":n},
 "overall": n,
 "findings": [{"turn": "assistant#3", "problem": "...", "severity": "high|med|low"}],
 "improvements": [{"target": "prompt.py (which part, e.g. FIRST MOMENTS / WHAT YOU DO / PLAYING THE PART)", "change": "concrete, actionable edit", "why": "..."}],
 "user_sim_realism": "one line: did the simulated person feel realistic? any tweak to harness/personas/<x>.md?",
 "verdict": "one line: is zaelar demo-ready for a human, and the #1 blocker if not?"
}"""


def _zaelar_system_prompt() -> str:
    from voice.prompt import build_system_prompt
    return build_system_prompt()   # the no-name variant (what a first-time tester hits)


def judge(run: dict, model: str = None) -> dict:
    model = model or os.getenv("EVAL_MODEL", "claude-opus-4-8")
    convo = "\n".join(
        f"[{t['t_s']:>5.1f}s] {t['who'].upper():<9} {t['text']}" for t in run.get("transcript", []))
    metrics = run.get("metrics", {})
    sysmsg = ("You are a senior evaluator of conversational voice assistants — demanding, concrete, fair. You "
              "judge whether the ASSISTANT sounds human, reasons well, helps, and stays honest, and you propose "
              "actionable fixes to its PROMPT. The simulated user being imperfect is expected; judge the ASSISTANT.")
    user = f"""Evaluate this simulated conversation between a PERSON (synthetic, persona = {run.get('persona')}) and our
personal voice assistant "Zaelar". Zaelar speaks English and is meant to be a warm personal-LIFE assistant
(agenda, reminders, recalling messages across WhatsApp/Telegram/email, prepping messages) — NOT a techy/search
tool. It is newly set up, so it should NOT have the user's real data yet and must not fabricate it.

{RUBRIC}

=== LATENCY (assistant reply wall-clock, seconds) ===
{json.dumps(metrics, ensure_ascii=False, indent=1)}

=== TRANSCRIPT ===
{convo}

=== zaelar's CURRENT SYSTEM PROMPT (this is what you can propose changing — prompt.py) ===
{_zaelar_system_prompt()}

{SCHEMA}"""
    raw = llm.call_llm([{"role": "system", "content": sysmsg}, {"role": "user", "content": user}],
                       model=model, max_tokens=4000)
    return llm.parse_json(raw)
