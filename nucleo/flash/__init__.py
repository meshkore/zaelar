"""nucleo/flash/ — FlashBrain: la capa refleja sub-segundo del cerebro v2.

Código propio (no un agente externo) que cierra cada turno de voz. Router de input + cliente de modelo
rápido no-razonador (modelo POR INVOCACIÓN) + gestor de frontend/widgets + lanzador de procesos + escalado
al SlowBrain. Se enchufa al motor de voz como provider `livekit.agents.llm.LLM` (V2-004). Esqueleto en V2-001.
"""
