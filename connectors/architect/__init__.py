#
# Architect connector — zaelar's link to the shared MeshKore daemon (the Architect "remote control"): one more
# CODE/PROJECT PROVIDER in the catalog, next to the ones that already build widgets (headless Claude Code, Hermes).
# The brain DECIDES (emits [[architect.*]] tags); the work is done by each project's architect-master inside the
# daemon; the result comes back through voice/proactive (voice+UI) and voice/brain_notes ([SISTEMA] note) — the
# same async fire-and-forget loop the widget generator uses. All activity is visible in the operator's cockpit.
#
# Security: these tags are OPERATOR-ONLY — an untrusted cluster peer turn can never emit them (the bridge's
# allow-list only admits cluster.send/done). The bearer token lives in .env (gitignored) and is never rendered
# into briefs or spoken output.
#


async def dispatch_tag(action: str, extra: dict):
    """Route a [[architect.*]] tag emitted by the brain (voice, chat or deep turns — never cluster turns)."""
    from connectors.architect import service
    if action == "architect.ask":
        await service.ask(extra.get("project") or "", extra.get("request") or "")
    elif action == "architect.new":
        await service.new_project(extra.get("data"))
