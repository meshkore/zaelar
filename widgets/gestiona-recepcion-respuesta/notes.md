# notes — gestiona-recepcion-respuesta

- 2026-07-27 (creación): widget que gestiona la RECEPCIÓN y RESPUESTA al mensaje nuevo de **Estefanía** en
  **WhatsApp**. Muestra el mensaje entrante, permite guardar un borrador de respuesta y marca el estado en tres
  pasos: **recibido → respondiendo → respondido**.
- **Restricción CLAVE del operador / V2-061 (no regresar):** el widget es un **ESPEJO**, no ejecuta el envío. La
  interacción debe completarse en el **SISTEMA REAL** (conector de mensajería / WhatsApp), no solo en el widget
  local. `mark_replied` NO envía nada: solo refleja que el envío real ya se completó y actualiza el estado. El
  envío de verdad lo hace el conector `mensajeria` / el cerebro, fuera de aquí.
- Acciones (data-ops, todas reversibles → ninguna `confirm`): `draft_reply` (guarda borrador, pasa a
  'respondiendo'), `mark_replied` (marca respondido en el sistema real, guarda el texto enviado), `reset` (vuelve
  a 'recibido'). Sincronizadas 1:1 con `apply_action` (gate de validación).
- Foreground-only a propósito: la recepción viva de WhatsApp la gobierna el widget `mensajeria` (backed); este es
  un tracker enfocado a UN mensaje, sin `tick()`/background.
- Estilo: clases propias con prefijo `.grr-` (evita colisiones con clases globales bare); todo color vía
  `var(--hb-*)`; texto entrante/enviado por `textContent` (untrusted WhatsApp → anti-XSS).
