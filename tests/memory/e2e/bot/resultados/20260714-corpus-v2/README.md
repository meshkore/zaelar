# Corpus v2 del test bot de memoria — preparado 2026-07-14 (post-auditoría V2-038)

Segundo corpus (`tests/memory/e2e/bot/cases2.py`), hermano de la GOLD `cases.py` (1032, persona Ricart). Motivación
tras la auditoría del sistema de memoria: (1) **genericidad/multi-operador** — la GOLD es 100 % "Ricart de Barcelona",
justo el sesgo que la auditoría quitó de los fewshots; (2) cubrir las **4 capacidades NUEVAS** de la auditoría.

## Qué es
- **Persona NUEVA:** Amaia Etxeberria, de Logroño (profesora de física → divulgadora científica; pareja Iván, hija
  Kattalin, gato Otto, hermano Xabier en Berlín; alérgica a la penicilina; trilingüe es/eu/fr). Anclas sin colisión
  con la GOLD.
- **650 casos, 33 dimensiones** (las 29 de la taxonomía + 4 nuevas):
  - **AD** señal `change` multiidioma (mudanza/cambio de oficio en es/fr/telegráfico → estado + supersede).
  - **AE** registro canónico de slots / colapso de linajes (step `slot_count`).
  - **AF** escritura EXTERNA de workers `remember_external` (step `worker_write`: ok / identidad-vetada / rechazo).
  - **AG** saneo `heal_slots` del consolidador (step `heal_slots`).
- Estructura: cimientos → bloques incisivos → inventario de vida (saves tempranos) → familias autocontenidas →
  **queries DIFERIDAS** (retención a profundidad) → identidad cross-sesión al final. Familias data-driven → crecer
  a ~1000 es trivial (añadir tuplas distintas, no relleno; disciplina de `EXIGENCIA.md`).

## Cómo se corre (BD/progreso/catálogo AISLADOS de la GOLD; requiere Ollama local)
```bash
python -m tests.e2e.memory.bot.runner --corpus v2 --coverage
python -m tests.e2e.memory.bot.runner --corpus v2 --fresh --range 0 650
python -m tests.e2e.memory.bot.runner --corpus v2 --catalog     # → CATALOG2.md
```

## Baseline de humo `[0,46]` (2026-07-14, `qwen2.5:3b` + embeddinggemma) = **42/46**
La maquinaria NUEVA de la auditoría funciona end-to-end: `worker_write` (los 3 gates), `slot_count` (colapso a 1),
y las mudanzas AD actualizan el estado **incluida la de francés** ("je viens de déménager à Bilbao" → estado=Bilbao).

Los 4 rojos son HALLAZGOS reales que el ciclo tría (no fallos del test):
1. **#12 / #29** — un `save` a LARGO no persiste (Xabier→Berlín, magnesio): **write-completeness de `qwen2.5:3b`**
   (la auditoría ya lo señaló; mejora con `MEM_PROCESSOR_MODEL=qwen2.5:7b`, ahora configurable). No es del test.
2. **#31** — recall por categoría de salud con fraseo vago: sensibilidad de fraseo del retriever = **frontera T178**
   documentada (la agregación de categoría sin puente léxico fuerte no aflora todo el cluster).
3. **#33** — la 1ª mudanza→estado ("acabo de mudarme a Vitoria") no actualizó el slot esa vez (sí las siguientes,
   #35 Pamplona y #39 Bilbao): **no-determinismo del CORAZÓN** en el routing perfil→estado (fenómeno conocido).

## Estado
PREPARADO y runnable. Pendiente (opcional, protocolo): crecer a ~1000 por tandas con checkpoints de `EXIGENCIA.md`,
y una pasada de ORO completa (`--corpus v2 --fresh --range 0 650`, ~30-60 min con Ollama) para el triaje completo.
