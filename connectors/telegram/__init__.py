#
# Telegram triage connector (INI-015) — zaelar reads the operator's PERSONAL Telegram (Telethon userbot, account
# linked by QR) and only interrupts with what DESERVES attention, marking already-summarized content as read.
# Read-only + mark-read (autoresponder out of scope, as in WhatsApp).
#
# Boundary with Hermes (doc: .meshkore/docs/architecture/zaelar-hermes-federation.md): Telegram is "black-box lib" —
# it uses NOTHING from Hermes (Hermes only brings the Bot API, which cannot read personal chats), so there is NO
# bridge to vendor. Pure in-process Python (asyncio). The classifier is the SHARED one (connectors/messaging), LOCAL
# by default -> nothing personal leaves the machine; does NOT go through the Hermes agent (voice ACP invariant intact).
#
# Triage writes the UNIFIED store (widgets/_data/mensajeria.json, platform="telegram"); the single messaging widget
# READS it. Voice control ([[msg.*]]) and the numbered brief are SHARED (connectors/messaging).
#
