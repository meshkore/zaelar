"""LLM judge — evaluates a scenario run (transcript + latency + what was expected) as a demanding human would,
and proposes CONCRETE improvements for zaelar's code team. Black-box: it judges OBSERVABLE behaviour and never
reads zaelar's source, so it stays independent of the code under test. Ported/adapted from the sim candidate."""
from __future__ import annotations

import json

from .. import config, llm

RUBRIC = """Score each dimension 1-5 (5=excellent):
- naturalidad: does zaelar sound like a real person? (phrasing, rhythm, no robotic repetition)
- coherencia: does it track context across turns, not repeat, not contradict itself?
- utilidad: did it actually DO/answer what the user asked (the scenario goal)?
- accion: did zaelar ACCOMPLISH THE SCENARIO GOAL (see "Qué cuenta como éxito")? Judge per the goal TYPE:
  · VISUAL goal (show/close a widget, open the canvas) → REQUIRES a matching action in the FRONTEND TRACE; if
    zaelar claimed to show a widget but the trace has no widget action, that's a FAILURE (score low).
  · INFORMATIONAL/CONVERSATIONAL goal (tell the time, summarize a note, answer a question, chat) → a correct VERBAL
    answer IS the action; do NOT require a frontend/widget action and do NOT penalize its absence. Score by whether
    zaelar actually delivered the answer/summary.
- latencia: do the response times make the conversation feel alive? (penalize slow/timeouts)
- robustez: did it recover from mis-hearings/garbled input instead of derailing or going mute?"""

SCHEMA = """Return ONLY a JSON object:
{
 "scores": {"naturalidad":n,"coherencia":n,"utilidad":n,"accion":n,"latencia":n,"robustez":n},
 "overall": n,
 "findings": [{"turno":"zaelar@turn2","problema":"...","gravedad":"alta|media|baja"}],
 "improvements": [{"area":"likely area in zaelar (e.g. voice prompt/persona, STT config, turn endpointing, brain memory, widget tags, TTS)","cambio":"concrete, actionable change","porque":"the observed symptom that motivates it"}],
 "veredicto": "one sentence: is this scenario production-ready, and the #1 blocker?"
}"""


def judge(scenario, run: dict, model: str | None = None) -> dict:
    convo = "\n".join(
        f"[{t.get('at','')}] {t['who'].upper():7} " + (t.get('text') or '(no reply / timeout)')
        + (f"  <{t['latency_ms']}ms>" if t.get('latency_ms') is not None else "")
        for t in run.get("transcript", []))
    tr = run.get("trace", {}) or {}
    actions = tr.get("frontend_actions", [])
    brain = tr.get("brain_trace", [])
    sys = ("Eres un evaluador senior de asistentes de voz, exigente y concreto. Juzgas por el comportamiento "
           "OBSERVABLE de zaelar: lo que dice (transcript) Y lo que hace en el frontend/cerebro (traza de eventos "
           "de observabilidad). No ves su código fuente. Propones mejoras accionables. Vas al grano.")
    user = f"""Evalúas a zaelar (asistente personal por voz, en castellano) en un escenario de prueba. Al usuario lo
simula otro bot (imperfecto: puede haber mis-hearings del STT en ambos lados — no penalices a zaelar por ruido de
transcripción del tester). Juzgas a ZAELAR.

CÓMO FUNCIONAN LOS CANALES (no te confundas):
- voz: conversación por audio (STT↔TTS).
- chat / paste: el usuario INYECTA texto por el data-channel (como teclear o Ctrl+V). zaelar lo recibe y responde
  como un turno normal — NO existe ni se espera una "UI de pegar" ni detección de intención de pegado; el éxito es
  que zaelar procese ese TEXTO y responda/resuma. No penalices por falta de un widget en chat/paste.
- websocket: preguntar por el estado del canal cluster; se juzga que lo diga en lenguaje natural.

=== ESCENARIO: {scenario.id} (canal {scenario.channel}) ===
Objetivo del usuario: {scenario.goal}
Qué cuenta como éxito: {scenario.checks}

=== MÉTRICAS DE LATENCIA (ms, lado zaelar: fin de la voz del usuario → primer audio de zaelar) ===
{json.dumps(run.get('latency_ms', {}), ensure_ascii=False)}

=== TRANSCRIPT (lo que se DIJO) ===
{convo or '(sin diálogo)'}

=== TRAZA DE OBSERVABILIDAD (lo que REALMENTE PASÓ en el frontend/cerebro; la fuente de verdad para 'accion') ===
Acciones de frontend/canvas observadas: {json.dumps(actions, ensure_ascii=False) if actions else '(NINGUNA — no se abrió/cerró ningún widget ni se disparó ningún conector)'}
Actividad del cerebro/LLM: {json.dumps(brain[:20], ensure_ascii=False) if brain else '(sin traza de cerebro)'}
Tipos de evento: {json.dumps(tr.get('event_kinds', {}), ensure_ascii=False)}

{RUBRIC}

{SCHEMA}"""
    raw, used = llm.judge_call([{"role": "system", "content": sys}, {"role": "user", "content": user}], max_tokens=2000)
    try:
        v = llm.parse_json(raw)
        v["_judge_model"] = used
        return v
    except Exception as e:
        return {"scores": {}, "overall": None, "findings": [], "improvements": [], "_judge_model": used,
                "veredicto": f"(juez no devolvió JSON válido: {e}) — raw: {raw[:300]}"}
