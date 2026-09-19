"""
test_a_fresh_show_needs_no_stored_card.py — opening a NEW card must never touch the record it has not stored yet.

Incident 2026-09-19: no widget could be opened at all. The worker-background fix (adb76984) added
`this._bringFront(w.card)` to show()'s FRESH branch, where `w` is still undefined (`let w =
this.wins.get(id)` missed, `this.wins.set(id, w)` comes later) — a TypeError before _place, before the
data fetch, before anything. The same commit also named the undeclared `background` flag from
_renderAliases, createWidget's error branch and maximize — a ReferenceError on the aliases panel, on a
failed generation and on every maximize. Four hunks, one root cause: background-focus guards pasted
where neither `w` nor `background` exists.
"""
import pathlib
import re

DESKTOP = pathlib.Path("frontend/app/widgets/desktop.js")


def _src() -> str:
    return DESKTOP.read_text(encoding="utf-8")


def _show_span(lines):
    start = next(i for i, l in enumerate(lines) if re.match(r"\s*async show\(rawId", l))
    end = next(i for i in range(start + 1, len(lines)) if re.match(r"  (async )?\w+\(", lines[i]))
    return start, end


def fresh_branch_of_show(src: str) -> str:
    """Text of show()'s `if(fresh){...}` up to (not including) `this.wins.set(id, w)`."""
    lines = src.splitlines()
    start, end = _show_span(lines)
    body = lines[start:end]
    fresh_open = next(i for i, l in enumerate(body) if "if(fresh){" in l.replace(" ", ""))
    store = next(i for i, l in enumerate(body) if "this.wins.set(id, w)" in l)
    assert store > fresh_open
    return "\n".join(body[fresh_open:store])


def background_code_lines(src: str):
    """0-based line numbers where the `background` identifier is used as code.

    CSS lives in the same file (`background:...`, `transition:background ...`) along with prose about
    it in comments — property lines and all comments are excluded. What remains must be show()'s own
    parameter at work.
    """
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.DOTALL)
    out = []
    for i, l in enumerate(src.splitlines()):
        code = l.split("//", 1)[0]
        if "background" in code and "background:" not in code and ":background" not in code:
            out.append(i)
    return out


def test_a_fresh_card_never_reads_the_record_it_has_not_stored_yet():
    """`w` is undefined until `this.wins.set(id, w)` — any `w.` read before that kills every new open."""
    branch = fresh_branch_of_show(_src())
    branch = branch.replace("w={", "").replace("w = {", "")
    assert "w." not in branch


def test_background_is_only_named_where_it_is_declared():
    """`background` is show()'s parameter — naming it anywhere else is a ReferenceError."""
    src = _src()
    lines = src.splitlines()
    start, end = _show_span(lines)
    for i in background_code_lines(src):
        assert start <= i < end, (
            f"`background` used outside show() at line {i + 1}: {lines[i].strip()[:100]}"
        )
