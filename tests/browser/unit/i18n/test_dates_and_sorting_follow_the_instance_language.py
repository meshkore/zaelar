#
# Dates, numbers, collation and the speech-recognition locale follow the INSTANCE language (`ctx.lang` in a
# widget, `store.lang()` in the app), never the browser locale and never a hardcoded Spanish default. English
# is the floor when the language is unknown. Static guard over the files that used to break the rule.
#
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]

SCOPED = [
    "frontend/app/components/ChatWall.js",
    "frontend/app/components/ConfigPanel.js",
    "frontend/app/services/wakeword.js",
    "frontend/app/services/session-lk.js",
    "widgets/mensajeria/widget.js",
    "widgets/archivos/widget.js",
    "widgets/contactos/widget.js",
    "widgets/markets/widget.js",
    "widgets/agenda/widget.js",
    "widgets/youtube/widget.js",
]

# Each pattern is a locale that is NOT the instance language.
FORBIDDEN = {
    "browser locale via toLocale*String([] | undefined)": re.compile(r"\.toLocale\w*String\(\s*(\[\]|undefined)\s*[,)]"),
    "browser locale via toLocale*String()": re.compile(r"\.toLocale\w*String\(\s*\)"),
    "browser locale via Intl.*(undefined | [])": re.compile(r"\bIntl\.\w+\(\s*(\[\]|undefined)\s*[,)]"),
    "browser locale via `|| undefined`": re.compile(r"\blang\s*\|\|\s*undefined\b"),
    "navigator.language": re.compile(r"\bnavigator\.languages?\b"),
    "Spanish default via || / ??": re.compile(r"(\|\||\?\?)\s*[\"']es(-ES)?[\"']"),
    "Spanish default as a ternary fallback": re.compile(r"\)\s*:\s*[\"']es-ES[\"']\s*[,;)]"),
    "Spanish default for _LANG": re.compile(r"\b_LANG\s*=\s*[\"']es(-ES)?[\"']"),
    "Spanish collation": re.compile(r"localeCompare\([^;]*,\s*[\"']es(-ES)?[\"']\s*\)"),
}


@pytest.mark.parametrize("rel", SCOPED)
def test_no_locale_other_than_the_instance_language(rel):
    src = (ENGINE / rel).read_text(encoding="utf-8")
    hits = []
    for n, line in enumerate(src.splitlines(), 1):
        code = line.split("//", 1)[0] if not line.lstrip().startswith("//") else ""
        for why, rx in FORBIDDEN.items():
            if rx.search(code):
                hits.append(f"{rel}:{n}: {why}: {line.strip()[:120]}")
    assert not hits, "locale must come from the instance language:\n" + "\n".join(hits)


def test_the_guard_catches_what_it_names():
    bad = [
        'd.toLocaleTimeString([], {hour:"2-digit"})', "d.toLocaleString()", "d.toLocaleDateString(undefined, o)",
        "new Intl.NumberFormat(undefined, o)", "x(lang || undefined)", "navigator.language",
        'r.lang = f() || "es-ES";', 'g(() => c() ? h(c()) : "es-ES",', 'let _LANG = "es";', 'a.localeCompare(b, "es")',
    ]
    for s in bad:
        assert any(rx.search(s) for rx in FORBIDDEN.values()), s
    good = ['d.toLocaleString(_LANG)', 'new Intl.DateTimeFormat(lang || "en", o)', 'l === "es" ? "es-ES" : l']
    for s in good:
        assert not any(rx.search(s) for rx in FORBIDDEN.values()), s


def test_apply_lang_sets_the_html_lang():
    src = (ENGINE / "frontend/app/core/i18n.js").read_text(encoding="utf-8")
    body = src[src.index("export async function applyLang"):]
    body = body[: body.index("\n}\n")]
    assert re.search(r"document\.documentElement\.lang\s*=\s*final\b", body), "applyLang must set <html lang>"
    for shell in ("frontend/index.html", "frontend/mobile/index.html"):
        assert '<html lang="en"' in (ENGINE / shell).read_text(encoding="utf-8"), shell
