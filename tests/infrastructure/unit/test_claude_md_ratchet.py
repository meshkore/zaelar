# engine/CLAUDE.md stays loadable — compaction by ARCHIVE, never by deletion (V2-601 T-18, audit 2026-09-05).
#
# At 869KB (~210k tokens) no agent could load the decision log whole, so every reader worked from a
# nondeterministic slice of it. The 2026-09-06 pass moved older entries byte-for-byte to
# `.meshkore/docs/decisions-archive.md`, leaving a one-line citation per entry. Two invariants keep that
# honest:
#   · a size ceiling on CLAUDE.md — when it trips, pay it with an archive pass (the policy note at the top
#     of «Decisiones clave» is the procedure), never by deleting content or raising the ceiling;
#   · every initiative cited in the archive stays cited in CLAUDE.md — the closure trinquete
#     (test_roadmap_closure) requires delivered initiatives to be cited THERE, so an archive pass that
#     drops an index line would silently break rule 4 for whoever delivers next.
#
# Run: .venv/bin/pytest tests/infrastructure/unit/test_claude_md_ratchet.py -q
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
CLAUDE = ENGINE / "CLAUDE.md"
ARCHIVE = ENGINE / ".meshkore" / "docs" / "decisions-archive.md"

CEILING_BYTES = 400_000  # ~100k tokens; compacted to 211KB on 2026-09-06, ~21KB/day growth ⇒ trips in ~9 days


def test_claude_md_fits_under_the_ceiling():
    size = CLAUDE.stat().st_size
    assert size <= CEILING_BYTES, (
        f"CLAUDE.md is {size} bytes (> {CEILING_BYTES}). Pay it with an archive pass — move the oldest "
        "full entries of «Decisiones clave» to .meshkore/docs/decisions-archive.md and leave their "
        "one-line index entry, as the policy note atop that section describes. Never raise this ceiling."
    )


def test_the_archive_and_the_policy_note_exist():
    assert ARCHIVE.is_file(), "the decisions archive vanished — CLAUDE.md's index points at nothing"
    body = CLAUDE.read_text(encoding="utf-8")
    assert "decisions-archive.md" in body, "CLAUDE.md no longer points readers at the archive"
    assert "### Archived decisions — index" in body, "the citation index section was removed"
    assert "## Moved on " in ARCHIVE.read_text(encoding="utf-8"), "archive passes must keep their dated markers"


def test_no_citation_is_lost_to_the_archive():
    """Everything cited in the archive is still cited in CLAUDE.md (its index line carries the refs)."""
    ref = re.compile(r"\b(?:V2|INI)-\d{3}\b")
    in_claude = set(ref.findall(CLAUDE.read_text(encoding="utf-8")))
    in_archive = set(ref.findall(ARCHIVE.read_text(encoding="utf-8")))
    lost = sorted(in_archive - in_claude)
    assert not lost, (
        f"archived entries cite {lost} but CLAUDE.md no longer does — an archive pass dropped index "
        "lines; restore them (the closure trinquete needs delivered initiatives cited in CLAUDE.md)"
    )
