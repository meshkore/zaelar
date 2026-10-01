"""The source of the VOICE TURN, for the tests that guard it by reading its code (V2-778 F1-10, 2026-10-01).

Until F1-10 the voice turn was one coroutine, `_run_inner` in `voice/engine/llm/providers/nucleo.py`, and ~60
source guards read that one file. F1 splits it: the tool executor now lives in `nucleo/flash/tool_executor.py`
(built by the provider per turn) and the post-stream chain in `nucleo/flash/post_stream.py` (awaited by it).
The guards still ask the same question — «does the voice turn do X, and before Y?» — so they read the turn's code as it runs: the provider with the executor's body put back where it
used to sit (just before `_tool_fired`) and the chain's body in place of its call, both at their old indentation.
Their positional assertions keep their meaning.

This is a reading aid for source guards, not a runtime: a behavioural test builds the executor itself.
"""
from __future__ import annotations

import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
PROVIDER = ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py"
EXECUTOR = ENGINE / "nucleo" / "flash" / "tool_executor.py"
POST_STREAM = ENGINE / "nucleo" / "flash" / "post_stream.py"

_ANCHOR = "        _tool_fired: set = set()\n"
_BODY_START = '    `on_tool_call`, `resolve_confirm`, `start_web_auth`."""\n'
_BODY_END = "    return SimpleNamespace("


#: The executor's widget half (split from it, V2-778 F1): its closures come FIRST, as they did in `_run_inner`.
EXECUTOR_WIDGET = ENGINE / "nucleo" / "flash" / "tool_executor_widget.py"
_W_BODY_START = '        _late["on_tool_call"](name, args)\n'


def executor_body() -> str:
    """The closures of `tool_executor.build` (its widget half first), re-indented to where they sat inside
    `_run_inner`."""
    w = EXECUTOR_WIDGET.read_text(encoding="utf-8")
    wi = w.index(_W_BODY_START) + len(_W_BODY_START)
    src = EXECUTOR.read_text(encoding="utf-8")
    i = src.index(_BODY_START) + len(_BODY_START)
    j = src.index(_BODY_END, i)
    body = w[wi:w.index(_BODY_END, wi)] + src[i:j]
    return "".join(("    " + ln) if ln.strip() else ln for ln in body.splitlines(True))


_PS_START = "        # V2-778 F1-10b — the post-stream chain lives in"
_PS_END = '        spoken_text, _op_text = _ps["spoken_text"], _ps["_op_text"]\n'
_PS_BODY_START = '    """The post-stream chain of ONE turn. Returns `{"spoken_text", "_op_text"}`."""\n'
_PS_BODY_END = '    return {"spoken_text": spoken_text, "_op_text": _op_text}\n'


def post_stream_body() -> str:
    """The body of `post_stream.run`, re-indented to where it sat inside `_run_inner`."""
    src = POST_STREAM.read_text(encoding="utf-8")
    i = src.index(_PS_BODY_START) + len(_PS_BODY_START)
    j = src.index(_PS_BODY_END, i)
    return "".join(("    " + ln) if ln.strip() else ln for ln in src[i:j].splitlines(True))


def turn_source() -> str:
    """The voice turn's code: the provider with the executor and the post-stream chain spliced back."""
    prov = PROVIDER.read_text(encoding="utf-8")
    k = prov.index(_ANCHOR)
    prov = prov[:k] + executor_body() + prov[k:]
    a = prov.index(_PS_START)
    b = prov.index(_PS_END, a) + len(_PS_END)
    prov = prov[:a] + post_stream_body() + prov[b:]
    for start, call, path, fname in _PROVIDER_CALLS:
        a = prov.index(start)
        b = prov.index("\n        )\n", prov.index(call, a)) + len("\n        )\n")
        rebind = re.compile(r"        if '\w+' in _blk:\n            \w+ = _blk\['\w+'\]\n")
        while (m := rebind.match(prov, b)):     # the outputs the call binds back
            b = m.end()
        body = re.sub(r"\b_p\.", "", _body_of(path.read_text(encoding="utf-8"), fname))
        prov = prov[:a] + "".join(("    " + ln) if ln.strip() else ln for ln in body.splitlines(True)) + prov[b:]
    return prov


