#
# The widget-layer i18n ratchet (V2-613, widened to the whole catalog in V2-694).
#
# V2-613 shipped the seam (`ctx.t`/`ctx.lang`) and migrated two pilots; this file guarded those two and, by
# construction, could not see anyone else — it only recognised a FULL key (`ctx.t("widgets.timer.pause")`),
# while every widget migrated since asks its own local helper for a SHORT one (`tt("pause", …)`) and the
# helper prefixes `widgets.<id>.`. So with fourteen widgets migrated it would still have been green having
# measured one. A ratchet that cannot see the thing it ratchets is worse than no ratchet: it reports safety.
#
# Four properties, and each one is a failure this batch actually met:
#   1. every key a widget asks for exists in BOTH bundles — `t()` returns the key on a miss, and a key is
#      truthy, so a gap renders as `widgets.musica.playlist` on screen and fails nowhere;
#   2. no `t(...) || fallback`, which is dead code that reads like a working fallback (V2-613);
#   3. no Castilian text left OUTSIDE a `tt()` call — the whole point of the batch, and the only half a human
#      reliably forgets;
#   4. a widget that HAS the helper actually binds it in `render()`, or every string silently falls back.
#
from __future__ import annotations

import json
import re
from pathlib import Path

_ENGINE = Path(__file__).resolve().parents[4]
_WIDGETS_DIR = _ENGINE / "widgets"

# `ctx.t("widgets.x.y")` / `tr("widgets.x.y")` — the V2-613 pilots' shape, full keys.
_FULL_RE = re.compile(r"\b(?:ctx\.t|tr|t)\(\s*[\"']([a-zA-Z0-9_.]+)[\"']")
# `tt("short_key", …)` — the shape every widget migrated in V2-694 uses; the prefix comes from its own helper.
_SHORT_RE = re.compile(r"\b(?:tt|tr)\(\s*(?:ctx\s*,\s*)?[\"']([a-zA-Z0-9_]+)[\"']")
# Both helper shapes in the catalog: `_T("widgets.x." + key)` and documento's
# `const k = "widgets.documento." + key` (it takes `ctx` as its first argument).
_PREFIX_RE = re.compile(r"[=(]\s*[\"'](widgets\.[a-z0-9_-]+\.)[\"']\s*\+\s*key")
_FALLBACK_RE = re.compile(r"\b(?:ctx\.t|tr|t)\([^)]*\)\s*\|\|")

# A character that only Castilian UI text carries. Deliberately NARROW: a CSS class, an action name, a data key
# or an event name never holds one, so this cannot produce a false accusation — and it says plainly what it does
# NOT catch, which is an untranslated string that happens to be spelled with plain ASCII.
_CASTILIAN = re.compile(r"[áéíóúüñÁÉÍÓÚÜÑ¿¡«»]")
# …and at least two letters beside it: a bare «»/¿ is PUNCTUATION wrapped around an interpolated
# value, not a sentence, and accusing it would be the kind of false positive that gets a ratchet
# weakened instead of believed.
_HAS_WORDS = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2}")

# The LANGUAGE-INDEPENDENT half. The accent check above cannot see «Semillas» or «Buscar» — measured: disarming
# `tt("seeds", …)` back to a bare "Semillas" left it green, which is the exact regression this batch exists to
# stop. A literal ASSIGNED to a user-visible sink is untranslated whatever language it happens to be in, and
# that question needs no dictionary.
_SINK_RE = re.compile(r"\.(textContent|title|placeholder|alt|ariaLabel)\s*=\s*"
                      r"(\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*')")


def _widget_js_files() -> list[Path]:
    # `_user/` forks are the OPERATOR's own customization, made AFTER their language is already known — out of
    # scope by the same reasoning V2-613's initiative states for a one-off generated widget.
    return sorted(p for p in _WIDGETS_DIR.glob("*/widget.js") if "_user" not in p.parts)


def _bundle(code: str) -> dict:
    return json.loads((_ENGINE / "i18n" / "bundles" / f"{code}.json").read_text(encoding="utf-8"))


def _prefix_of(src: str) -> str:
    """`widgets.<id>.` for a widget whose helper prefixes it, else "" (not migrated to the short shape)."""
    m = _PREFIX_RE.search(src)
    return m.group(1) if m else ""


def _keys_of(src: str) -> set[str]:
    keys = {m.group(1) for m in _FULL_RE.finditer(src) if m.group(1).startswith("widgets.")}
    pre = _prefix_of(src)
    if pre:
        keys |= {pre + m.group(1) for m in _SHORT_RE.finditer(src)}
    return keys


