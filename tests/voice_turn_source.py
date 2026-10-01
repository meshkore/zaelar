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


def _splice(text: str, calls, aliases: str) -> str:
    """Put each block F1 extracted back in place of its call: (comment opening the call, the call, module, function).
    The indentation is the call's own; the outputs it binds back and its early-return sentinel are consumed."""
    for start, call, path, fname in calls:
        a = text.index(start)
        pad = re.match(r"[ \t]*", start).group(0)
        close = "\n" + pad + ")\n"
        b = text.index(close, text.index(call, a)) + len(close)
        rebind = re.compile(rf"{pad}if '\w+' in _blk:\n{pad}    \w+ = _blk\['\w+'\]\n"
                            rf"|{pad}if _blk\.get\('__return__'\):\n{pad}    return\n"
                            rf"|{pad}if isinstance\(_blk, tuple\):\n{pad}    return _blk\[1\] if len\(_blk\) == 2 else _blk\[1:\]\n")
        while (m := rebind.match(text, b)):     # the outputs the call binds back
            b = m.end()
        body = re.sub(rf"\b(?:{aliases})\.", "", _body_of(path.read_text(encoding="utf-8"), fname))
        body = body.replace('return {"__return__": True}', "return")     # the turn's own early return
        body = re.sub(r"\breturn _R, None\b(?=\s*(?:#.*)?$)", "return", body, flags=re.M)
        body = re.sub(r"\breturn _R, ", "return ", body)                  # a value the original returned
        extra = pad[4:]                          # the extracted body sits at 4 spaces
        text = text[:a] + "".join((extra + ln) if ln.strip() else ln for ln in body.splitlines(True)) + text[b:]
    return text


def turn_source() -> str:
    """The voice turn's code: the provider with the executor and the post-stream chain spliced back."""
    prov = PROVIDER.read_text(encoding="utf-8")
    k = prov.index(_ANCHOR)
    prov = prov[:k] + executor_body() + prov[k:]
    a = prov.index(_PS_START)
    b = prov.index(_PS_END, a) + len(_PS_END)
    prov = prov[:a] + post_stream_body() + prov[b:]
    prov = _splice(prov, _PROVIDER_CALLS, r"_p|_pst")
    # module-level helpers F1 moved out of the provider: read with it, as written there
    return _unlift(prov + "".join("\n" + _as_written(x) for x in _PROVIDER_MODULES))


#: Module-level helpers moved out of the provider (V2-778 F1), read as part of it by a source guard.
_PROVIDER_MODULES = (ENGINE / "voice" / "engine" / "llm" / "providers" / "pending_confirm.py",)


#: Blocks F1 moved out of `_run_inner` into a module of their own, called in place (V2-778 F1): (the comment that
#: opens the call, the call, the module, the function). Their bodies read the provider's names as `_p.<name>`.
_PROVIDER_CALLS = (
    ("        # V2-778 F1 — the end of the turn (dialog window", "_turn_after.close_the_turn(",
     ENGINE / "voice" / "engine" / "llm" / "providers" / "turn_after.py", "close_the_turn"),
    ("        # V2-778 F1 — the turn's prompt (spec, recall", "_turn_prompt.compose_the_prompt(",
     ENGINE / "voice" / "engine" / "llm" / "providers" / "turn_prompt.py", "compose_the_prompt"),
    ("        # V2-778 F1 — the turn's tool set (situational tools", "_turn_tools_mod.choose_the_tools(",
     ENGINE / "voice" / "engine" / "llm" / "providers" / "turn_tools.py", "choose_the_tools"),
    ("        # V2-778 F1 — admitting the turn (brief", "_turn_admit.admit_the_turn(",
     ENGINE / "voice" / "engine" / "llm" / "providers" / "turn_admit.py", "admit_the_turn"),
    ("        # V2-778 F1 — the turn the model did not answer", "_turn_failure.say_the_turn_failed(",
     ENGINE / "voice" / "engine" / "llm" / "providers" / "turn_failure.py", "say_the_turn_failed"),
    ("        # V2-778 F1 — the phrase accumulator (a fragment", "_turn_fragment.hold_a_fragment(",
     ENGINE / "voice" / "engine" / "llm" / "providers" / "turn_fragment.py", "hold_a_fragment"),
    # the post-stream chain's own blocks (spliced into it once it is back inside the turn)
    ("        # V2-778 F1 — holding the model to its words", "_ps_words.hold_the_model_to_its_words(",
     ENGINE / "nucleo" / "flash" / "post_stream_words.py", "hold_the_model_to_its_words"),
    ("        # V2-778 F1 — the light lanes the model chose", "_ps_lanes.run_the_light_lanes(",
     ENGINE / "nucleo" / "flash" / "post_stream_lanes.py", "run_the_light_lanes"),
    ("        # V2-778 F1 — settling what is pending", "_ps_settle.settle_what_is_pending(",
     ENGINE / "nucleo" / "flash" / "post_stream_settle.py", "settle_what_is_pending"),
)


