#
# connectors/email — operator personal EMAIL connector (V2-051), integrated into the `mensajeria` widget.
#
# The CLEANEST of the three channel connectors: pure stdlib (imaplib/smtplib), NO Node bridge (WhatsApp) and no
# third-party lib (Telethon). Network logic vendored/adapted from Hermes' email adapter (mailbox.py). Reads the
# mailbox over IMAP (LOCAL triage, like WhatsApp/Telegram) and replies by SMTP with threading (reply capability,
# V2-051). Auth = IMAP/SMTP + app-password with presets (Gmail/Outlook/iCloud/Yahoo/other); OAuth2 = future Phase 2.
# Config MANAGED BY THE INTERFACE (config/connectors.py, gitignored + redacted); `.env` = power-user fallback.
#
# Pieces: config.py (knobs + presets), mailbox.py (pure IMAP/SMTP, testable without network), service.py (asyncio engine).
#
