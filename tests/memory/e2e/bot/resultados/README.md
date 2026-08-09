# Registro de corridas de benchmark de la memoria

Cada carpeta es una corrida REAL, versionada, con `report.md` (tabla legible) y `report.json` (detalle por caso,
incluidos los **fallos concretos** de cada modelo). Se guardan a propósito: cuando alguien pregunta *«¿por qué
usamos este modelo?»* la respuesta no debería exigir volver a gastar en llamadas.

- **Veredictos y razonamiento** → `.meshkore/docs/ops/zaelar-model-benchmarks.md` §12.3 (destilar) y §12.4 (REM).
- **Respuesta corta y canónica** → `.meshkore/docs/architecture/zaelar-memory.md` §Modelos de la memoria.
- **Arneses** → `../distiller_bench.py` (CORAZÓN) y `../rem_synth_bench.py` (sueño REM); tarifas en `../prices.json`.

## Corridas

| carpeta | qué mide | por qué existe |
|---|---|---|
| `20260809-distiller-bench-fase1` | CORAZÓN · **21 candidatos**, 1 pasada, 34 casos, 4 ejes | cribado de la ronda de PRECIO: quién se queda cerca del titular |
| `20260809-distiller-bench-fase2` | CORAZÓN · 8 finalistas, **3 pasadas** | varianza — separar señal de suerte de una pasada |
| `20260809-distiller-bench-fase2b` | CORAZÓN · `gpt-4o-mini` por AIMLAPI, 3 pasadas | re-medición LIMPIA: por OpenAI directo el rate-limit (21 muertas de 102) fingía mala calidad |
| `20260809-rem-synth-bench-ronda2` | REM · **11 candidatos**, 3 pasadas, 8 grupos, 6 ejes | la ronda buena; incluye potentes y razonadores |
| `20260809-rem-synth-bench-verif` | REM · verificación del marcador | cazó el artefacto «no devolver nada aprobaba el eje `null`» |
| `20260809-rem-synth-bench-confirm` | REM · 3 finalistas | destapó la inestabilidad de DeepSeek (99,0% ↔ 64,5%) → era `max_tokens=1200` truncando |
| `20260809-rem-synth-bench-final` | REM · 4 finalistas, ya con `max_tokens=4000` | la corrida que sostiene el veredicto de §12.4 |
| `20260720-distiller-bench` | CORAZÓN · ronda V2-056 (16 casos) | histórico — **superado** por §12.3 |
| `20260720-rem-synth-bench` | REM · ronda V2-056 (3 grupos) | histórico — **superado** por §12.4. ⚠️ Mide un código que dejó de ejecutarse poco después (el `KeyError` del prompt, ver §12.4): no es evidencia vigente |
| `20260712-ciclo-1000`, `20260714-corpus-v2` | recall/escala del bot de memoria | otras líneas de evaluación (taxonomía A–X), no elección de modelo |

## Cómo leer un `report.json`

- `misses` / `notes` — los fallos CONCRETOS por caso. Es lo más útil: dice *qué* pierde cada modelo, no solo cuánto.
- `spread` — el valor de cada pasada por eje. Un modelo con 98% y spread `[98, 98, 98]` no es lo mismo que uno con
  98% y spread `[100, 96, 98]`.
- `dead_calls` — llamadas que no devolvieron nada. **Si es alto, el número de calidad NO significa nada**: mira
  primero si el endpoint estaba limitando la tasa antes de juzgar al modelo.
- `avg_in_tok` / `avg_out_tok` — tokens REALES del proveedor (no estimados), que es de donde sale el $/1k turnos
  y el $/año.
