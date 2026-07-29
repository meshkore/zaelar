# zaelar — Auditoría de arquitectura (2026-06-27)

> **HISTÓRICO** — snapshot pre-restructura (2026-06-30) y pre-auditoría global (2026-07-02). Los paths y
> claims de este documento reflejan el árbol antiguo (`voice/hermes_*`, `static/`, «cero cross-imports»).
> La foto vigente: `harbee-audit-2026-07-02.md` + `zaelar-architecture.md`. Remediación: INI-006/INI-007.

Revisión profunda del proyecto contra sus objetivos: piezas independientes, interacción limpia, escalabilidad
(miles de widgets), y **actualización de módulos externos (Hermes) sin interferir**. Incluye una auditoría
independiente (subagente con ojos frescos) + verificación estructural + **los arreglos ya aplicados**.

## Veredicto
**La arquitectura es sólida y, para ser un prototipo, inusualmente disciplinada.** Las tres capas grandes —
**voz**, **cerebro/Hermes** y **widgets** — están realmente separadas: verificado que hay **cero imports
cruzados** entre `widgets/` y el core de voz/cerebro, y al revés. Un widget roto **no puede tumbar** el audio.
Los contratos existen y son mayormente limpios. Los riesgos reales no son de acoplamiento, sino de: (1) el
**cerebro no conoce los widgets** todavía, (2) acoplamiento **frágil a Hermes** ante updates, y (3) algunas
suposiciones de escala que **leían disco en cada llamada** (ya corregido).

## Mapa: plan inicial → entregado
| Iniciativa (JARVIS plan) | Estado |
|---|---|
| I0 Cimientos (estructura, Makefile) | ✅ |
| I1 Hermes cerebro + **memoria** (regla de oro) | ✅ instalado, memoria persiste y se recupera entre sesiones (verificado: recuerda nombre+idioma) |
| I1.3/I1.4 cron + permisos/log | ✅ cron desatendido (gateway launchd); permisos vía tirith (auto-approve en voz) |
| I2 voz always-on | ✅ cascada + VAD navegador + barge-in + **streaming** ACP; ⏳ wake-word pendiente |
| Capa de **widgets** (no estaba en el plan; añadida) | ✅ agenda(coach) + search/tiempo, escritorio drag&drop, loader/boop |
| **SpeakerGate** (filtrar otras voces) | ✅ v1 (huella acústica); ⏳ v2 Picovoice Eagle |
| I3/I4/I5 importadores + canales + conectores | ⏳ pendiente (requiere cuentas del usuario) |
| I8 arnés E2E + juez | ✅ bot-vs-bot + juez Opus (texto) |

## Hallazgos por dimensión (con evidencia)

**1. Aislamiento — FUERTE (verificado).** `grep "import voice|brain|observer|voice_agent" widgets/` → 0. Único
borde: `from widgets.server_api import router` en server/__init__.py:15. Fallo de un widget → `desktop.close(id)`
(widgets-desktop.js:95), nunca alcanza el bucle de WebRTC/VAD. Store por-widget aislado (widgets/store.py).

**2. Contratos — MAYORMENTE LIMPIOS.** `render(el,data,ctx)`, API HTTP catalog-driven, API del escritorio
(show/close/list), cliente ACP. *Implícitos a mejorar:* el módulo de datos de un widget es **duck-typed**
(server_api proba `hasattr`), sin Protocol/ABC → un typo degrada a 404 silencioso; el shape de respuesta de
`action` no está estandarizado entre widgets.

**3. Escalabilidad a miles — CORREGIDO (parcial).** `runtime.catalog()` releía+parseaba todos los manifests en
**cada** llamada (y `identify()` corre en cada transcript). **Arreglado**: caché invalidada por mtime
(runtime.py). Pendiente: `identify()` sigue siendo lineal por keywords → a futuro, índice invertido o embeddings,
y mover la decisión al cerebro.

**4. Seguridad ante `hermes update` — ENDURECIDO (riesgo residual).** zaelar acopla a superficies de Hermes:
formas JSON-RPC de ACP (initialize/session-new/prompt/`agent_message_chunk`), flag `--accept-hooks`, binario
`~/.local/bin/hermes`, y la **persona en `~/.hermes/memories/MEMORY.md`**. **Aplicado**: guarda de versión en
`start()` (registra agentInfo+protocolo y avisa si cambia) y `stop()` que mata el proceso. **Pendiente (clave):**
un *contract-test* de ACP que se ejecute tras cada `hermes update` (ver playbook abajo). Ver tabla de
acoplamiento en NOTES/hermes/README.

