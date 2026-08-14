#
# WhatsApp triage connector (INI-014; unified store in INI-015) — zaelar reads the operator's personal WhatsApp and
# only interrupts with what DESERVES attention, marking already-summarized content as read. Read-only + mark-read.
#
# Boundary with Hermes (doc: .meshkore/docs/architecture/zaelar-hermes-federation.md): the Baileys bridge is a
# vendored COPY from Hermes in connectors/whatsapp/bridge/ (patches marked // ZAELAR-PATCH), immune to
# `hermes update`. The classifier is SHARED (connectors/messaging), LOCAL by default (Ollama), and does NOT go
# through the Hermes agent -> nothing personal leaves the machine and the voice ACP invariant is preserved.
#
# Modules: bridge/ (Node, vendored) · bridge_proc (lifecycle+QR) · client (HTTP) · service (engine). Triage, the
# unified store, proactive notice, brief, and tag dispatch live in connectors/messaging/ (common to all platforms).
# Bridge config is in config.py.
#
