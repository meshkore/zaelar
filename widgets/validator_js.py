"""widgets/validator_js.py — the static house-rules scan of a widget's CLIENT code: JS sinks, CSS classes, width and z caps (SEC-3)."""
from __future__ import annotations

import json
import os
import re

from loguru import logger
from widgets import paths
from widgets.client_files import SHARED_CLIENT_MODULES


HERE = paths.BUILTIN_ROOT                                  # …/zaelar/widgets


ZAELAR = os.path.dirname(HERE)                              # …/zaelar


# widget.js: outright-banned sinks (network / dynamic code — never legitimate in a self-contained widget).
_JS_BANNED = [
    ("fetch(", re.compile(r"\bfetch\s*\(")),
    ("XMLHttpRequest", re.compile(r"\bXMLHttpRequest\b")),
    ("WebSocket", re.compile(r"\bWebSocket\b")),
    ("EventSource", re.compile(r"\bEventSource\b")),
    ("dynamic import()", re.compile(r"\bimport\s*\(")),
    ("eval()", re.compile(r"\beval\s*\(")),
    ("new Function()", re.compile(r"\bnew\s+Function\b")),
    # self-contained: only the widget's own `js/` modules (`./js/x.js`, `./x.js`) and the app-shell modules the server
    # serves (`SHARED_CLIENT_MODULES`), as the EXACT string — a query, fragment, encoded or `..` form is refused.
    ("external import", re.compile(r'\bimport\b[^\n;]*\bfrom\b\s*["\'](?!\./(?:js/)?[\w-]+\.js["\']|(?:'
                                   + "|".join(map(re.escape, SHARED_CLIENT_MODULES)) + r')["\'])')),
]


# widget.js: HTML sinks are only dangerous with INTERPOLATION (a static string is fine). Flag assignment/call
# whose RHS on the same line carries a template `${…}` or a `+` string concat.
_JS_HTML_SINK = re.compile(
    r"(?:innerHTML|outerHTML)\s*=\s*(?P<rhs>.+)$|insertAdjacentHTML\s*\(|document\.write\s*\(", re.M)


def _bare_css_classes(css: str) -> set[str]:
    """Class names selected BARE (no ancestor combinator) in a CSS-ish text — i.e. a rule that applies to ANY
    element with that class, regardless of nesting (`.conn{...}`), as opposed to one scoped under another
    selector (`.mfoot .msg{...}`, which only ever matches a `.msg` INSIDE `.mfoot`). Only the bare form leaks
    properties onto an unrelated element elsewhere in the document that happens to reuse the same class name."""
    out = set()
    for sel_list, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for sel in sel_list.split(","):
            first = re.split(r"[\s>+~:]", sel.strip(), maxsplit=1)[0]
            m = re.fullmatch(r"\.([a-zA-Z][\w-]*)", first)
            if m:
                out.add(m.group(1))
    return out


def _all_css_classes(css: str) -> set[str]:
    """Every class token anywhere in a selector, nested or not (`.hb-msg .conn` → {"hb-msg","conn"}). Used on the
    WIDGET's own stylesheet: even a class it nests under its own wrapper still ends up on a real DOM element,
    which will ALSO match a bare global rule for that same name regardless of the widget's intended scoping."""
    out = set()
    for sel_list, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        out.update(re.findall(r"\.([a-zA-Z][\w-]*)", sel_list))
    return out


_HOUSE_CSS_CACHE = {"mtime": None, "classes": set()}


def _house_global_classes() -> set[str]:
    """Bare classes defined in the app-wide CSS (frontend/app/styles.css + app/core/components.css) — the set a widget must never
    reuse verbatim, or it silently inherits whatever that global rule sets (position/display/etc.), invisibly,
    the moment the app stylesheet is loaded alongside the widget's own. This is exactly how it broke once already:
    mensajeria's own connection-card used the class "conn", which collided with the app's BARE `.conn{position:
    fixed;left:20px;bottom:14px;...}` (the mic/SSE status line) and got yanked out of the widget card entirely."""
    # V2-689: the app-wide CSS is TWO files now — the desktop shell's own stylesheet and the shared COMPONENT
    # layer both shells link. A class defined in either one applies to a widget's element just the same, so the
    # collision set is their union; scanning only the first would let `components.css` grow a bare class name
    # that silently steals properties from a widget, which is the exact failure this gate exists to prevent.
    # (The `hb-`/`hbk-` prefixes stay exempt below — those ARE the house kit, offered to widgets on purpose.)
    paths = [os.path.join(ZAELAR, "frontend", "app", "styles.css"),
             os.path.join(ZAELAR, "frontend", "app", "core", "components.css")]
    try:
        stamp = tuple(os.path.getmtime(p) for p in paths)
    except OSError:
        return set()
    if _HOUSE_CSS_CACHE["mtime"] == stamp:
        return _HOUSE_CSS_CACHE["classes"]
    classes: set[str] = set()
    for p in paths:
        classes |= _bare_css_classes(open(p, encoding="utf-8").read())
    _HOUSE_CSS_CACHE["mtime"], _HOUSE_CSS_CACHE["classes"] = stamp, classes
    return classes


