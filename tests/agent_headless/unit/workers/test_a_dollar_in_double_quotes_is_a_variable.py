"""A price with `$` inside double quotes is a shell variable (demo pass 30, 2026-09-28).

«find me three 27 inch 4k monitors, under 400 bucks» — the worker wrote `agent_report plan "…under $400…"` and the
permission gate refused it: «Contains simple_expansion». It happened in 12 of the last 14 demo passes, with Z.ai and
with DeepSeek alike. Measured against the CLI: `"under $400"` is refused, `'under $400'` and `"under \\$400"` pass
(and plain bash would have turned the text into «under 00»). The prompt listed `$(…)` and `${…}` and never the bare
`$` of a price.

And the trace blamed the wrong command: `agent_report` paints no row, so its rejection fell back to the LAST step
and the log said «navegador ⚠️ error» on a `nav_cli scroll down` that had succeeded.
"""
from nucleo import dispatch_prompts as DP
from nucleo.workers.claude_session import ClaudeCodeSession


def test_the_prompt_says_a_dollar_in_double_quotes_is_a_variable():
    text = DP._drawer_rules("/usr/bin/python")
    assert '"under $400"' in text and "\\$400" in text, "the worker is never told how to write a price"


def _session():
    s = object.__new__(ClaudeCodeSession)
    s._task_id, s._native_sid, s._model, s._done = "7", "", "m", False
    return s


def test_a_rejection_is_blamed_on_the_command_that_was_refused():
    s = _session()
    tool = lambda i, cmd: {"type": "tool_use", "id": i, "name": "Bash", "input": {"command": cmd}}
    list(s._map({"type": "assistant", "message": {"content": [tool("a", "python -m nucleo.nav_cli scroll down")]}}))
    list(s._map({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "a", "content": "scrolled"}]}}))
    refused = 'python -m nucleo.agent_report plan "under $400|verify"'
    list(s._map({"type": "assistant", "message": {"content": [tool("b", refused)]}}))
    evs = list(s._map({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "b", "content": "Contains simple_expansion", "is_error": True}]}}))
    res = [e for e in evs if e.type == "step_result"][0]
    assert res.data["cmd"] == refused, res.data