#: Other files F1 split, and the modules their code moved to. A guard that reads the old file reads them all,
#: concatenated: the moved code stays contiguous, so an «X before Y» assertion inside it keeps its meaning.
DISPATCH = ENGINE / "nucleo" / "dispatch.py"
_SPLIT = {DISPATCH.resolve(): [ENGINE / "nucleo" / "dispatch_listener.py", ENGINE / "nucleo" / "dispatch_session.py",
                              ENGINE / "nucleo" / "dispatch_prepare.py"],
          (ENGINE / "nucleo" / "workers" / "session.py").resolve(): [ENGINE / "nucleo" / "workers" / "session_notes.py"],
          (ENGINE / "server" / "voice_api.py").resolve(): [ENGINE / "server" / "canvas_api.py"],
          (ENGINE / "voice" / "attention.py").resolve(): [ENGINE / "voice" / "interrupt_grammar.py"],
          POST_STREAM.resolve(): [ENGINE / "nucleo" / "flash" / f"post_stream_{x}.py" for x in ("words", "lanes", "settle")],
          (ENGINE / "widgets" / "navegador" / "owner.py").resolve(): [ENGINE / "widgets" / "navegador" / "owner_login.py",
                                                                    ENGINE / "widgets" / "navegador" / "owner_actions.py",
                                                                    ENGINE / "widgets" / "navegador" / "owner_page.py"]}


PROBE = ENGINE / "nucleo" / "flash" / "probe.py"
PROBE_AFTER = ENGINE / "nucleo" / "flash" / "probe_after.py"
#: (marker that opens the call in run_turn, last line of the call, the function whose body goes back there)
_PROBE_CALLS = (
    ("    # V2-778 F1 — executing the decision lives in", "        return_extra_exec = _blk['return_extra_exec']\n",
     "execute_what_was_decided"),
    ("    # V2-778 F1 — answering a web search lives in", "        spoken = _blk['spoken']\n", "answer_a_search"),
    ("    # V2-778 F1 — the words the turn owes live in", "        spoken = _blk['spoken']\n", "the_words_it_owes"),
    ("    # V2-778 F1 — naming the turn's action from what", "        video_req = _blk['video_req']\n", "name_the_action",
     ENGINE / "nucleo" / "flash" / "probe_decide.py"),
    ("    # V2-778 F1 — the mirrors of the voice backstops", "        spoken = _blk['spoken']\n",
     "mirror_the_voice_backstops", ENGINE / "nucleo" / "flash" / "probe_mirrors.py"),
    ("    # V2-778 F1 — composing the turn (memory ingest", "        tool_calls = _blk['tool_calls']\n",
     "compose_the_turn", ENGINE / "nucleo" / "flash" / "probe_before.py"),
    ("    # V2-778 F1 — preparing the model stream", "        spec = _blk['spec']\n",
     "prepare_the_stream", ENGINE / "nucleo" / "flash" / "probe_before.py"),
)


