"""Gate 6: structured decision metadata on gateway.call()'s response
(`meta.decision`/`rules_fired`/`regulations`/`sources`/`matched_entities`/
`shingle_overlap`), additive alongside the existing result/error shape, so a
consumer never has to parse the human-readable `error` string to know what
fired.
"""
import pathlib

import pytest

from gateway.gateway import build_gateway

SESSION = "s_meta_test"
AGENT = "agent-meta-test"


@pytest.fixture
def gw(tmp_path):
    return build_gateway(
        config_dir=pathlib.Path(__file__).parent.parent / "config",
        ledger_path=tmp_path / "ledger.jsonl",
        server_key=b"test-key",
    )


def test_allow_meta_is_structured(gw):
    result = gw.call(
        tool="read_maintenance_log",
        args={"line": "line-3", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    meta = result["meta"]
    assert meta["decision"] == "ALLOW"
    assert meta["rules_fired"] == []
    assert meta["regulations"] == []
    assert meta["sources"]
    assert meta["matched_entities"] == []
    assert meta["shingle_overlap"] == 0


def test_deny_meta_names_the_fired_rule_and_regulation_without_parsing_error_text(gw):
    gw.call(
        tool="read_maintenance_log",
        args={"line": "line-3", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    ticket = gw.call(
        tool="post_supplier_ticket",
        args={
            "subject": "warranty",
            "body": "Fault reported by operator EMP-4471 Jukka Nieminen on line 3 gearbox vibration",
            "endpoint": "partner-portal.example.net/intake",
            "session_id": SESSION,
            "agent_id": AGENT,
        },
        session_id=SESSION,
        agent_id=AGENT,
    )
    meta = ticket["meta"]
    assert meta["decision"] == "DENY"
    assert "gdpr-art44-transfer" in meta["rules_fired"]
    assert any("GDPR Art. 44" in r for r in meta["regulations"])
    assert meta["sources"]
    assert "EMP-4471" in meta["matched_entities"]


def test_review_meta_reports_decision_and_rules(gw):
    gw.call(
        tool="search_supplier_docs",
        args={"query": "bulletin", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    ticket = gw.call(
        tool="post_supplier_ticket",
        args={
            "subject": "warranty",
            "body": "a paraphrased ticket with no fingerprint overlap at all",
            "endpoint": "partner-portal.example.net/intake",
            "session_id": SESSION,
            "agent_id": AGENT,
        },
        session_id=SESSION,
        agent_id=AGENT,
    )
    assert ticket["resultType"] == "input_required"
    meta = ticket["meta"]
    assert meta["decision"] == "REVIEW"
    assert meta["rules_fired"]


def test_missing_identity_meta_is_error(gw):
    result = gw.call(tool="read_maintenance_log", args={"line": "line-3"}, session_id="", agent_id="")
    assert result["meta"]["decision"] == "ERROR"
