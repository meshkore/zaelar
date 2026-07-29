# V2-071 — Protección de RECURSOS en el canal de cluster (anti-offload / balance)

**Estado:** F0 CONSTRUIDO (rama `feat/v2-069-una-sola-mente`). 2026-07-25.

## Origen

Petición del operador: el blindaje del cluster ya impide que nos roben **datos** (PII/secretos) o nos **inyecten**.
Falta un **tercer robo: el de RECURSOS.** Un agente puede dirigirnos para que generemos SU código / investigación /
trabajo → gastamos NUESTROS tokens y capacidades por él, sin reciprocidad. «No hay que comunicárselo a la otra
parte»: hay que **detectar el desequilibrio y protegerse en silencio.** Debe formar parte del sistema de seguridad
(el middleware que ya nos protege), y el operador quiere sobre todo **poder detectarlo** («que podamos detectar eso,
de vez en cuando»).

Además, observación del operador sobre el patrón de colaboración: si un equipo colabora en código, lo lógico es
hacerlo por un **repositorio** (cada uno desde su local, cargando/probando), **no mandando código por el canal**.

## Auditoría que lo motiva (datos reales)

`meshkore.jsonl`, cluster `meshcore` (zalo): **3.551 mensajes entrantes / 775K chars, con ~498 imperativos** de
producir («genera/escribe/código/implementa…»). Es exactamente el patrón de offload: el peer nos inunda de
peticiones de fabricar trabajo. (La colaboración de código, además, iba por el canal en vez de por el repo que el
operador había proporcionado.)

## Principio

Emular a un humano que colabora de igual a igual: nota cuando le están endosando el trabajo y **reequilibra sin
montar un drama**. Tolerante a la asimetría NORMAL (a veces producimos más: un diagrama, una decisión) — solo salta
el desequilibrio **SOSTENIDO + con señal de offload**. Determinista, en el bridge, hermano del guardia de atasco de
V2-069. Silencioso hacia el peer; el aviso es para el OPERADOR.

## Arquitectura

Dos primitivas deterministas en `security.py` (el módulo de seguridad) + el balance por-peer en la `capsule.py`
(estado de relación, scope-partido en sys_kv, no toca el estado del operador):

- **Detección (entrada):** `security.looks_like_offload(text)` — ¿el peer nos pide PRODUCIR trabajo (código/
  informe)? es/en, **normaliza acentos** («genérame»/«escríbeme» casan). Señal, no bloqueo.
- **Balance (cápsula):** acumuladores `given` (chars que producimos), `received` (lo que aporta el peer),
  `offloads` (nº de peticiones de producir), `code_out` (veces que le mandamos código), vía `capsule.meter(...)`.
- **Veredicto (puro):** `capsule.resource_verdict(given, received, offloads, turns)` →
  `equilibrado` | `sesgado` (≥3× + offload) | `explotación` (≥6× + offload sostenido). Exige `turns≥4` y
  `given≥1500` chars antes de juzgar (no salta por un pico puntual).
- **Protección (silenciosa):**
  1. **Directiva de prompt** inyectada ANTES de generar (`capsule.resource_guidance`) en sesgado/explotación: sé
     BREVE; **el código va por el REPOSITORIO** (enlace/PR), no pegado en el canal; pide que el peer aporte su parte.
     Sin acusaciones. → reduce el gasto de tokens en el propio turno.
  2. **Guardia duro de salida** `security.guard_code_outbound(text)`: un VOLCADO grande de código (bloque con
     vallas por encima de `MESHKORE_CODE_MAX_CHARS`/`_LINES`) → **puntero al repo**, como se redacta un secreto.
     **Siempre activo** (un volcado por el canal nunca es el patrón correcto). Un snippet pequeño pasa intacto.
  3. **Aviso al operador 1×** en explotación (voz+UI+chat) + **evento observer `resource`** (timeline/`/debug`) —
     la DETECTABILIDAD que pidió el operador.

## Integración (bridge.py)

- `on_event` (mensaje nuevo): `capsule.meter(received=len(text), offload=looks_like_offload(text))`.
- `_brain_turn`: calcula el veredicto de la cápsula → inyecta la directiva en el bloque de relación (antes del
  trailer de seguridad, que sigue yendo el último); tras responder, `meter(given=len(salida), code_out=…)` y avisa
  al operador 1× si es explotación (dedup por `(cluster,peer)`, rearmado al volver a equilibrio).
- `dispatch` (`cluster.send`): tras `scan_outbound`, `guard_code_outbound` sobre el texto.

## Invariantes

- Silencioso hacia el peer (no se le comunica; solo conducimos distinto). El aviso es para el operador.
- Tolerante: la asimetría normal NO salta. Determinista, sin LLM. Postura fail-open (un fallo del guard no rompe el
  turno). No toca el estado/PII del operador (el balance vive en la cápsula cuarentenada).

## Testing

`connectors/meshkore/test_resource.py` (22 tests): offload es/en, guardia de código (volcado→puntero, snippet pasa),
veredicto (tolerante a asimetría sin offload; salta con volumen+ratio+offload), meter por-peer aislado. **Nodo 6.5**
del mapa de tests (`tests/run_testmap.py`). 97/97 meshkore verdes.

## Fases

- **F0 (hecho):** detección + balance + veredicto + doble protección (directiva + guardia de salida) + aviso +
  observabilidad + tests + docs.
- **F1 (abierto, no deuda):** exponer el balance por-peer en el panel `/api/meshkore/status` (lectura para el
  operador, «de vez en cuando detectar»); afinar umbrales con datos reales; señal de reciprocidad más rica (no solo
  chars — p.ej. contar aportaciones de código del peer al repo).