def _body_of(src: str, fname: str) -> str:
    i = src.find(f"async def {fname}(")
    i = i if i >= 0 else src.index(f"\ndef {fname}(") + 1     # a sync block (V2-778 F1)
    i = src.index(") -> dict:\n", i) + len(") -> dict:\n")
    return src[i:src.index("    _out = ", i)]


def probe_source() -> str:
    """`probe.py` with what F1 moved to `probe_after.py` put back where it sat in `run_turn` (same indentation)."""
    prov = PROBE.read_text(encoding="utf-8")
    after = PROBE_AFTER.read_text(encoding="utf-8")
    for start, last, fname, *where in _PROBE_CALLS:
        a = prov.index(start)
        b = prov.index(last, a) + len(last)
        src = where[0].read_text(encoding="utf-8") if where else after
        prov = prov[:a] + re.sub(r"\b_probe\.", "", _body_of(src, fname)) + prov[b:]
    return _unlift(prov)


#: Moved bodies that read their old module's names through an alias; a guard reads them as they were written.
_ALIASED = {(ENGINE / "nucleo" / "dispatch_session.py").resolve(): "_d",
            (ENGINE / "server" / "voice_status.py").resolve(): "_va",
            (ENGINE / "nucleo" / "memory_agent" / "ingest_steps.py").resolve(): "_ing",
            (ENGINE / "nucleo" / "flash" / "live_blocks_nav.py").resolve(): "_lb",
            (ENGINE / "nucleo" / "flash" / "tool_executor_calls.py").resolve(): "_tx",
            (ENGINE / "nucleo" / "flash" / "tool_executor_widget_calls.py").resolve(): "_txw",
            (ENGINE / "voice" / "engine" / "pipeline" / "agent_events.py").resolve(): "_ag",
            **{(ENGINE / "nucleo" / "flash" / f"probe_{x}.py").resolve(): "_probe" for x in ("after", "decide", "mirrors", "before")},
            **{(ENGINE / "nucleo" / "flash" / f"post_stream_{x}.py").resolve(): "_pst" for x in ("words", "lanes", "settle")},
            (ENGINE / "voice" / "engine" / "llm" / "providers" / "pending_confirm.py").resolve(): "_p",
            (ENGINE / "nucleo" / "dispatch_prepare.py").resolve(): "_d",
            (ENGINE / "widgets" / "navegador" / "owner_login.py").resolve(): "_o",
            (ENGINE / "widgets" / "navegador" / "owner_actions.py").resolve(): "_o",
            (ENGINE / "widgets" / "navegador" / "owner_page.py").resolve(): "_o"}


def _as_written(x: Path) -> str:
    src = x.read_text(encoding="utf-8")
    alias = _ALIASED.get(x.resolve())
    return _unlift(re.sub(rf"\b{alias}\.", "", src) if alias else src)


_LIFTED = re.compile(r"(?m)^(?P<ind>[ \t]*)# V2-778 F1 — the body lives in `(?P<path>[\w/]+\.py)`; this closure passes "
                     r"what it closed over\.\n[ \t]*return (?:await )?\w+\.(?P<name>\w+)\(.*\)\n")


def _unlift(src: str) -> str:
    """Put every closure F1 lifted to a module function back in its thin closure, as it was written there."""
    import ast as _ast

    def _back(m):
        mod = ENGINE / m["path"]
        text = _as_written(mod)
        tree = _ast.parse(mod.read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name == m["name"])
        lines = text.splitlines(True)
        # the alias was stripped line by line, so line numbers still match the parsed module
        import io
        import tokenize
        depth, start = 0, fn.body[0].lineno - 1
        head = "".join(lines[fn.lineno - 1:fn.end_lineno])
        for t in tokenize.generate_tokens(io.StringIO(head).readline):   # the `:` closing the def header
            if t.type == tokenize.OP and t.string in "([{":
                depth += 1
            elif t.type == tokenize.OP and t.string in ")]}":
                depth -= 1
            elif t.type == tokenize.OP and t.string == ":" and depth == 0:
                start = fn.lineno - 1 + t.end[0]
                break
        body = lines[start:fn.end_lineno]       # comments between the header and the first statement included
        ind = m["ind"]
        return "".join((ind + ln[4:]) if ln.strip() else ln for ln in body)   # module body sits at 4 spaces
    return _LIFTED.sub(_back, src)


