#
# connectors/email — conector de EMAIL personal del operador (V2-051), integrado en el widget `mensajeria`.
#
# El conector más LIMPIO de los tres canales: stdlib puro (imaplib/smtplib), SIN bridge Node (WhatsApp) ni lib de
# terceros (Telethon). Lógica de red vendorizada/adaptada del adaptador de email de Hermes (mailbox.py). Lee el
# buzón por IMAP (triaje LOCAL, como WhatsApp/Telegram) y responde por SMTP con threading (capacidad de responder,
# V2-051). Auth = IMAP/SMTP + app-password con presets (Gmail/Outlook/iCloud/Yahoo/otro); OAuth2 = Fase 2 futura.
# Config MANEJADA POR LA INTERFAZ (config/connectors.py, gitignored + redactado); `.env` = fallback power-user.
#
# Piezas: config.py (knobs + presets), mailbox.py (IMAP/SMTP puro, testeable sin red), service.py (motor asyncio).
#
