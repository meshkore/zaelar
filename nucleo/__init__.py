"""nucleo/ — cerebro propio de zaelar v2 «Colmena» (EPIC-v2-colmena).

It replaces `brains/` (Hermes retirement, V2-009). For now this package is the brain's **SKELETON**:
docstrings and signatures that define the contract. Nothing is wired to voice yet (`BRAIN=duo`/`hermes`
remains the default until V2-009). The pieces are filled in during V2-004→V2-007.

Dos velocidades:

- **FlashBrain** (`nucleo/flash/`) — CÓDIGO PROPIO reflejo, **sub-segundo**. Cierra cada turno de voz. Piezas:
    · `router`      — classifies input and chooses the action (chat · widget control · launch process · escalate).
    · `fast_client` — client for the fast NON-REASONING model, **MODEL PER INVOCATION** (local Ollama / Grok
                      AIMLAPI), never a global model environment (session concurrency).
    · `frontend`    — gestor de frontend/widgets (emite el protocolo de tags `[[show]]`/`[[close]]`/…).
    · `procs`       — lanzador/gestor de procesos (widgets backed, tareas de navegador…).
    · `escalate`    — bridge to SlowBrain when a turn needs memory/tools/reasoning.
  Se enchufa al motor de voz como provider `livekit.agents.llm.LLM` (misma costura que `duo`), en V2-004.

- **SlowBrain** (`nucleo/dispatch.py` + `nucleo/memory_agent.py` + `nucleo/agentes/`) — **async** deliberation:
  a constellation of **Claude Code** agents behind `CodeAgent` (replaceable by Codex; model per invocation).
  Dispatcher + MEMORY agent ★ (composes the minimum context from `memory/`) + work agents (web/code/other).
  The result returns through the usual rails: `voice/proactive` + `voice/brain_notes`.

- **Orchestrator loop** (`nucleo/loop.py`, ~1 Hz) — the thread of time: scheduled tasks (built-in cron),
  🔥 sparks (spontaneous thought), memory consolidation ("sleep"), and voice+UI reporting.

Substratos compartidos (NO son parte del cerebro): la **memoria** (`memory/`, V2-002/003) y el **Sistema
Nervioso** (`bus/`, V2-001, ya construido).
"""

__all__ = ["flash", "agentes"]

# Phase marker: since V2-004 FlashBrain IS wired to voice (provider `nucleo`, opt-in with
# BRAIN=nucleo, alongside duo/hermes). The startup default remains `duo` until the V2-009 cutover.
WIRED_TO_VOICE = True