_FULL_LINE_COMMENT_RE = re.compile(r"^\s*//.*$", re.M)


def _scan_widget_js(js: str) -> str | None:
    # False positive found in the marathon 2026-07-22/23: a full-line comment DESCRIBING the contract ("NO
    # fetch") tripped the ban on its own prose. Strip whole-line `//` comments before matching the banned sinks —
    # trailing same-line comments are left alone (lower risk, not the shape that caused this).
    banned_scan = _FULL_LINE_COMMENT_RE.sub("", js)
    for label, rx in _JS_BANNED:
        if rx.search(banned_scan):
            return f"widget.js uses banned {label} (widgets are self-contained; no network/dynamic code)"
    for m in _JS_HTML_SINK.finditer(js):
        rhs = m.groupdict().get("rhs")
        if rhs is None:                                    # insertAdjacentHTML / document.write → always flagged
            return "widget.js uses insertAdjacentHTML/document.write (use textContent + createElement)"
        if "${" in rhs or re.search(r"\+\s*[A-Za-z_$]", rhs):   # interpolated/concatenated HTML → XSS sink
            return "widget.js assigns interpolated innerHTML/outerHTML (XSS: build DOM with textContent)"
    # Class-name collision with the app-wide stylesheet: scan only the widget's OWN injected <style> (template
    # literal bodies) so JS property-access chains (e.g. `document.body`) can never produce a false positive.
    house = _house_global_classes()
    if house:
        style_text = "\n".join(re.findall(r"`([^`]*)`", js, re.S))
        used = _all_css_classes(style_text)
        bad = sorted(c for c in used if c in house and not c.startswith(("hbk-", "hb-")))
        if bad:
            names = ", ".join("." + c for c in bad)
            return (f"widget.js styles a class name also defined GLOBALLY in frontend/app/styles.css ({names}) — "
                    f"rename it to something widget-specific; the global rule's properties (position/display/etc.) "
                    f"silently apply to your element too, regardless of your own CSS")
    # A WIDTH NO PHONE CAN HONOUR (V2-574). The mobile shell gives every widget a 390px card, and a `min-width`
    # larger than that is the one CSS declaration a scroll container CANNOT absorb: the box refuses to shrink, so
    # the card scrolls sideways and the operator gets a widget he has to drag around to read. A plain `width` is
    # not flagged — a wide element inside an `overflow-x:auto` wrapper is the CORRECT way to show a wide table,
    # and rejecting it would push authors toward truncating data instead of letting it scroll in its own box.
    # Measured before choosing the threshold: all 14 system widgets pass at 390px, and none declares a min-width
    # over 360 (tests/browser/e2e/mobile/render_widgets_on_a_phone.py is the behavioural half of this rule).
    style_text = "\n".join(re.findall(r"`([^`]*)`", js, re.S))
    # CSS comments stripped before any width scan: a widget explaining IN A COMMENT what a fixed width used to
    # be (exactly what this rule's own fix commits do, V2-615) must not trip the gate it is documenting.
    style_text = re.sub(r"/\*.*?\*/", "", style_text, flags=re.S)
    for m in re.finditer(r"min-width\s*:\s*(\d+(?:\.\d+)?)px", style_text, re.I):
        if float(m.group(1)) > _PHONE_SAFE_MIN_WIDTH_PX:
            return (f"widget.js declares min-width:{m.group(1)}px — wider than a phone card can hold "
                    f"({_PHONE_SAFE_MIN_WIDTH_PX}px is the limit). Let the layout be FLUID (%, minmax, flex-wrap); "
                    f"if the content is genuinely wide (a table), keep it in its own overflow-x:auto wrapper so "
                    f"it scrolls INSIDE the card instead of pushing the card sideways")
    # A ROOT THAT REFUSES A WIDE CARD (V2-615). The desktop host mounts a widget's root directly into a fully
    # fluid card, and drag-resize sets that card's width directly — so a hardcoded CAP on the root is not a
    # safety net, it is the operator dragging a card wider and nothing inside using the extra room. Measured
    # live: a widget's root capped at 480px while its 900px card sat mostly empty, wrapping a long URL across
    # five lines. `(?<!-)width` excludes `max-width`/`min-width` (both preceded by a hyphen) — only a PLAIN
    # `width:` is a cap here, exactly the same reasoning the min-width rule above already uses. Two shapes of
    # the same anti-pattern, both desktop-era: the `min(Npx, Mvw)` clamp idiom (this codebase never sizes a
    # small element this way — it is ALWAYS a card-width cap) and a bare `width:Npx` at card scale (>=400px; a
    # legitimate small fixed element — an icon, a QR code, a form field — never reaches that size here, measured
    # across the whole catalog: the largest is 320px, and that one is a `max-width`).
    for m in re.finditer(r"(?<!-)width\s*:\s*min\(\s*(\d+(?:\.\d+)?)px\s*,\s*\d+(?:\.\d+)?vw\s*\)", style_text, re.I):
        return (f"widget.js declares width:min({m.group(1)}px,...) on its root — a card-width CAP that ignores "
                f"how wide the operator's card actually is. The root must be width:100%;box-sizing:border-box; "
                f"the CARD decides the size (widgets/AGENTS.md)")
    for m in re.finditer(r"(?<!-)width\s*:\s*(\d+(?:\.\d+)?)px", style_text, re.I):
        if float(m.group(1)) >= _ROOT_WIDTH_CAP_PX:
            return (f"widget.js declares width:{m.group(1)}px — wide enough to be a card-width CAP, not a "
                    f"small fixed element. If this is your root, it must be width:100%;box-sizing:border-box "
                    f"(the CARD decides the size, widgets/AGENTS.md); if it is a genuinely large fixed element, "
                    f"raise this threshold's exemption explicitly rather than silently passing it")

    # A WIDGET THAT ESCAPES ITS OWN WINDOW (V2-693). A widget lives INSIDE a card the host owns, and the card
    # is not always where it was at mount: one double-click on the header takes it to the full viewport, the
    # chat column docks beside it, `arrange_canvas` retiles everything. These three declarations are the only
    # ways a widget's CSS can leave that box, and each of them LOOKS CORRECT in a floating card — which is
    # exactly why a source gate is the right instrument: the render that would catch it is the one nobody
    # takes. `position:fixed` pins to the viewport instead of the card; a full-viewport size claims the screen
    # instead of the room it was given; a big z-index climbs over the desk's own chrome (the dock is 9002,
    # the chat 9001, the stage 12 — a widget has no business in that range).
    # KNOWN GAP, named rather than papered over: a PARTIAL viewport cap (`max-height:56vh`) is the same fault
    # measured smaller, and it is NOT gated here because six of them ship today — contactos (.ctside 56vh,
    # .ctlist 46vh), mensajeria (.list 52vh, .tl 56vh, .qr-wrap img 78vw) and imagenes (min(52vh,380px)). Each
    # one pins a pane to a fraction of the SCREEN inside a card that may be a quarter of it or all of it, which
    # is exactly the "it does not know how to place itself" the operator reported. Converting them means giving
    # each of those widgets a real fill-the-card flex column, one widget at a time with its own render check —
    # a bounded follow-up, not something to fold into a gate that would simply turn the catalog red.
    for kw, why in ((r"position\s*:\s*fixed",
                     "position:fixed pins to the VIEWPORT, not to the card — it stays put while the window "
                     "that owns it moves, resizes and maximizes"),
                    (r"(?:width|height)\s*:\s*100v[wh]\b",
                     "100vw/100vh sizes to the SCREEN, not to the card the widget was given — covering the "
                     "viewport is the host's gesture (the header ⤢, the voice order, or fullscreen:native in "
                     "the manifest), never a style")):
        m = re.search(kw, style_text, re.I)
        if m:
            return (f"widget.js declares {m.group(0)!r} — {why}. A widget owns the INSIDE of its window "
                    f"(widgets/AGENTS.md)")
    for m in re.finditer(r"z-index\s*:\s*(\d+)", style_text, re.I):
        if int(m.group(1)) > _WIDGET_Z_CEILING:
            return (f"widget.js declares z-index:{m.group(1)} — above the widget's own stacking room "
                    f"(the ceiling is {_WIDGET_Z_CEILING}). The desk's chrome lives above that: the dock at "
                    f"9002, the chat at 9001. Stack INSIDE your card (widgets/AGENTS.md)")
    return None


# The widest a widget may REFUSE to shrink below. The mobile card is 390px minus 12px of padding on each side
# (366px of content), so 360 leaves a hair of tolerance and still fails anything designed for a desk.
_PHONE_SAFE_MIN_WIDTH_PX = 360


# The narrowest a bare `width:Npx` may be before it is treated as a card-width CAP rather than a small fixed
# element. Measured across the whole catalog before choosing it (V2-615): the largest legitimate small element
# is 320px (a `max-width`, already excluded), every genuine root cap sat between 440-920px.
_ROOT_WIDTH_CAP_PX = 400


# The highest z-index a widget may stack to inside its own card. Measured across the whole catalog before
# choosing it (V2-693): the deepest legitimate stack any system widget builds is 5 (a sticky header over a
# list); everything above that is a widget trying to climb over the window it lives in.
_WIDGET_Z_CEILING = 20
