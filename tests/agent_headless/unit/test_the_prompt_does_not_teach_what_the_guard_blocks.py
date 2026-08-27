"""We were telling the worker to do the exact thing our own permission gate refuses.

Measured across the whole first US batch (2026-08-27): every one of the four rounds carried the same internal
errors — `Contains simple_expansion`, `Contains brace with quote character (expansion obfuscation)` — and in
`cheapest-monitor__us` they cost the round: three navigations, ten searches, **zero structured products**.

The cause was ours. `worker_bridge act` is how the worker ASKS for a web search, and the prompt taught it as
`act <accion> <json>` with the JSON pasted on the command line — which is precisely what the gate blocks. The
same prompt already taught the correct two-step `@file` form for the results sheet, and `read_payload` had
grown `@file` support for `act` on that same day (V2-379); only the sentence that teaches it was left behind.
So the worker hit a wall it had been aimed at, improvised, and sometimes never recovered.

These tests pin the shape of the instruction, not its wording: what must never come back is a prompt that
shows inline JSON for a bridge, or that stays silent about the two rejections a worker will actually meet.
"""
from __future__ import annotations

import re

from nucleo import dispatch_prompts as DP


def _worker_prompt() -> str:
    """What the worker actually READS — built, not scraped from module constants.

    Both halves are built per worker: `_build_prompt` carries the bridge instructions and `_drawer_rules` the
    shell ones. Reading module constants instead would have made the first test pass on an empty string.
    """
    return "\n".join([
        DP._build_prompt("busca hoteles", "", True),
        DP._drawer_rules("/usr/bin/python"),
    ])


def test_no_bridge_is_taught_with_inline_json():
    """`act <accion> {json}` is the pattern the gate refuses. Any bridge shown that way is a trap we set."""
    text = _worker_prompt()
    offenders = re.findall(r"worker_bridge act [^\n@]*\{", text)
    assert not offenders, f"the prompt still teaches inline JSON to a bridge: {offenders}"


def test_the_file_form_is_taught_instead():
    text = _worker_prompt()
    assert "worker_bridge act" in text
    assert "@" in text and re.search(r"worker_bridge act [^\n]*@", text), \
        "the worker is never shown the `@fichero` form for the bridge it uses to ask for searches"


def test_and_the_two_rejections_it_will_meet_are_named():
    """A rule the worker cannot connect to the error it just got is a rule it will not apply. The gate's own
    words are what appears in its transcript, so the prompt uses them."""
    text = _worker_prompt()
    assert "simple_expansion" in text, "nothing tells the worker what the expansion rejection means"
    assert "brace with quote" in text, "nothing connects the JSON rejection to writing a file instead"


def test_the_shell_rules_still_forbid_the_expansions_themselves():
    """Sensitivity: naming the error must not replace forbidding the cause."""
    text = _worker_prompt()
    assert "$(…)" in text and "${…}" in text