**5. Voz ↔ Cerebro — OK.** Un proceso `hermes acp` por conexión (voice_agent.py); `ask()` bloqueante pero
marshalled con `run_in_executor`+cola asyncio (no bloquea el event loop); streaming de chunks → TTS; latencias
instrumentadas (ttft/ttfa/brain_ms). *Pendiente:* sin reconexión si el proceso muere a mitad; timeout de turno
(120s) muy largo.

**6. Datos/estado — CORREGIDO (parcial).** **Aplicado**: escrituras de store **atómicas** (temp+os.replace) y
lecturas con lock; la agenda **ya no muta el store en cada lectura** (GET idempotente, sin carrera RMW).
*Pendiente:* `server/state.py` es un dict global de proceso → ok mono-usuario local, cross-talk en multi-cliente.

**7. Seguridad/robustez — ENDURECIDO.** **Aplicado**: `wid` normalizado en TODOS los endpoints (traversal → 404,
verificado); **anti-XSS** en el widget de búsqueda (texto de la web por `textContent`, no `innerHTML`).
*Pendiente:* el scraping de DuckDuckGo es frágil (mejor enrutar por el buscador propio de Hermes); los permisos
de Hermes están en auto-approve durante la voz (decisión deliberada — cualquier tool corre sin confirmación).

**8. Gaps vs objetivos.**
- **El cerebro no conoce los widgets (ALTO).** `prompt.py` no tiene ninguna referencia a widgets; el disparo es
  100% regex en el front (assistant.html). El endpoint `coach_context` existe pero **nadie lo inyecta** → el rol
  coach está cableado en el server pero "muerto" en el cerebro. Esto incumple "los prompts se adaptan a las
  capacidades de los widgets". **Es la recomendación nº1.**
- **Widgets disparados por Hermes — no construido** (hoy intención en el front).
- **Persistencia de preferencias/layout de widgets — falta** (posición, z-order, "no me muestres X" → memoria).
- **Tests de contrato — faltan** (`make test` solo comprueba imports). Las superficies más frágiles (ACP, widget
  HTTP, identify, store) no tienen test.

## Arreglos APLICADOS en esta auditoría
1. Caché del catálogo (runtime.py) — fin del "disk storm" por petición.
2. Store atómico + lecturas con lock (store.py).
3. Agenda: plan derivado puro, sin mutar en lectura (data.py).
4. `wid` normalizado en todos los endpoints (server_api.py) — traversal bloqueado (404 verificado).
5. Anti-XSS en search/widget.js (web → `textContent`).
6. Guarda de versión de Hermes + `stop()` con kill (hermes_acp_client.py).

## Recomendaciones priorizadas (siguiente)
**Ahora (producto):**
1. **Hacer al cerebro consciente de los widgets**: inyectar `runtime.catalog()` (id/título/whenToUse) en el
   system prompt y que Hermes EMITA "muestra el widget X" (señal/tool) que un puente SSE→`desktop.show()`
   consuma; inyectar `coach_context` al mostrar la agenda. Mantener la regex del front solo como fast-path.
2. **Contract-test de ACP** (`make test-hermes`): abre sesión, prompt, comprueba el shape del chunk — correr tras
   cada `hermes update`.
**Pronto (robustez):** ciclo de vida del proceso ACP (reconexión + timeout al presupuesto de voz); declarar el
contrato del módulo de datos (Protocol/ABC); índice para `identify()` + desambiguación que muestre candidatos;
persistir preferencias/layout de widgets.
**Después (escala):** estado por-conexión (no global); sacar la intención de widgets del `onmessage` a un módulo
puente documentado; suite de tests de contrato (ACP, widget HTTP, identify, store).

## Playbook: actualizar Hermes sin romper zaelar
1. `cd zaelar && hermes update`.
2. Arrancar zaelar; revisar el log de `start()`: debe imprimir `Hermes ACP: <name> v<version> · protocol 1`. Si
   el protocolo ≠ 1 o cambia agentInfo → revisar `voice/hermes_acp_client.py` (formas ACP).
3. Probar una sesión de voz corta: saludo memory-aware (nombre+idioma) + una pregunta. Si el saludo o la memoria
   fallan, comprobar `~/.hermes/memories/MEMORY.md` (la persona vive ahí) y `~/.hermes/config.yaml` (provider/
   api_key/base_url). 4. (Recomendado, cuando exista) `make test-hermes`.

**Conclusión:** el esqueleto es correcto y el aislamiento es real — esto es un prototipo bien factorizado, no
spaghetti. La distancia entre "parece modular" y "es robusto" estaba en tres puntos (cerebro ciego a widgets,
acoplamiento a Hermes sin guardas, y escala disco-por-llamada); dos ya mitigados aquí, el primero es el próximo
gran paso. Todo abordable sin re-arquitecturar.
