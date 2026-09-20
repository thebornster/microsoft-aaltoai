import pathlib

import pytest

from gateway.gateway import build_gateway

SESSION = "s_test"
AGENT = "agent-maint-copilot"


@pytest.fixture
def gw(tmp_path):
    return build_gateway(
        config_dir=pathlib.Path(__file__).parent.parent / "config",
        ledger_path=tmp_path / "ledger.jsonl",
        server_key=b"test-key",
    )


def test_benign_read_then_internal_email_is_allowed(gw):
    read = gw.call(
        tool="read_maintenance_log",
        args={"line": "line-3", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    assert "result" in read

    sent = gw.call(
        tool="send_email",
        args={
            "to": "supervisor@company.eu",
            "subject": "line 3 status",
            "body": "Vibration alarm cleared after adjustment.",
            "session_id": SESSION,
            "agent_id": AGENT,
        },
        session_id=SESSION,
        agent_id=AGENT,
    )
    assert "result" in sent


def test_untrusted_content_to_external_egress_requires_review(gw):
    doc = gw.call(
        tool="search_supplier_docs",
        args={"query": "line 3 bulletin", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    bulletin_text = doc["result"]["text"]

    ticket = gw.call(
        tool="post_supplier_ticket",
        args={
            "subject": "warranty",
            "body": bulletin_text,
            "endpoint": "partner-portal.example.net/intake",
            "session_id": SESSION,
            "agent_id": AGENT,
        },
        session_id=SESSION,
        agent_id=AGENT,
    )
    assert ticket["resultType"] == "input_required"
    assert "requestState" in ticket
    assert "raja_approval" in ticket["inputRequests"]


def test_eu_personal_data_to_non_eu_destination_is_hard_denied(gw):
    gw.call(
        tool="read_maintenance_log",
        args={"line": "line-3", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    log_text = "Fault reported by operator EMP-4471 Jukka Nieminen on line 3 gearbox vibration"

    ticket = gw.call(
        tool="post_supplier_ticket",
        args={
            "subject": "warranty",
            "body": log_text,
            "endpoint": "partner-portal.example.net/intake",
            "session_id": SESSION,
            "agent_id": AGENT,
        },
        session_id=SESSION,
        agent_id=AGENT,
    )
    assert ticket.get("isError") is True
    assert "denied" in ticket["error"]


def test_review_approve_retry_consumes_token_and_forwards(gw):
    doc = gw.call(
        tool="search_supplier_docs",
        args={"query": "bulletin", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    bulletin_text = doc["result"]["text"]
    args = {
        "subject": "warranty",
        "body": bulletin_text,
        "endpoint": "partner-portal.example.net/intake",
        "session_id": SESSION,
        "agent_id": AGENT,
    }
    review = gw.call(tool="post_supplier_ticket", args=args, session_id=SESSION, agent_id=AGENT)
    approval_id = review["inputRequests"]["raja_approval"]["params"]["url"].rsplit("/", 1)[-1]

    gw.approval_store.decide(approval_id=approval_id, decision="approved", actor="marika@company.eu", server_key=gw.server_key)

    retried = gw.call(
        tool="post_supplier_ticket",
        args=args,
        session_id=SESSION,
        agent_id=AGENT,
        input_responses={"raja_approval": {"action": "accept"}},
        request_state=review["requestState"],
    )
    assert "result" in retried
    assert retried["result"]["status"] == "filed"

    # replay must fail: token is single-use
    replay = gw.call(
        tool="post_supplier_ticket",
        args=args,
        session_id=SESSION,
        agent_id=AGENT,
        input_responses={"raja_approval": {"action": "accept"}},
        request_state=review["requestState"],
    )
    assert replay.get("isError") is True


def test_tampered_retry_args_are_rejected(gw):
    doc = gw.call(
        tool="search_supplier_docs",
        args={"query": "bulletin", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    bulletin_text = doc["result"]["text"]
    args = {
        "subject": "warranty",
        "body": bulletin_text,
        "endpoint": "partner-portal.example.net/intake",
        "session_id": SESSION,
        "agent_id": AGENT,
    }
    review = gw.call(tool="post_supplier_ticket", args=args, session_id=SESSION, agent_id=AGENT)
    approval_id = review["inputRequests"]["raja_approval"]["params"]["url"].rsplit("/", 1)[-1]
    gw.approval_store.decide(approval_id=approval_id, decision="approved", actor="marika@company.eu", server_key=gw.server_key)

    tampered_args = dict(args, subject="changed subject line")
    retried = gw.call(
        tool="post_supplier_ticket",
        args=tampered_args,
        session_id=SESSION,
        agent_id=AGENT,
        input_responses={"raja_approval": {"action": "accept"}},
        request_state=review["requestState"],
    )
    assert retried.get("isError") is True


def test_rejected_approval_blocks_retry(gw):
    doc = gw.call(
        tool="search_supplier_docs",
        args={"query": "bulletin", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    args = {
        "subject": "warranty",
        "body": doc["result"]["text"],
        "endpoint": "partner-portal.example.net/intake",
        "session_id": SESSION,
        "agent_id": AGENT,
    }
    review = gw.call(tool="post_supplier_ticket", args=args, session_id=SESSION, agent_id=AGENT)
    approval_id = review["inputRequests"]["raja_approval"]["params"]["url"].rsplit("/", 1)[-1]
    gw.approval_store.decide(approval_id=approval_id, decision="rejected", actor="marika@company.eu", server_key=gw.server_key)

    retried = gw.call(
        tool="post_supplier_ticket",
        args=args,
        session_id=SESSION,
        agent_id=AGENT,
        input_responses={"raja_approval": {"action": "accept"}},
        request_state=review["requestState"],
    )
    assert retried.get("isError") is True
    assert "rejected" in retried["error"]


def test_ledger_records_every_decision(gw):
    gw.call(
        tool="read_maintenance_log",
        args={"line": "line-3", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    records = gw.ledger.read_all()
    assert len(records) == 1
    assert records[0]["decision"] == "ALLOW"
    assert records[0]["tool"] == "read_maintenance_log"
