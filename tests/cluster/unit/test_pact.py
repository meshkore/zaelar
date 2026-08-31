#
# Tests for the agent-to-agent CONVERSATION PACT (V2-072). Run: .venv/bin/pytest tests/cluster/unit/test_pact.py -q
#
# The 3rd level of rules (hard-system > operator > negotiated PACT), ONLY in the agent-to-agent tunnel. Covers:
#   · the [[cluster.pact:NAME]]{json} tag that the mind emits when agreeing on rules
#   · sanitization to the CLOSED vocabulary (a pact never grants capabilities, it only restricts our conduct)
#   · hierarchy: the peer cannot override an OPERATOR pact
#   · REAL cadence (enforcement of zalo's complaint: do not bombard with messages)
#   · composition of the pact block for the prompt
#
import pytest

from connectors.meshkore import capsule
from voice.tag_protocol import strip_tags
from memory import db as memdb


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


# ── the tag ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_pact_tag_parsed():
    acts = []
    spoken, _ = strip_tags(
        'de acuerdo. [[cluster.pact:meshcore]]{"to":"zalo","cadence_s":20,"medium":"repo"}[[/cluster.pact]] seguimos',
        lambda a, e: acts.append((a, e)), final=True)
    assert ("cluster.pact", {"name": "meshcore",
            "data": {"to": "zalo", "cadence_s": 20, "medium": "repo"}}) in acts
    assert "[[cluster.pact" not in spoken            # the tag is removed from the spoken text


def test_pact_tag_in_turn_allowlist():
    from connectors.meshkore.bridge import ClusterBridge
    assert "cluster.pact" in ClusterBridge._CLUSTER_TURN_ALLOWED


# ── sanitization to the closed vocabulary (pure) ────────────────────────────────────────────────────────────────
def test_clean_pact_keeps_valid():
    out = capsule._clean_pact({"cadence_s": 30, "medium": "repo", "scope": "analysis", "note": "x"})
    assert out == {"cadence_s": 30, "medium": "repo", "scope": "analysis", "note": "x"}


def test_clean_pact_drops_garbage():
    out = capsule._clean_pact({"cadence_s": "no", "medium": "carrier-pigeon", "scope": "hack",
                               "run_command": "rm -rf /"})   # nothing outside the closed vocabulary gets in
    assert out == {}


def test_clean_pact_clamps_cadence():
    assert capsule._clean_pact({"cadence_s": 99999})["cadence_s"] == capsule.CADENCE_MAX_S


# ── pact_set + hierarchy (persistence) ──────────────────────────────────────────────────────────────────────────
def test_pact_set_merges(fresh_db):
    capsule.pact_set("meshcore", "zalo", {"cadence_s": 20}, by="peer")
    cap = capsule.pact_set("meshcore", "zalo", {"medium": "repo"}, by="peer")
    assert cap["pact"]["cadence_s"] == 20 and cap["pact"]["medium"] == "repo"


def test_operator_pact_not_clobbered_by_peer(fresh_db):
    capsule.pact_set("meshcore", "zalo", {"scope": "code"}, by="operator")
    capsule.pact_set("meshcore", "zalo", {"scope": "chat"}, by="peer")   # the peer CANNOT override the operator
    cap = capsule.load("meshcore", "zalo")
    assert cap["pact"]["scope"] == "code" and cap["pact"]["by"] == "operator"


# ── cadence (real enforcement) ───────────────────────────────────────────────────────────────────────────────────
def test_cadence_wait_none_without_pact():
    assert capsule.cadence_wait({"pact": {}}, now=1000) == 0.0


def test_cadence_wait_counts_down():
    cap = {"pact": {"cadence_s": 20}, "last_out_ts": 1000.0}
    assert capsule.cadence_wait(cap, now=1005) == 15.0     # 15s remain
    assert capsule.cadence_wait(cap, now=1025) == 0.0      # the window has already passed


# ── composition of the prompt block ────────────────────────────────────────────────────────────────────────────
def test_pact_compose_empty_without_pact():
    assert capsule.pact_compose({"pact": {}}) == ""


def test_pact_compose_renders_norms():
    block = capsule.pact_compose({"pact": {"cadence_s": 20, "medium": "repo", "scope": "analysis", "by": "peer"}})
    assert "PACTO" in block and "repositorio" in block.lower() and "análisis" in block.lower()


def test_pact_compose_marks_operator_authority():
    block = capsule.pact_compose({"pact": {"scope": "chat", "by": "operator"}})
    assert "operador" in block.lower()
