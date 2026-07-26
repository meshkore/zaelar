# gestiona-mensaje-recibido — notas

- Widget creado para hacer SEGUIMIENTO LOCAL del mensaje nuevo recibido de Gonza en WhatsApp: apuntar si se dio
  por atendido o qué borrador de respuesta se quiere mandar, y que el estado mostrado (pendiente/procesado/
  respondido) refleje SIEMPRE la acción real ejecutada (nunca un "hecho" cosmético sin haber mutado el store).
  Tres acciones: `process` (atendido sin responder), `reply` (GUARDA un borrador local — nunca `confirm:true`,
  no es irreversible: `reopen` lo deshace siempre), `reopen` (deshace, vuelve a pendiente).
- **FIX 2026-07-26 (auditoría, hallazgo P0 — bug de confianza del operador):** el manifest/UI originales decían
  "envía una respuesta real a Gonza por WhatsApp" y pedían confirmación como si fuera irreversible, pero
  `apply_action("reply", …)` SOLO escribía `db["reply_text"]` — nunca llamó a `connectors.messaging`/
  `connectors.whatsapp` ni a la cola `pending_reply`/`reply_message` (el mecanismo REAL de envío, documentado en
  `CLAUDE.md`). El operador podía confirmar "sí, envíasela" creyendo que Gonza lo recibió, y NO se enviaba nada —
  exactamente el antipatrón que V2-061/Susurro existen para cazar. Corregido para que el widget sea honesto (es
  un tracker/borrador local, sin `confirm`) en vez de fingir una integración que no tiene. Además, un canal de
  mensajería nuevo NUNCA debería ser un widget propio (regla dura de `CLAUDE.md` — todo va DENTRO de
  `mensajeria`); si en el futuro se quiere responder de VERDAD a Gonza, ha de hacerse desde el widget
  `mensajeria` (`reply_message`), no aquí.
