"""A factory reset forgets the rules the operator SAID (2026-09-29).

`config/style.json` and `config/consent.json` are written when a spoken rule is understood («no me confirmes las
órdenes», «pregúntame siempre antes») — they are memory, the learned layer over genesis. The reset wiped the
database and every widget state and kept them: measured on the demo prep of pass 58, a rule set by hand for pass
57 was still governing after «empieza de cero». Tested by TEXT, like its siblings: running the script in a test
would delete the operator's real memory.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
SCRIPT = (ROOT / "scripts/reset-memory.sh").read_text(encoding="utf-8")


def _memory_files_block() -> str:
    i = SCRIPT.index("MEMORY_FILES=(")
    return SCRIPT[i:SCRIPT.index(")", i)]


def test_the_spoken_rule_overrides_die_with_the_memory():
    block = _memory_files_block()
    assert '"config/style.json"' in block, "the style overrides a spoken rule wrote are memory"
    assert '"config/consent.json"' in block, "the consent overrides a spoken rule wrote are memory"


def test_credentials_and_settings_are_still_kept():
    block = _memory_files_block()
    for kept in ("config/connectors.json", "config/settings.json", "config/credentials"):
        assert kept not in block, f"{kept} is not memory — the reset must keep it"
