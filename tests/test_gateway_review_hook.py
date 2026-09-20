import pathlib

import pytest

from gateway.gateway import build_gateway

SESSION = "s_hook"
AGENT = "agent-maint-copilot"


@pytest.fixture
def gw(tmp_path):
    return build_gateway(
        config_dir=pathlib.Path(__file__).parent.parent / "config",
        ledger_path=tmp_path / "ledger.jsonl",
        server_key=b"test-key",
    )


def _ingest_bulletin(gw):
    return gw.call(
        tool="search_supplier_docs",
        args={"query": "line 3 bulletin", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )


def test_on_review_hook_fires_with_expected_metadata(gw):
    calls = []
    gw.on_review = lambda **kwargs: calls.append(kwargs)

    _ingest_bulletin(gw)
    result = gw.call(
        tool="post_supplier_ticket",
        args={
            "subject": "Warranty",
            "body": "Affected units manufactured before 2025-11 may report elevated vibration readings after 4000 operating hours.",
            "endpoint": "partner-portal.example.net/intake",
            "session_id": SESSION,
            "agent_id": AGENT,
        },
        session_id=SESSION,
        agent_id=AGENT,
    )

    assert result["resultType"] == "input_required"
    assert len(calls) == 1
    call = calls[0]
    assert call["tool"] == "post_supplier_ticket"
    assert call["session_id"] == SESSION
    assert call["agent_id"] == AGENT
    assert any(rule_id == "nis2-art21-untrusted-egress" for rule_id, _ in call["fired_rules"])


def test_on_review_hook_not_called_on_allow(gw):
    calls = []
    gw.on_review = lambda **kwargs: calls.append(kwargs)

    gw.call(
        tool="read_maintenance_log",
        args={"line": "line-3", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )

    assert calls == []


def test_on_review_hook_failure_does_not_block_the_call(gw):
    def boom(**kwargs):
        raise RuntimeError("teams webhook is down")

    gw.on_review = boom

    _ingest_bulletin(gw)
    result = gw.call(
        tool="post_supplier_ticket",
        args={
            "subject": "Warranty",
            "body": "Affected units manufactured before 2025-11 may report elevated vibration readings after 4000 operating hours.",
            "endpoint": "partner-portal.example.net/intake",
            "session_id": SESSION,
            "agent_id": AGENT,
        },
        session_id=SESSION,
        agent_id=AGENT,
    )

    assert result["resultType"] == "input_required"
