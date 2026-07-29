# V2-072 — Pacto de conversación agente-agente (3er nivel de reglas negociadas)

**Estado:** F0 CONSTRUIDO (rama `feat/v2-069-una-sola-mente`, commit engine `8d9c615`). 2026-07-25.

## Origen

Petición del operador tras V2-071: además del **filtro DURO** del sistema, hacen falta **reglas** en niveles. El
sistema ya tiene reglas de sistema (genética/seguridad) y reglas de usuario (`state.rules`). Falta un **tercer
nivel**: reglas que forman parte de las **conversaciones** y se **negocian entre los dos agentes** sobre la marcha —
p. ej. «el código se hace por repositorio, no por mensajes», «vamos más lentos en las comunicaciones para no gastar
tokens», «esta colaboración es solo charla/análisis, o también código». Detonante concreto: **zalo se quejó de que
le bombardeábamos con mensajes** (gasto de tokens); si lo pactáramos, podríamos aplicar un delay.

Matiz clave del operador: **solo tiene sentido en el túnel agente-agente** (cluster), no en una conversación con un
humano por WhatsApp. Se puede **proponer al abrir** la conversación (saludo), quedar sujetos mientras convenga, y
**enmendar/añadir** normas en cualquier momento; un agente incluso puede **preguntar** por las reglas al otro.

## Principio — jerarquía de reglas

**(1) SISTEMA / duro > (2) OPERADOR > (3) PACTO negociado.** El pacto opera DENTRO de lo que permiten los niveles
superiores: **nunca afloja** una regla dura ni una del operador, y **solo puede restringir NUESTRA conducta**
(cadencia, medio, alcance), jamás conceder capacidades (eso lo gobierna el nivel 1 en código). Vocabulario CERRADO
por seguridad. Es «una sola mente»: la mente conduce la negociación en prosa; nosotros capturamos el acuerdo
estructurado y lo aplicamos de forma determinista.

## Arquitectura

- **Estado por-relación en la cápsula** (`capsule.pact`): `{cadence_s, medium: repo|channel, scope:
  chat|analysis|code, note, by: peer|operator}` + `last_out_ts` (para la cadencia). Scope-partido/cuarentenado como
  el resto de la cápsula; no toca el estado del operador.
- **Vocabulario CERRADO** (`capsule._clean_pact`): sanea toda propuesta (del tag o del operador) a esos campos;
  descarta lo demás (un pacto no puede meter «run_command»). Cadencia acotada a `[0, CADENCE_MAX_S=600]`.
- **Tag `[[cluster.pact:<cluster>]]{to,cadence_s,medium,scope,note}[[/cluster.pact]]`** (hermano de `cluster.send`
  en `voice/tag_protocol.py`; en la allowlist del turno de cluster `bridge._CLUSTER_TURN_ALLOWED`): la mente lo emite
  al ACORDAR normas con el peer → `capsule.pact_set(..., by="peer")`.
- **Propuesta al SALUDAR** (`capsule.PACT_DEFAULT_PROPOSAL`, inyectada en los saludos a peers nuevos): propone normas
  eficientes (esperar respuesta / sin ráfagas · código por repo · acordar alcance). Reconcilia **V2-067**: sigue sin
  proponer objetivo/tarea (eso lo decide el operador), pero SÍ normas de comunicación.
- **Aplicación**:
  - **Prompt**: `capsule.pact_compose(cap)` inyecta el bloque «PACTO DE ESTA CONVERSACIÓN» en cada turno, por DEBAJO
    del trailer de seguridad (nivel 1) y de las reglas del operador (nivel 2). Marca si las fijó el operador (mandan).
  - **Cadencia REAL** (enforcement, no solo hint): en `cluster.send`, `capsule.cadence_wait` calcula lo que falta y
    el bridge **espera** (`asyncio.sleep`, tope defensivo) antes de mandar → no más ráfagas. Sella `last_out_ts`.
- **Jerarquía en código**: `pact_set` con `by="operator"` no lo puede pisar un pacto posterior del peer.

## Alcance y no-alcance

- Solo canal de cluster (agente-agente). El chat/voz/WhatsApp con humanos NO lo usan.
- El pacto no reemplaza la protección DURA de recursos (V2-071): son complementarios — V2-071 nos protege aunque no
  haya pacto; el pacto es el acuerdo mutuo y explícito (mejor ciudadanía, bidireccional).

## Testing

`connectors/meshkore/test_pact.py` (15): parseo del tag, saneado al vocabulario cerrado (descarta basura, clampa
cadencia), jerarquía operador>peer, cadencia real (cuenta atrás), composición del bloque. **Nodo 6.6** del mapa de
tests. 153/153 (meshkore+voz) verdes.

## Fases

- **F0 (hecho):** modelo + tag + propuesta al saludar + inyección + cadencia real + jerarquía + tests + docs.
- **F1 (abierto, no deuda):** endpoint REST/voz para que el OPERADOR fije/consulte el pacto de un peer explícitamente;
  pacto a nivel de CLÚSTER (no solo por-peer); negociación multironda más rica (propuesta→contrapropuesta→acuerdo con
  captura); exponer el pacto vigente en `/api/meshkore/status` (junto al balance de recursos de V2-071).
