# CLAUDE.md is RULES; the diary is its own file — and neither may grow past being readable (2026-09-15).
#
# The operator, looking at a 394KB CLAUDE.md that was 80% decision log: «no sé por qué tienes que mencionar ahí
# números de tarea o cosas así. Se supone que ese archivo es para setear las reglas… dónde se encuentra el
# contexto, las listas de tareas y qué reglas necesitamos seguir para trabajar con este proyecto».
#
# He is right, and the size was the symptom of the category error. Three invariants now:
#   · CLAUDE.md stays SMALL — it is loaded whole by every agent on every session, so a decision entry there is
#     a tax on every turn of every session forever. The diary goes to `.meshkore/docs/decisions.md`;
#   · the DIARY has its own ceiling, paid by ARCHIVING byte-for-byte into `decisions-archive.md` and leaving a
#     one-line citation — never by deleting (that history is the only record of what was already tried);
#   · every initiative cited in the archive stays cited in the live log — `test_roadmap_closure` requires a
#     delivered initiative to be written down somewhere findable, and an archive pass that drops an index line
#     would silently break that for whoever delivers next.
#
# Run: .venv/bin/pytest tests/infrastructure/unit/test_claude_md_ratchet.py -q
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
CLAUDE = ENGINE / "CLAUDE.md"
DECISIONS = ENGINE / ".meshkore" / "docs" / "decisions.md"
ARCHIVE = ENGINE / ".meshkore" / "docs" / "decisions-archive.md"

# CLAUDE.md was 394_000 bytes on 2026-09-15 and came out at ~55_000 once the diary and the dense module
# inventory moved to their own docs. The headroom is for rules, not for entries.
CLAUDE_CEILING_BYTES = 80_000
# The live diary: compacted to 211KB on 2026-09-06, ~21KB/day ⇒ an archive pass every week or two.
DECISIONS_CEILING_BYTES = 400_000


def test_claude_md_stays_a_rules_file():
    size = CLAUDE.stat().st_size
    assert size <= CLAUDE_CEILING_BYTES, (
        f"CLAUDE.md is {size} bytes (> {CLAUDE_CEILING_BYTES}). It is loaded WHOLE by every agent on every "
        "session: what belongs here is rules and pointers. A decision entry goes to "
        ".meshkore/docs/decisions.md; a dense inventory goes to its doc under .meshkore/docs/. Never raise "
        "this ceiling."
    )


def test_the_diary_is_not_in_the_rules_file():
    """The category error, made red. A `V2-xxx` may be CITED here (a rule can name where it came from); what
    may not live here is the log itself."""
    body = CLAUDE.read_text(encoding="utf-8")
    assert "decisions.md" in body, "CLAUDE.md no longer points readers at the diary"
    refs = len(re.findall(r"\bV2-\d{3}\b", body))
    assert refs <= 40, (
        f"CLAUDE.md cites {refs} initiatives — the decision log is creeping back in. An entry belongs in "
        ".meshkore/docs/decisions.md; here, a rule may name at most the initiative it came from."
    )


def test_the_diary_fits_under_its_own_ceiling():
    size = DECISIONS.stat().st_size
    assert size <= DECISIONS_CEILING_BYTES, (
        f".meshkore/docs/decisions.md is {size} bytes (> {DECISIONS_CEILING_BYTES}). Pay it with an archive "
        "pass — move the oldest full entries to decisions-archive.md and leave their one-line index entry, as "
        "the note at the top of that file describes. Never raise this ceiling and never delete an entry."
    )


def test_the_archive_and_the_policy_note_exist():
    assert ARCHIVE.is_file(), "the decisions archive vanished — the index points at nothing"
    assert DECISIONS.is_file(), "the decision log vanished — CLAUDE.md points at nothing"
    body = DECISIONS.read_text(encoding="utf-8")
    assert "decisions-archive.md" in body, "the live log no longer points readers at the archive"
    assert "### Archived decisions — index" in body, "the citation index section was removed"
    assert "## Moved on " in ARCHIVE.read_text(encoding="utf-8"), "archive passes must keep their dated markers"


def test_no_citation_is_lost_to_the_archive():
    """Everything cited in the archive is still cited in the live log (its index line carries the refs)."""
    ref = re.compile(r"\b(?:V2|INI)-\d{3}\b")
    live = set(ref.findall(DECISIONS.read_text(encoding="utf-8")))
    archived = set(ref.findall(ARCHIVE.read_text(encoding="utf-8")))
    lost = sorted(archived - live)
    assert not lost, (
        f"archived entries cite {lost} but the live log no longer does — an archive pass dropped index "
        "lines; restore them (the closure trinquete needs delivered initiatives cited somewhere findable)"
    )
