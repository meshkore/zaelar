# Chain-loop — procedimiento del test→fix autónomo (iteración 2)

Loop autónomo continuo para el operador ausente. Sube el listón de `tests/voice/e2e/agent/fixloop-web-music.md`: prueba frases
HUMANAS y difusas, CADENAS multi-paso y TRAZAS (V2-044), en TODOS los dominios. **No preguntes. No pares. Asume la
mejor opción.** Commits cortos, bien documentados. **NUNCA push.**

## Cada disparo (un ciclo LARGO)

1. **Preflight.** `curl -s localhost:43917/api/flash/say -d '{"text":"hola"}'`. Si `ok:false` / reply vacío →
   FlashBrain caído (créditos/modelo). NO es bug de zaelar: documenta el bloqueo en la bitácora y termina el ciclo
   (no churnees). Si zaelar no responde de nada → `bash scripts/reset-memory.sh --yes` no; solo `make run` y espera.
2. **¿Operador en vivo?** `curl -s localhost:43917/api/status` → si `voice.state` ∈ {ok,on,active} hay sesión de voz
   → SALTA el ciclo (no reinicies con el operador hablando).
3. **Reset limpio** (solo si NO hay sesión viva): `make reset` (memoria + UI + sesiones/observabilidad a cero;
   conserva credenciales/conectores/config). Reinicia solo si tocaste `.py` desde el último arranque.
4. **Sweep.** `./.venv/bin/python -m tests.voice.e2e.agent.chain_suite` (completo) o `--sample 2` para rotación rápida, o
   `--domains music,chain,video` para enfocar un área. Guarda GREEN/YELLOW/RED + trazas.
5. **Traza de muestra.** `./.venv/bin/python -m tests.voice.e2e.agent.chain_suite --trace CHAIN-01` — confirma que la cadena
   texto→acción queda sellada con el mismo trace id (la observabilidad que pidió el operador).
6. **Diagnostica cada RED/YELLOW por COMPRENSIÓN.** Distingue:
   - **bug real** — la primera acción es objetivamente incorrecta (charla muda ante una orden, navegador para
     música, alucinar una data-op en un "ábreme X", escalar una data-op de datos, no escalar una reserva ITV).
   - **rigidez del check** — la acción es aceptable pero el predicado era estrecho → relaja el check (documenta).
   - **varianza del titular de entonces** — falla 1-2× y acierta a la 3ª (YELLOW por reintentos): NO es bug; no toques prosa a lo
     loco (whack-a-mole). Solo actúa si falla las 3 (RED consistente).
   - **hueco de producto** — funcionalidad no implementada (listas/favoritos): NO se arregla aquí → HUECO en roadmap.
7. **Decide: arreglar o diferir.**
   - **Simple** (prosa de descripción de tool, guard determinista, predicado): arréglalo, re-testéalo, commit corto.
   - **Complejo** (plan del worker, cadena real, nueva capacidad): NO lo arregles a medias → anótalo en
     `tests/voice/e2e/agent/chain_roadmap.md` con el ID del caso + severidad + por qué es del developer.
8. **Documenta.** Añade la entrada al roadmap (abiertos/cerrados) + una línea a la bitácora de ciclos.
9. **Commit corto** por cambio coherente. NUNCA push.
10. **Repite** (el cron re-dispara).

## Régimen (invariantes del loop)

- Los bugs P0 (corrupción de datos: data-op alucinada en show, supersede que borra identidad) tienen prioridad
  absoluta — si aparecen, arréglalos y verifícalos con un guard determinista (unit test del helper de router),
  no solo con el probe (que es no-determinista).
- El probe NO ejecuta workers/rails → la cadena COMPLETA (worker→web→widget) NO se verifica aquí; se verifica el
  HEAD (primera acción + instrucciones del handoff) + el sellado de traza. La cadena completa es observación del
  camino real (vista Trazas ◷⛓) — anótala como verificación manual si un caso lo requiere.
- No conviertas varianza en bug. Retry×3 ya de-ruida; si un caso oscila, el fix es entender POR QUÉ el modelo
  duda (prompt/descripción ambigua) o aceptar la varianza — nunca hardcodear tablas de verbos (feedback operador).
- El objetivo es un catálogo que, cuando el developer arregle un plan complejo, se re-corra entero y confirme.

## Objetivos vivos

- FlashBrain como CABEZA fiable: cada dominio → primera acción correcta con frases humanas variadas.
- Cadenas: identificar→reproducir (música), buscar candidatos→reproducir (vídeo), dato→acción (widget).
- Handoff: cuando escala, el `request` describe el plan (no escalado vacío).
- Trazabilidad: todo estímulo nace trazado y su decisión queda sellada.

## Bitácora de ciclos

_(cada disparo añade su resumen fechado aquí)_