#: Blocks F1 moved out of `_run_inner` into a module of their own, called in place (V2-778 F1): (the comment that
#: opens the call, the call, the module, the function). Their bodies read the provider's names as `_p.<name>`.
_PROVIDER_CALLS = (
    ("        # V2-778 F1 — the end of the turn (dialog window", "_turn_after.close_the_turn(",
     ENGINE / "voice" / "engine" / "llm" / "providers" / "turn_after.py", "close_the_turn"),
    ("        # V2-778 F1 — the turn's prompt (spec, recall", "_turn_prompt.compose_the_prompt(",
     ENGINE / "voice" / "engine" / "llm" / "providers" / "turn_prompt.py", "compose_the_prompt"),
)


#: Other files F1 split, and the modules their code moved to. A guard that reads the old file reads them all,
#: concatenated: the moved code stays contiguous, so an «X before Y» assertion inside it keeps its meaning.
DISPATCH = ENGINE / "nucleo" / "dispatch.py"
_SPLIT = {DISPATCH.resolve(): [ENGINE / "nucleo" / "dispatch_listener.py"],
          (ENGINE / "nucleo" / "workers" / "session.py").resolve(): [ENGINE / "nucleo" / "workers" / "session_notes.py"],
          (ENGINE / "server" / "voice_api.py").resolve(): [ENGINE / "server" / "canvas_api.py"],
          (ENGINE / "voice" / "attention.py").resolve(): [ENGINE / "voice" / "interrupt_grammar.py"]}


PROBE = ENGINE / "nucleo" / "flash" / "probe.py"
PROBE_AFTER = ENGINE / "nucleo" / "flash" / "probe_after.py"
#: (marker that opens the call in run_turn, last line of the call, the function whose body goes back there)
_PROBE_CALLS = (
    ("    # V2-778 F1 — executing the decision lives in", "        return_extra_exec = _blk['return_extra_exec']\n",
     "execute_what_was_decided"),
    ("    # V2-778 F1 — answering a web search lives in", "        spoken = _blk['spoken']\n", "answer_a_search"),
    ("    # V2-778 F1 — the words the turn owes live in", "        spoken = _blk['spoken']\n", "the_words_it_owes"),
)


def _body_of(src: str, fname: str) -> str:
    i = src.index(f"async def {fname}(")
    i = src.index(") -> dict:\n", i) + len(") -> dict:\n")
    return src[i:src.index("    _out = ", i)]


def probe_source() -> str:
    """`probe.py` with what F1 moved to `probe_after.py` put back where it sat in `run_turn` (same indentation)."""
    prov = PROBE.read_text(encoding="utf-8")
    after = PROBE_AFTER.read_text(encoding="utf-8")
    for start, last, fname in _PROBE_CALLS:
        a = prov.index(start)
        b = prov.index(last, a) + len(last)
        prov = prov[:a] + _body_of(after, fname).replace("_probe.", "") + prov[b:]
    return prov


def read(path) -> str:
    """`Path.read_text` for a source guard: the provider path yields the whole turn, a split file its pieces,
    anything else its file."""
    p = Path(path)
    if not p.is_absolute():
        p = ENGINE / p
    if p.resolve() == PROVIDER.resolve():
        return turn_source()
    if p.resolve() == PROBE.resolve():
        return probe_source()
    if p.resolve() in _SPLIT:
        return "\n".join(x.read_text(encoding="utf-8") for x in [p, *_SPLIT[p.resolve()]])
    return p.read_text(encoding="utf-8")


def getsource(obj) -> str:
    """`inspect.getsource` for a source guard: the provider module (or its `_run_inner`) yields the whole turn."""
    import inspect
    name = getattr(obj, "__name__", "") or ""
    qual = getattr(obj, "__qualname__", "") or ""
    if name == "voice.engine.llm.providers.nucleo" or qual == "NucleoLLMStream._run_inner":
        return turn_source()
    if name == "nucleo.dispatch":
        return read(DISPATCH)
    if name == "server.voice_api":
        return read(ENGINE / "server" / "voice_api.py")
    if name == "voice.attention":
        return read(ENGINE / "voice" / "attention.py")
    if name == "nucleo.flash.probe":
        return probe_source()
    if getattr(obj, "__module__", "") == "nucleo.flash.probe" and qual == "run_turn":
        src = probe_source()
        i = src.index("async def run_turn(")
        j = src.find("\ndef ", i)
        k = src.find("\nasync def ", i + 10)
        ends = [x for x in (j, k) if x != -1]
        return src[i:min(ends)] if ends else src[i:]
    mod = getattr(obj, "__module__", "") or ""
    if mod == "nucleo.dispatch" and qual == "run_listener":          # the facade's delegate (V2-778 F1-11)
        from nucleo import dispatch_listener
        return inspect.getsource(dispatch_listener.run_listener)
    return inspect.getsource(obj)
