"""A BACKTICK inside an injected <style> template literal ends the stylesheet and the module with it.

Half the app's chrome ships its CSS the same way: a component calls `injectStyles()`, which builds one
`<style>` whose body is a JS template literal. A template literal ends at its first unescaped backtick — so a
single backtick anywhere inside, **including inside a CSS comment**, closes the string early and turns the
rest of the block into raw JS. Two things make that expensive rather than merely wrong:

  · `node --check` does NOT catch it. The truncated remainder often still parses as valid JavaScript, so
    every syntax gate in this repo stays green and the file looks fine.
  · The failure is total and silent at RUNTIME: the module throws while evaluating, so the import never
    resolves, `window.__Desktop` never appears, and the whole canvas simply does not come up — with no CSS
    error, no console line naming the file, and nothing pointing at a comment.

`frontend/app/widgets/desktop.js` has carried a warning about this in its own text since V2-559 («no
backticks inside, ever»), and it was paid AGAIN in V2-689: four backticks landed in the prose of new CSS
comments (`.hb-scroll`, `_bringFront`, `right:70px`, `_dragHandle`) and took the desktop down whole — caught
only because a rendered e2e test waited 30s for a global that would never exist. A rule written in a comment
is not a rule; this is the same rule, measured.

SCOPE: every `…textContent = \\`` template in the frontend and in the widget catalog — the desktop shell, the
mobile shell, and every `widget.js`, since a generated widget injects its style exactly the same way
(`widgets/AGENTS.md`: «Inject your <style> once (id-guarded)»).
"""
from __future__ import annotations

import pathlib
import re

_ENGINE = pathlib.Path(__file__).resolve().parents[3]

#: `x.textContent = ` followed by a backtick — the shape every injectStyles() in the tree uses.
_OPEN = re.compile(r"textContent\s*=\s*`")


def _sources() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for root, pat in ((_ENGINE / "frontend", "**/*.js"), (_ENGINE / "widgets", "*/widget.js")):
        out.extend(p for p in root.glob(pat) if "vendor" not in p.parts and "node_modules" not in p.parts)
    return sorted(out)


def test_no_injected_style_block_contains_a_backtick():
    offenders: list[str] = []
    for path in _sources():
        src = path.read_text(encoding="utf-8")
        for m in _OPEN.finditer(src):
            start = m.end()
            end = src.find("`", start)
            if end == -1:                     # an unterminated literal is a syntax error the parser owns
                continue
            # The literal ends at the FIRST backtick. If what follows is not the close of the statement, the
            # backtick we just found is INSIDE the intended stylesheet — which is the defect.
            tail = src[end:end + 60].lstrip("`").lstrip()
            if not tail.startswith(";"):
                line = src.count("\n", 0, end) + 1
                offenders.append(f"{path.relative_to(_ENGINE)}:{line}: {src[end:end + 70]!r}")
    assert not offenders, (
        "a backtick inside an injected <style> template literal closes it early and kills the module at "
        "import time, with no syntax error anywhere:\n  " + "\n  ".join(offenders))


def test_the_scan_would_actually_catch_one():
    """The counterweight: a guard that cannot fail is not a guard.

    Measured against a synthetic source rather than by trusting the regex — the same shape the real defect
    had (a backtick inside a CSS comment, well before the statement's own close).
    """
    bad = 's.textContent=`\n  /* the `.hb-scroll` element */\n  .x{color:red}\n`; document.head.appendChild(s);'
    m = _OPEN.search(bad)
    assert m
    end = bad.find("`", m.end())
    assert end != -1 and not bad[end:end + 60].lstrip("`").lstrip().startswith(";"), \
        "the scan must read this as a stray backtick"

    good = 's.textContent=`\n  .x{color:red}\n`; document.head.appendChild(s);'
    m = _OPEN.search(good)
    end = good.find("`", m.end())
    assert good[end:end + 60].lstrip("`").lstrip().startswith(";"), \
        "and it must read a clean block as clean"