# ── the scanner: which byte ranges are NOT ordinary code ─────────────────────────────────────────────────────
# Comments, and the TEXT of template literals — but NOT the `${…}` substitutions inside them, which are code and
# routinely hold labels (`${n === 1 ? "canción" : "canciones"}`). Missing that hid a whole class of strings when
# this batch was written, which is why the scanner is here and not a regex.
def _mask_spans(src: str) -> list[tuple[int, int, str]]:
    """(start, end, kind) with kind in {"comment", "template"} — the KIND matters: a comment is masked like a
    template but is not text the operator ever reads, and one holding a backtick would otherwise be reported as
    an untranslated sentence."""
    spans: list[tuple[int, int, str]] = []
    n = len(src)

    def quoted(i: int) -> int:
        q, j = src[i], i + 1
        while j < n and src[j] != q:
            if src[j] == "\n":
                break
            j += 2 if src[j] == "\\" else 1
        return j + 1

    _BEFORE_REGEX = set("(,=:[!&|?{};~+-*%^<>") | {"return", "typeof", "case", "in", "of", "new", "delete"}

    def starts_regex(i: int) -> bool:
        j = i - 1
        while j >= 0 and src[j] in " \t":
            j -= 1
        if j < 0 or src[j] == "\n":
            return True
        if src[j] in _BEFORE_REGEX:
            return True
        k = j
        while k >= 0 and (src[k].isalnum() or src[k] == "_"):
            k -= 1
        return src[k + 1:j + 1] in _BEFORE_REGEX

    def regex(i: int) -> int:
        j, cls = i + 1, False
        while j < n:
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "\n":
                return i + 1                      # not a regex after all; treat the slash as ordinary
            if c == "[":
                cls = True
            elif c == "]":
                cls = False
            elif c == "/" and not cls:
                return j + 1
            j += 1
        return n

    def comment(i: int) -> int:
        if src[i + 1] == "*":
            k = src.find("*/", i + 2)
            k = n if k < 0 else k + 2
        else:
            k = src.find("\n", i)
            k = n if k < 0 else k
        spans.append((i, k, "comment"))
        return k

    def expr(i: int) -> int:
        depth, j = 1, i
        while j < n:
            c = src[j]
            if c == "`":
                j = template(j)
                continue
            if c in "\"'":
                j = quoted(j)
                continue
            if c == "/" and j + 1 < n and src[j + 1] in "/*":
                j = comment(j)
                continue
            if c == "/" and starts_regex(j):
                j = regex(j)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return n

    def template(i: int) -> int:
        j, start = i + 1, i
        while j < n:
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                spans.append((start, j + 1, "template"))
                return j + 1
            if c == "$" and j + 1 < n and src[j + 1] == "{":
                spans.append((start, j + 2, "template"))
                j = expr(j + 2)
                start = j
                continue
            j += 1
        spans.append((start, n, "template"))
        return n

    i = 0
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] in "/*":
            i = comment(i)
        elif c == "/" and starts_regex(i):
            i = regex(i)
        elif c == "`":
            i = template(i)
        elif c in "\"'":
            i = quoted(i)
        else:
            i += 1
    return spans


def _tt_call_spans(src: str) -> list[tuple[int, int]]:
    """The byte range of every `tt(...)` call, parens balanced — so a fallback built by CONCATENATION or as a
    template literal counts as inside the call, which a backwards regex cannot tell."""
    out = []
    for m in re.finditer(r"\b(?:tt|tr)\(", src):
        depth, j, n = 0, m.end() - 1, len(src)
        while j < n:
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    out.append((m.start(), j + 1))
                    break
            j += 1
    return out


def _inside(pos: int, spans) -> bool:
    return any(a <= pos < b for a, b, *_ in spans)


# ── 1 · every key exists in both bundles ─────────────────────────────────────────────────────────────────────

def test_every_widget_translation_key_exists_in_both_bundles():
    en, es = _bundle("en"), _bundle("es")
    missing = {}
    for f in _widget_js_files():
        keys = _keys_of(f.read_text(encoding="utf-8"))
        gone = sorted(k for k in keys if k not in en or k not in es)
        if gone:
            missing[str(f.relative_to(_ENGINE))] = gone
    assert not missing, f"widget i18n keys missing from a bundle: {missing}"


def test_no_dead_or_fallback_pattern_after_a_translation_call():
    """`t()`/`ctx.t()` never returns falsy (worst case: the literal key), so `t(...) || "fallback"` is dead code
    that reads like a working fallback and never runs — the exact trap the mobile shell's own test already
    guards against (found there 2026-08-29)."""
    offenders = [str(f.relative_to(_ENGINE)) for f in _widget_js_files()
                 if _FALLBACK_RE.search(f.read_text(encoding="utf-8"))]
    assert not offenders, f"dead `t(...) || fallback` pattern in: {offenders}"


# ── 2 · nothing Castilian is left outside a translation call ─────────────────────────────────────────────────

