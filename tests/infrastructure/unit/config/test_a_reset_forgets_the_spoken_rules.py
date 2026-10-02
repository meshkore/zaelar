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


def test_a_factory_reset_also_forgets_the_circuit_override():
    """V2-778 F3-29 — `<workspace>/config/circuit.json` overrides genesis's bound on a worker's retries, per
    install, like `library.json`. A factory reset returned everything else to genesis and left this one."""
    i = SCRIPT.index("FACTORY_PATHS=(")
    block = SCRIPT[i:SCRIPT.index("\n)", i)]          # the array's closing line, not a «)» inside a comment
    assert '"config/circuit.json"' in block


def test_a_factory_reset_also_forgets_the_errand_playbooks_but_never_a_connectors_credentials():
    """V2-778 F3-29, the operator's decision (2026-10-02): a factory reset leaves the agent as just installed — his
    per-kind errand preferences (`config/playbooks.json`) included — and never takes the credentials a connector
    needs: those die only with the explicit `--wipe-credentials`."""
    i = SCRIPT.index("FACTORY_PATHS=(")
    factory = SCRIPT[i:SCRIPT.index(")", SCRIPT.index("\n)", i))]
    assert '"config/playbooks.json"' in factory
    for cred in ("config/connectors.json", "connectors/whatsapp/_session", "connectors/telegram/_session",
                 ".meshkore/credentials"):
        assert f'"{cred}"' not in factory, f"a factory reset must not take {cred}"
