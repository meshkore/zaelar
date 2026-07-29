# Prompt de relevo — construcción autónoma de zaelar v2 «Colmena»

Copia el bloque de abajo en un Claude Code nuevo (contexto en blanco), en
`/Users/ricartjuncadella/Documents/Prj/asimovia/zaelar`. También sirve como prompt de `/loop`.

---

Eres el agente de construcción de **zaelar v2 «Colmena»** (asistente de voz personal, castellano). Trabajas en
`/Users/ricartjuncadella/Documents/Prj/asimovia/zaelar`, rama `feat/v2-colmena`, **MeshKore Standard v27**.
Estás **entierrando Hermes** y construyendo un cerebro propio (FlashBrain + SlowBrain) + memoria central.

## 1. Carga contexto (en orden)
- `CLAUDE.md` (reglas duras + decisiones clave).
- `.meshkore/roadmap/EPIC-v2-colmena.md` (el plan maestro: fate table, fases, orden, protocolo). **Manda.**
- La iniciativa abierta de menor `wall_order` (empieza por V2-001).
- Diseño: `/architecture` (pestañas Arquitectura/FlashBrain/SlowBrain/Memoria/Widgets) +
  `.meshkore/docs/architecture/zaelar-memory.md`.

## 2. El bucle (tu trabajo, una tarea por iteración)
1. Arranca/verifica zaelar (`curl -s localhost:8473/api/brain`; si no responde, `make run` y espera).
2. Coge la **primera tarea `status: next`** cuyas `depends_on` estén en `done` (`modules/<m>/tasks/T-NN-*.md`,
   orden de la tabla §4 del EPIC; empieza por V2-001 = T34).
3. Constrúyela en código, respetando la estrategia strangler-fig (construir en blanco → integrar tras flag →
   retirar lo viejo AL FINAL). No rompas el arranque actual (`BRAIN=duo` sigue siendo el default hasta V2-009).
4. Verifica: tests (`./.venv/bin/pytest` de lo tocado) + arranque limpio; reinicia si tocaste `.py`.
5. Pon la tarea en **`status: done`** (`completed_at` + `commit_shas`) y añade UNA línea fechada en la sección
   **## Bitácora** de su iniciativa.
6. `git add -A && git commit` (mensaje = qué construiste + verificación; termina con la co-autoría de abajo).
   **NUNCA `git push`** sin OK explícito del operador.
7. Si TODAS las tareas de la iniciativa están en `done` y su **Aceptación** se cumple → iniciativa `status: done`.
   Repite con la siguiente tarea.

## 3. Reglas duras (no negociar)
- **NO push** sin confirmación. Un commit por tarea.
- Core **sin Docker** (LiveKit nativo; memoria = SQLite embebido). Docker solo el tester.
- Cerebro de voz **no-razonador** (cierra el turno o se queda mudo). FlashBrain = modelo rápido no-razonador.
- **Modelo por invocación**, nunca variable de entorno global de modelo (concurrencia de sesiones).
- No crear módulos sin declararlos en `.meshkore/public/cluster.yaml`. No editar `state.json` a mano.
- Nada que configure el usuario final va en `.env` (config gestionada por la UI; env = fallback power-user).
- Si topas con una decisión de producto NO resuelta en el EPIC/iniciativa → anótala como *abierta* en la
  bitácora y salta a la siguiente tarea ejecutable. No bloquees la noche.

## 4. Estado al heredar
Rama `feat/v2-colmena`. Diagramas v2 commiteados (`/architecture`). Roadmap escrito (V2-001→V2-010).
Aún **nada de código v2 construido** — V2-001 es la primera tarea. zaelar sigue corriendo con Hermes/duo.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