def test_no_widget_ships_text_the_operators_language_cannot_change():
    """The operator's rule, made mechanical: «todos los nombres, etiquetas, títulos, botones… todo es
    configurable cuando se inicializa un idioma».

    A rule every widget author has to REMEMBER is not a rule (V2-626), and this is the half a human forgets —
    a widget passes review, ships, and an English session reads one Castilian button. The check is narrow on
    purpose and its limits are written down rather than implied:
      · it sees a character only Castilian text carries (accents, ñ, ¿¡, guillemets), so a CSS class, an action
        name or an event name can never be accused;
      · the SINK half is language-independent and does catch those: anything assigned to `textContent`,
        `title`, `placeholder`, `alt` or `ariaLabel` is read by a person whatever language it is written in;
      · what neither half catches is a plain-ASCII label passed as an ARGUMENT to a widget's own element
        helper — those are caught by review and by the key test above, and the limit is written here rather
        than implied;
      · a literal INSIDE a `tt(...)` call is the sanctioned fallback and is exactly what this batch put there.
    """
    offenders: dict[str, list[str]] = {}
    for f in _widget_js_files():
        src = f.read_text(encoding="utf-8")
        masked, calls = _mask_spans(src), _tt_call_spans(src)
        bad = []
        for m in re.finditer(r"\"((?:[^\"\\\n]|\\.)*)\"|'((?:[^'\\\n]|\\.)*)'", src):
            if _inside(m.start(), masked) or _inside(m.start(), calls):
                continue
            text = m.group(1) if m.group(1) is not None else m.group(2)
            if _CASTILIAN.search(text) and _HAS_WORDS.search(text):
                bad.append(f"line {src.count(chr(10), 0, m.start()) + 1}: {text[:60]!r}")
        # a template literal's own TEXT can hold a whole sentence too, and it is inside no quote at all
        for a, b, kind in masked:
            if kind != "template":
                continue
            chunk = src[a:b]
            if not (_CASTILIAN.search(chunk) and _HAS_WORDS.search(chunk)):
                continue
            if _inside(a, calls) or "--hb-" in chunk or "px;" in chunk:   # a tt() fallback, or the CSS block
                continue
            bad.append(f"line {src.count(chr(10), 0, a) + 1}: template {chunk.strip()[:60]!r}")
        # …and the language-independent half: a bare literal handed to a sink the operator reads.
        for m in _SINK_RE.finditer(src):
            if _inside(m.start(), masked) or _inside(m.start(), calls):
                continue
            lit = m.group(2)[1:-1]
            if not _HAS_WORDS.search(lit):      # "", "✓", "×", "‹" — punctuation and marks, not text
                continue
            bad.append(f"line {src.count(chr(10), 0, m.start()) + 1}: .{m.group(1)} = {lit[:60]!r}")
        if bad:
            offenders[str(f.relative_to(_ENGINE))] = bad
    assert not offenders, (
        "a widget still paints Castilian text that no language can change — wrap it in "
        "`tt(\"key\", params, \"<the literal>\")` and add the row to i18n/bundles/en.json + es.json:\n"
        + "\n".join(f"  {k}\n    " + "\n    ".join(v) for k, v in offenders.items()))


# ── 3 · the helper is actually bound, and the scan is actually measuring something ───────────────────────────

def test_a_widget_with_the_helper_binds_it_in_render():
    """`tt()` falls back to the literal when `_T` is null — which is correct outside the engine and a SILENT
    total failure inside it. A widget that declares the helper and never binds it translates nothing, in every
    language, with no error anywhere."""
    unbound = []
    for f in _widget_js_files():
        src = f.read_text(encoding="utf-8")
        if not _prefix_of(src) or "_T" not in src:      # documento takes `ctx` per call: nothing to bind
            continue
        if not re.search(r"_T\s*=\s*\(\s*ctx\s*&&", src):
            unbound.append(str(f.relative_to(_ENGINE)))
    assert not unbound, f"these widgets declare the i18n helper and never bind it in render(): {unbound}"


def test_the_ratchet_actually_sees_the_whole_catalog():
    """A ratchet with nothing to ratchet proves nothing. Measured 2026-09-14: all 15 shipped widgets carry
    translated chrome, so a regex drift shows up as this COUNT collapsing rather than as a silently-green scan
    over an empty set."""
    migrated, no_strings = {}, []
    for f in _widget_js_files():
        src = f.read_text(encoding="utf-8")
        migrated[f.parent.name] = len(_keys_of(src))
        # `clock` is the honest exception and says so in its own header: it paints a date and a time and NOTHING
        # else, so `Intl.DateTimeFormat(ctx.lang, …)` gives it every language with no string of ours at all.
        # Delegating the SHAPE is a better answer than a bundle here, so having zero keys is correct — what
        # would not be correct is having neither keys nor `ctx.lang`.
        if not migrated[f.parent.name] and "ctx.lang" not in src:
            no_strings.append(f.parent.name)
    assert not no_strings, (
        "these widgets neither ask for a translated string nor delegate the locale shape to `ctx.lang` — "
        f"either they are untranslated or the scan stopped matching: {no_strings}")
    assert sum(migrated.values()) >= 500, f"expected the catalog's translated strings, found {sum(migrated.values())}"
