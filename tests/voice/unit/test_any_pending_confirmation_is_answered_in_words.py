"""Every «¿lo hago?» the agent asks can be answered in words — typed or said — not only with the button
(operator, 2026-09-28: «sí, te autorizo» has to send it for real).

Two readers: a clear yes/no is resolved before the model (`classify_reply`); anything else — «acepto que lo
envíes», another language — reaches the model with the tool that resolves the pending confirmation. That tool was
described as resolving a DELETION only, so over a pending SEND the model had no reason to reach for it."""
from nucleo.flash import router, router_catalog
from widgets import confirm


def test_the_plain_answers_resolve_before_the_model():
    for yes in ("yes", "sí", "yes, I authorize it", "sí, te autorizo", "go ahead", "ok send it"):
        assert confirm.classify_reply(yes) == "yes", yes
    for no in ("no", "no, don't send it"):
        assert confirm.classify_reply(no) == "no", no


def test_the_tool_is_offered_whenever_something_waits_for_his_yes():
    names = lambda ctx: {t["function"]["name"] for t in router.tools(ctx)}  # noqa: E731
    assert "confirm_widget_delete" in names(router.tool_context(confirm_pending=True, auth_pending=False))
    assert "confirm_widget_delete" not in names(router.tool_context(confirm_pending=False, auth_pending=False))


def test_the_tool_says_it_resolves_any_pending_confirmation_not_only_a_deletion():
    spec = next(t for t in router_catalog.TOOLS if t["function"]["name"] == "confirm_widget_delete")
    desc = spec["function"]["description"]
    assert "ENVIAR un mensaje" in desc and "CUALQUIER" in desc
