"""nucleo/ — cerebro propio de zaelar v2 «Colmena» (EPIC-v2-colmena).

Sustituye a `brains/` (entierro de Hermes, V2-009). Este paquete es, de momento, el **ESQUELETO** del
cerebro: docstrings + firmas que fijan el contrato. Nada está cableado a la voz todavía (`BRAIN=duo`/`hermes`
sigue siendo el default hasta V2-009). Las piezas se rellenan en V2-004→V2-007.

Dos velocidades:

- **FlashBrain** (`nucleo/flash/`) — CÓDIGO PROPIO reflejo, **sub-segundo**. Cierra cada turno de voz. Piezas:
    · `router`      — clasifica el input y decide la acción (charla · control de widgets · lanzar proceso · escalar).
    · `fast_client` — cliente del modelo rápido NO-razonador, **modelo POR INVOCACIÓN** (Ollama local / Grok
                      AIMLAPI), nunca una env global de modelo (concurrencia de sesiones).
    · `frontend`    — gestor de frontend/widgets (emite el protocolo de tags `[[show]]`/`[[close]]`/…).
    · `procs`       — lanzador/gestor de procesos (widgets backed, tareas de navegador…).
    · `escalate`    — puente al SlowBrain cuando el turno pide memoria/tools/razonamiento.
  Se enchufa al motor de voz como provider `livekit.agents.llm.LLM` (misma costura que `duo`), en V2-004.

- **SlowBrain** (`nucleo/dispatch.py` + `nucleo/memory_agent.py` + `nucleo/agentes/`) — deliberación **async**:
  una constelación de agentes **Claude Code** tras la interfaz `CodeAgent` (sustituible por Codex; modelo por
  invocación). Dispatcher + agente de MEMORIA ★ (compone el contexto mínimo desde `memory/`) + agentes de
  trabajo (web/código/otros). El resultado vuelve por los raíles de siempre: `voice/proactive` + `voice/brain_notes`.

- **Loop orquestador** (`nucleo/loop.py`, ~1 Hz) — el hilo del tiempo: tareas programadas (cron propio),
  🔥 chispas (pensamiento espontáneo), dispara el consolidador ("sueño") de la memoria, y reporta por voz+UI.

Substratos compartidos (NO son parte del cerebro): la **memoria** (`memory/`, V2-002/003) y el **Sistema
Nervioso** (`bus/`, V2-001, ya construido).
"""

__all__ = ["flash", "agentes"]

# Marcador de fase: desde V2-004 el FlashBrain SÍ está cableado a la voz (provider `nucleo`, opt-in con
# BRAIN=nucleo, en paralelo a duo/hermes). El default de arranque sigue siendo `duo` hasta el cutover de V2-009.
WIRED_TO_VOICE = True
