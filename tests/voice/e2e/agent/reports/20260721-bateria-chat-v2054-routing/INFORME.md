# Batería 2026-07-21 — canal CHAT (V2-054) · routing · memoria · bóveda (V2-060)

Sesión de testing pedida por el operador tras el merge a main de V2-060 (bóveda de secretos), V2-058 (música
Spotify), V2-057 (verificación/rutas temporales) y **V2-054 §1 (modo CHAT = voz OFF)**. Encargo: probar random por
dominios, incorporar tests del canal chat sin voz, arreglar lo simple, recoger lo complejo, sin interferir, usando/
extendiendo la memoria real (datos ficticios permitidos).

## Estado del sistema
- main @ `9af3a22` (merge V2-060). Server + LiveKit arriba. Corazón `gpt-4.1-mini` (OpenAI) VIVO, voz `gpt-4o-mini`,
  embeddings auto→Ollama, reranker local. Config sana (la temporal DeepSeek/Ollama-off ya estaba revertida).

## Qué se probó y resultados
| Dominio | Herramienta | Resultado |
|---|---|---|
| Routing multi-dominio (17 dominios) | `domain_sea.py all 1` (×varias pasadas) | **46/47** · lat p50 1.4-1.8 s. El único fallo residual (`quiero ver mis tareas`→chat) es el verbo AMBIGUO «ver», excluido a propósito (colisiona con «a ver si…») → territorio Susurro, no más regex. |
| **Canal CHAT sin voz (V2-054)** | `chat_convo.py` (NUEVO, multi-turno) | **12/13** — coherente, arrastra contexto («bajo un toldo… barbacoa»; «150-250 g para seis»), maneja corrección de nombre («Te llamas Marco»), dato factual en medio → search y vuelve a charla. Único: 1 pico de latencia (11 s) puntual (p50 1.9 s). |
| Memoria (datos ficticios, ingest=True) | probe | **✓✓** guardar hecho compuesto → recall → **corrección (12→21)** → recall corregido → **recall DURABLE en sesión nueva** devolvió el valor corregido. Corazón + supersede + retriever e2e correctos. |
| Bóveda de secretos (V2-060) | pytest + probe live | unit+integration **44/44** verdes. **INVARIANTE FAIL-CLOSED VERIFICADO EN VIVO**: secreto ficticio con ingest=True y sin bóveda → el valor NO aparece EN CLARO en reply, mapa de memoria, timeline, ni logs de sesión. Sin fuga. |
| Adversarial/edge | probe | delete→confirm ✓, math compuesto (4692) ✓, evento memoria ✓, latest→youtube ✓, marketplace→escalate ✓, dangling correction → pide aclaración (3/4) ✓. |

## Hallazgos y arreglos
### ARREGLADO — bug real de producto (commit `90f46b9`)
**Mostrar un widget solo se emitía ~50-65% de las veces.** El no-razonador NARRABA la acción («Te muestro el
reloj», «Te abro el reloj») sin emitir el tag `[[show]]` → `action=chat`. El backstop de promesa
(`promises_action`+`looks_like_show_strict`) NO se disparaba porque el gate `_PROMISE_RE` exigía el CLÍTICO («te LO
muestro») y se colaba la forma con objeto nominal directo. Fix: clítico OPCIONAL + enseñar/sacar. **Verificado:
abre el reloj 6/6, muéstrame la agenda 4/4, enséñame el reloj 3/3** (antes ~3/6). Sin regresión (test_router 23/23).
Beneficia voz Y probe (regex compartida). Borde conocido: entradas en INGLÉS aún no re-derivan (looks_like_show_strict
es es-only; zaelar es monolingüe español).

### ARREGLADO — fidelidad del arnés (commit `3dbadf7`)
**El probe daba veredictos falsos en «cierra todo»** (caía en `widget_data` ~60%). Producción SIEMPRE estuvo bien:
en voz/chat el hard-interrupt DETERMINISTA (`attention.hard_interrupt`, V2-015) resuelve «cierra todo»/«quita todo»/
«para» ANTES del LLM. El probe (impl PARALELA) no lo espejaba. Fix: mirror del hard-interrupt en `probe.py`.
Verificado: cierra todo 5/5 `canvas:close`, quita todo 3/3, para 2/2 chat.

### INCORPORADO — cobertura del canal chat (commit `e9d6eb6`)
`tests/voice/e2e/agent/chat_convo.py` — conversación MULTI-TURNO headless del canal voz-OFF (el lado cerebro del T1.4 pendiente),
registrado en el catálogo. Complementa al escenario single-shot `chat` de `scenarios.py`.

### CERRADO POR OTRA SESIÓN — `guardar secretos por voz` (commit `fc69fb5`, NO mío)
El primer test dio «No puedo guardar contraseñas directamente, anótala en un lugar seguro» (con ingest=false =
artefacto del probe). Otra sesión, EN PARALELO, ya lo arregló: detección amplia de secreto + short-circuit de
GUARDADO (cifra si hay bóveda; si no, pide crearla → «(hace falta crear la bóveda)»). No lo toqué.

## Observaciones inciertas → RESUELTAS en main estable
Durante el edge round 2, `git status` mostró `probe.py`/`router.py`/`nucleo.py` modificados sin commitear por OTRA
sesión (V2-060/V2-061 routing) → server con código a medias, veredictos no fiables. La otra sesión commiteó
(`cc74e56 fix(flash): mis-ruteo por verbo — pronombre suelto sobre widget ausente escala con contexto (V2-061)`);
reinicié a main ESTABLE y re-probé:
- `¿puedes quitar el reloj?` → **`canvas:close:clock` 4/4** ✓ — el `search` anterior era ARTEFACTO de su código a
  medias. RESUELTO (estado estable / su commit).
- `apúntame dentista el jueves a las 10` → **`escalate` 3/4** — PERSISTE en main estable. Un evento con fecha/hora
  debería ir a `add_meeting`/agenda, no escalar a un Brain Worker. **HALLAZGO REAL de routing** → para el dueño de
  V2-061 (router.py está EN CURSO por esa sesión; NO lo toqué para no colisionar).

**Sweep final en main estable: 46/47** (único fallo = `open the clock` EN, el borde monolingüe documentado).

## Pendiente para desarrollo (recoger)
1. `apúntame <cita> <fecha/hora>` → `escalate` en vez de `add_meeting`/agenda (routing, coordinar con V2-061).
2. Show-widget con entrada en INGLÉS aún no re-deriva por el backstop (es-only). Borde de bajo valor (monolingüe es).
3. Reply del no-vault secreto muestra señal semi-cruda `(hace falta crear la bóveda)` en vez de frase natural
   (cosmético, V2-060).

## Doctrina respetada
- Sin tablas de verbos hardcodeadas para routing (el fix del show es un BACKSTOP gated por promesa, patrón ya
  existente, no routing primario). Sin engordar el prompt.
- No se pisó trabajo de otra sesión: mis 3 commits son aditivos y limpios sobre lo suyo; NO commiteé sus ficheros
  modificados; me retiré del hammering activo al detectar el churn concurrente en los ficheros de routing.
- Testing por PROBE/HTTP (headless, no LiveKit) → no interfiere con la voz del operador. Memoria real extendida con
  datos ficticios (gestor Fernando Ruiz; secreto de prueba fail-closed → no persistió).
