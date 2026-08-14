#
# messaging — SHARED layer for triaged personal messaging (INI-015). One mental model for ANY platform (WhatsApp,
# Telegram and, later, email): per-platform connectors (connectors/whatsapp, connectors/telegram) handle transport +
# pairing; THIS layer provides what is common to all:
#
#   · triage.py  — the LOCAL, platform-agnostic classifier (Ollama by default; does NOT go through the Hermes agent
#                  -> privacy + voice ACP invariant). Promoted from connectors/whatsapp.
#   · store.py   — the UNIFIED store (widgets/_data/mensajeria.json): per-platform link state + one item list across
#                  ALL platforms + pending_read queue (with its platform).
#   · notify.py  — the shared proactive notice (voice + [SYSTEM] note) and "what deserves attention" filter.
#   · brief.py   — the combined NUMBERED brief the brain sees (one list -> [[msg.read:N]] maps correctly).
#
# Boundary with Hermes (doc: .meshkore/docs/architecture/zaelar-hermes-federation.md): the classifier is LOCAL and
# NEVER goes through the Hermes agent; no personal data leaves the machine.
#


async def dispatch_tag(action: str, extra: dict) -> None:
    """Route a [[msg.*]] emitted by the brain (voice/chat/duo — never cluster turns: operator-only).

    read:N / dismiss:N / clear -> same mutation as the unified widget buttons (apply_action over the unified store).
    The action does NOT need to know the platform: item N already carries its `platform`, and each connector drains
    its part of `pending_read` (actual mark-read on its platform). Never raises."""
    try:
        from widgets.mensajeria import data
        name = action.split(".", 1)[1] if "." in action else action
        payload = {"n": extra.get("n")} if extra.get("n") is not None else {}
        data.apply_action(name, payload)
    except Exception:
        pass
