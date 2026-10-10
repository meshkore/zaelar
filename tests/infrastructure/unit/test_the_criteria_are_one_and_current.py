"""The standing criteria are ONE document, dated, tested, and without contradictions (V2-776 J, 2026-09-29).

The operator: «me gustaría empezar a simplificar criterios y que no haya contradicciones. En plan, en la V200
dijiste esto, en la V300 te contradijiste y dijiste esto, en la V421 dijiste lo otro. Necesitaríamos realmente
eliminar histórico y dejar solamente los últimos criterios de las cosas.» Measured that day: four sources said
what the engine must do (CLAUDE.md, decisions.md, the archive, principles.md), CLAUDE.md carried eight
"norma del operador" sections written at different dates, and one topic (the ack after a short order) had three
readable rules of which only the last was true. This ratchet keeps the fix from rotting.
"""
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
CRITERIA = ENGINE / ".meshkore/docs/criteria.md"
CLAUDE = ENGINE / "CLAUDE.md"
AGENTS = ENGINE / "AGENTS.md"
INSTRUCTIONS = ENGINE / ".meshkore/public/AGENT_INSTRUCTIONS.md"
DECISIONS = ENGINE / ".meshkore/docs/decisions.md"
TESTMAP = ENGINE / "tests/run_testmap.py"

#: CLAUDE.md came out at 688 lines once the eight rule sections and the workflow prose became pointers (from
#: 1,074; 265 of them are the MeshKore preamble the daemon renders). It only shrinks.
#: V2-778 (2026-10-02) — measured on the OPERATOR_CONTENT block only, the part this repo writes: the daemon re-rendered
#: its preamble (266 → 279 lines) and the whole-file count went red over text nobody here wrote or can trim. 422 is the
#: operator block today, unchanged by that render. It only shrinks.
CLAUDE_LINE_CEILING = 422


def _criteria_bullets() -> list[str]:
    body = CRITERIA.read_text(encoding="utf-8")
    body = body.split("## Contradicciones", 1)[0]
    # a bullet ends where the next bullet or the next heading starts
    return [b.split("\n#")[0].strip() for b in re.split(r"\n- \*\*CRIT-", body)[1:]]


def _node_ids() -> set[str]:
    return set(re.findall(r'"id": "(\d+\.\d+)"', TESTMAP.read_text(encoding="utf-8")))


def _operator_block(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    return s[s.index("<!-- OPERATOR_CONTENT_BEGIN"):s.index("<!-- OPERATOR_CONTENT_END -->")]


def test_every_criterion_is_dated_and_guarded_by_a_real_node():
    bullets = _criteria_bullets()
    assert len(bullets) >= 40, "the criteria file lost its lines"
    ids = _node_ids()
    for b in bullets:
        name = b.split("·", 1)[0].strip()
        assert re.search(r"—\s+since\s+\d{4}-\d{2}-\d{2}", b), f"CRIT-{name}: no date"
        m = re.search(r"nodes\s+([\d.,\s]+?)(?:·|$)", b, re.S)
        if not m:
            assert "⚠ sin test" in b, f"CRIT-{name}: neither a node nor the ⚠ sin test mark"
            continue
        for nid in [x.strip(" .\n") for x in m.group(1).split(",") if x.strip(" .\n")]:
            assert nid in ids, f"CRIT-{name} cites node {nid}, which is not in tests/run_testmap.py"


def test_no_topic_has_two_lines_and_the_contradictions_table_is_empty():
    bullets = _criteria_bullets()
    names = [b.split("·", 1)[0].strip() for b in bullets]
    assert len(names) == len(set(names)), f"a criterion id is repeated: {sorted(set(n for n in names if names.count(n) > 1))}"
    tail = CRITERIA.read_text(encoding="utf-8").split("## Contradicciones", 1)[1]
    rows = [ln for ln in tail.splitlines() if ln.startswith("|") and not ln.startswith("| topic") and not ln.startswith("|---")]
    assert rows == [], f"the contradictions table must be resolved, not kept: {rows}"


def test_the_debt_of_untested_criteria_only_shrinks():
    untested = sum("⚠ sin test" in b for b in _criteria_bullets())
    assert untested <= 5, f"{untested} criteria without a test — the debt was 5 on 2026-09-29 and only goes down"


def test_claude_md_is_rules_and_pointers_not_a_diary():
    body = CLAUDE.read_text(encoding="utf-8")
    dated = re.findall(r"^## .*\((?:norma|regla) del operador, \d{4}|^## .*\(operator rule, \d{4}", body, re.M)
    assert dated == [], f"a dated rule section grew back into CLAUDE.md — it belongs in criteria.md: {dated}"
    assert "criteria.md" in body, "CLAUDE.md no longer points at the standing criteria"
    i, j = body.find("<!-- OPERATOR_CONTENT_BEGIN"), body.find("<!-- OPERATOR_CONTENT_END")
    lines = body[i:j].count("\n") if 0 <= i < j else body.count("\n")
    assert lines <= CLAUDE_LINE_CEILING, (f"CLAUDE.md's operator block is {lines} lines (> {CLAUDE_LINE_CEILING}); "
                                          f"never raise this ceiling")


def test_the_three_rendered_files_carry_one_operator_block():
    """CLAUDE.md is rendered from AGENT_INSTRUCTIONS.md and mirrored in AGENTS.md; measured 2026-09-29 they had
    drifted 264 lines apart because agents hand-edited the render."""
    a, b, c = _operator_block(CLAUDE), _operator_block(AGENTS), _operator_block(INSTRUCTIONS)
    assert a == b == c, "the OPERATOR_CONTENT block differs between CLAUDE.md, AGENTS.md and AGENT_INSTRUCTIONS.md"


@pytest.mark.skipif(not DECISIONS.is_file(),
                    reason="decisions.md is local-only (gitignored since 2026-10-10); absent on a clone")
def test_the_diary_declares_itself_history():
    head = DECISIONS.read_text(encoding="utf-8")[:3000]
    assert "Este fichero es HISTORIA" in head and "criteria.md" in head


#: The reading test of V2-776 J: ten questions an agent asks before touching the engine, each answered by ONE
#: criterion. If the criterion vanishes, so does the answer.
READING_TEST = {
    "what do I say after a short order?": "V1",
    "when do I ask before acting?": "C1",
    "who decides which card an order goes to?": "K1",
    "may a backstop overrule a verdict?": "K2",
    "does a delete on the agenda ask?": "C3",
    "what happens to a send the verdict does not back?": "C5",
    "which prompts carry a spoken rule?": "M1",
    "is a provider error ours or theirs?": "R1",
    "how do I run the whole suite?": "W5",
    "is this sentence a rule or a mechanism?": "W1",
}


def test_the_reading_test_has_its_criteria():
    names = {b.split("·", 1)[0].strip() for b in _criteria_bullets()}
    missing = {q: c for q, c in READING_TEST.items() if c not in names}
    assert not missing, f"questions whose criterion is gone: {missing}"
