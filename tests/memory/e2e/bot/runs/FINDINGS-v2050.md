# Hallazgos del cron test→fix de memoria (V2-050) — pendientes

Los gates deterministas (precisión + slots + supersede) manejan bien los átomos CORRECTOS (verificado
aislado). Estos fallos son de CALIDAD del DESTILADOR LLM (qwen2.5:7b, temp 0) bajo contexto acumulado,
NO gaps de gate → no se arreglan con un gate de precisión ni con tablas de palabras (doctrina).

## Abierto (corpus v1, ventana 0..30) — 2026-07-17

- **v1 #24/#29 — mensaje entrante mal destilado. [RESUELTO 2026-07-17]** «Me escribió Carlos por WhatsApp…»
  → el LLM alucinaba un placeholder. Fix: BACKSTOP `_INCOMING_MSG_RE` (me escribió/dijo/mandó/contó/llamó/
  avisó) que guarda el TEXTO CRUDO a largo (hermano de _COMMITMENT_RE), con guard de negación vacía
  (_EMPTY_MSG_RE «no me dijo nada»). +2 controles en test_write_precision_v2050. Verificado: v1 0..40 4→2 fallos.
- **v1 #20/#28 — objetivo. [RESUELTO 2026-07-17]** Dos gaps DETERMINISTAS (no era LLM): (1) el CORAZÓN
  DOBLE-namespacea el slot (`operator.goal.current`) → `canonical` no lo reconocía → sin state_field. Fix:
  `canonical` quita el prefijo `operator.` si el resto es un slot conocido. (2) el CORAZÓN mete el NOMBRE DEL
  SLOT como clave del estado (`state_patch={"goal.current":…}`) → clave STRAY que nunca supersede → objetivo
  viejo persistía. Fix: `_sanitize_state_patch` renombra slot→state_field. Verificado v1 0..30 28/30→30/30;
  +2 controles en test_write_precision_v2050.

Nota: el destilador es temp 0 (determinista), así que estos fallos son REPETIBLES en v1 0..30 — el tick
seguirá marcándolos FIX hasta que se aborde la calidad del destilador (fewshots/backstop/modelo), no los gates.

## Abierto (corpus v2, ventana 0..110) — 2026-07-17 [PENDIENTE, aplazado por el operador]

- **v2 #107 — negativa a revelar un secreto se guardó como dato.** «Mi contraseña del banco NO te la voy a decir
  nunca» → debía DESCARTARSE (no es un dato, es una negativa a darlo) pero quedó en ['long']. Gap probable en el
  destilador/gate: una frase que REHÚSA dar un dato no es una píldora. Reproducir aislado (v2 #107) y añadir gate +
  control (una preferencia legítima sobre el banco NO debe rechazarse). NO tocado en esta sesión.