#: Files whose function bodies F1 cut into called blocks: read with each block put back where it sat.
_SPLICED = {
    (ENGINE / "server" / "voice_api.py").resolve(): (
        [("    # V2-778 F1 — the brain, the voice and its providers in the status", "_vstatus.brain_and_voice(",
          ENGINE / "server" / "voice_status.py", "brain_and_voice"),
         ("    # V2-778 F1 — the rest of the status and its overall light", "_vstatus.the_rest_and_the_light(",
          ENGINE / "server" / "voice_status.py", "the_rest_and_the_light")], "_va"),
    (ENGINE / "nucleo" / "memory_agent" / "ingest.py").resolve(): (
        [("    # V2-778 F1 — the gates an utterance crosses", "_ing_steps.gate_the_utterance(",
          ENGINE / "nucleo" / "memory_agent" / "ingest_steps.py", "gate_the_utterance"),
         ("    # V2-778 F1 — filing the atoms the distiller returned", "_ing_steps.file_the_atoms(",
          ENGINE / "nucleo" / "memory_agent" / "ingest_steps.py", "file_the_atoms")], "_ing"),
    (ENGINE / "nucleo" / "flash" / "live_blocks.py").resolve(): (
        [("            # V2-778 F1 — reading each live browser task", "_lbn.read_the_browser_tasks(",
          ENGINE / "nucleo" / "flash" / "live_blocks_nav.py", "read_the_browser_tasks"),
         ("            # V2-778 F1 — saying what the brain may claim about the browser", "_lbn.say_the_browser_state(",
          ENGINE / "nucleo" / "flash" / "live_blocks_nav.py", "say_the_browser_state")], "_lb"),
    (ENGINE / "server" / "__init__.py").resolve(): (
        [("    # V2-778 F1 — the engine's start (identity", "_boot.start_the_engine(", ENGINE / "server" / "boot.py",
          "start_the_engine")], "_srv"),
}


def _spliced(path: Path, text: str) -> str:
    calls, alias = _SPLICED.get(path.resolve(), ([], ""))
    present = [c for c in calls if c[0] in text]
    return _splice(text, present, alias) if present else text


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
        return _unlift("\n".join(_spliced(x, _as_written(x)) for x in [p, *_SPLIT[p.resolve()]]))
    return _unlift(_spliced(p, p.read_text(encoding="utf-8")))


def getsource(obj) -> str:
    """`inspect.getsource` for a source guard: the provider module (or its `_run_inner`) yields the whole turn."""
    import inspect
    if inspect.ismodule(obj) and getattr(obj, "__file__", None) and Path(obj.__file__).resolve() in _SPLIT:
        return read(obj.__file__)             # a split module is read with its moved pieces
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
    if mod == "nucleo.dispatch" and qual == "_run_session":          # the facade's delegate (V2-778 F1)
        from nucleo import dispatch_session      # read as it was written there: without the `_d.` the move added
        return re.sub(r"\b_d\.", "", inspect.getsource(dispatch_session._run_session))
    src = inspect.getsource(obj)
    try:                                      # a moved body reads its old module through an alias: read as written
        _file = Path(inspect.getfile(inspect.unwrap(obj)))
        alias = _ALIASED.get(_file.resolve())
        src = _spliced(_file, src)
    except TypeError:
        alias = None
    return re.sub(rf"\b{alias}\.", "", src) if alias else src
