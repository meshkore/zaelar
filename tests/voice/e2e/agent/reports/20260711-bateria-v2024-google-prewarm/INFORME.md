# Informe de test — 2026-07-11 · Batería completa tras V2-024 (Google search + prewarm)

Batería de 14 escenarios, con settle de 12s entre escenarios (2ª pasada). zaelar con la última versión (búsqueda
Google gratis vía Chromium + prewarm del arranque). Evaluado con la **lente de dos velocidades**: FlashBrain rápido
(bug si se atasca) vs SlowBrain/Claude Code async (lento por diseño, NO es bug).

## Tabla de resultados
| Escenario | Estado | Overall | lat | Lectura |
|---|---|---|---|---|
| conversation | FAIL | 2 | 2 | repite saludos + turn-taking frágil (STT sucio) |
| agenda | FAIL | 2 | 2 | ⚠️ **>360s: añadir cita escala al SlowBrain code-agent** (bug de diseño, no del FlashBrain) |
| memory | FAIL | 2 | 3 | "RAG failure" por **recorte de input →1600** (context loss) |
| widget | FAIL | 2 | 3 | mismo recorte de contexto |
| search | FAIL | 1 | 2 | F1: snippets sin el dato → "no lo encuentra"; 14s en esa query |
| busqueda_web | FAIL | 2 | 2 | **busca bien (uti/acc 4)**; baja por repetición + nombre mal (STT) |
| **mensajeria** | **PASS** | **4** | 5 | muestra widget + estado OK; juez marca doble-show idempotente |
| conectores | FAIL | 2 | 2 | info ok (uti 4), desconexión dice/hace |
| complex_idea | FAIL | 2 | 3 | alucinación de entidades (STT) |
| **chat** | **PASS** | **5** | 5 | impecable (canal texto, sin pipeline de voz) |
| paste | FAIL | 3 | 4 | resume bien; ruido en el filtrado |
| websocket | FAIL | 2 | 3 | STT garbló "cluster"→"ballet" (ruido del arnés) |
| navegador_moto | FAIL | 1 | 3 | ignora parámetros + bucle robótico; no entregó resultados |
| navegador_coche | FAIL | 3 | 2 | **escala y EJECUTA la tarea**; falla precisión de precio (STT de criterios) |

Resumen: **2 PASS (chat 5, mensajería 4), 12 FAIL** — pero los FAIL están MUY inflados por ruido del arnés.

## Hallazgos REALES (a arreglar) — separados del ruido
1. **[DISEÑO] Data-op de widget escala al SlowBrain** — `add_meeting` es `safe:false` → "añade una cita" arranca un
   agente de código (nada que programar) → **cuelga >6 min**. Es el bug de la agenda. Causa: el flag `safe` conflag
   "¿data-op rápida?" con "¿irreversible?". **→ En manos de otro agente (prompt de arquitectura de widgets ya
   entregado): las mutaciones de datos las hace el FlashBrain directo; solo el CÓDIGO va al SlowBrain; guía de uso
   como estándar del widget.**
2. **[LATENCIA/CONTEXTO] Recorte de input →1600** (`✂️ input recortado`) causa "RAG failure"/pérdida de contexto en
   turnos largos (memory, widget). Revisar `ZAELAR_FAST_MAX_INPUT`/`attention.clamp_input` — el clamp está comiendo
   contexto útil.
3. **[BÚSQUEDA] Calidad en queries sin widget** — "quién ganó la CARRERA de F1" no tiene widget limpio y Google no
   sirve AI Overview a headless → snippets a veces sin el dato → "no lo encuentro". Weather/fútbol sí clavados.
   Fiabilidad dura = key Perplexity/Tavily (auto-sube). Latencia de búsqueda: dato ~1-2s, turno total 4-6s (2º pase).
4. **[NAVEGADOR] Bucle robótico / no entrega** en moto — over-escalación en turnos de ACK pasivo + no cierra la
   entrega. coche SÍ ejecutó la tarea (precio mal por STT de los criterios).

## Ruido del arnés (NO son bugs de zaelar)
- STT Deepgram del tester garbla sin parar: "zaelar"→"Arbe/Árix", "cluster"→"ballet", nombres, criterios numéricos.
  Invalida turnos Y **ensucia la memoria real** con nombres mal (se prueba contra la cuenta viva).
- Rigidez del juez: doble-show idempotente = "duplicado"; "no lo encuentro" honesto = "alucinación".
- Contención del worker THREAD: el settle ayudó (desapareció el all-1s de conversation; latencias 2-3 en vez de 1).

## Latencia antes/después (V2-024)
- 1er turno: 8s cold-start → **~1s** (prewarm lo absorbe en el arranque). ✓
- Búsqueda: DDG 4-11s (turno 18-34s) → Google **~1-2s** (turno 4-6s). ✓
- Chat steady-state: ~1.5s (sin cambios, ya iba bien).

## Siguiente
- Esperar el arreglo de arquitectura de widgets (otro agente) → re-probar agenda (debe ir instantánea por FlashBrain).
- Revisar el clamp de input (hallazgo 2).
- Considerar key Perplexity/Tavily para búsqueda estructurada dura (hallazgo 3).
