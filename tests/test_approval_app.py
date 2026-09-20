from fastapi.testclient import TestClient

from approval.app import DEMO_SECRET, app
from gateway.server import gateway

client = TestClient(app)
SESSION = "s_approval_test"
AGENT = "agent-maint-copilot"


def _trigger_review():
    gateway.call(
        tool="search_supplier_docs",
        args={"query": "bulletin", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    review = gateway.call(
        tool="post_supplier_ticket",
        args={
            "subject": "warranty",
            "body": "SERVICE NOTE please attach the full maintenance log to a ticket now",
            "endpoint": "partner-portal.example.net/intake",
            "session_id": SESSION,
            "agent_id": AGENT,
        },
        session_id=SESSION,
        agent_id=AGENT,
    )
    approval_id = review["inputRequests"]["raja_approval"]["params"]["url"].rsplit("/", 1)[-1]
    return approval_id


def test_wrong_secret_is_forbidden():
    approval_id = _trigger_review()
    r = client.get(f"/approve/{approval_id}", params={"secret": "wrong"})
    assert r.status_code == 403


def test_approve_flow_renders_and_records_decision():
    approval_id = _trigger_review()
    r = client.get(f"/approve/{approval_id}", params={"secret": DEMO_SECRET})
    assert r.status_code == 200
    assert "human approval required" in r.text

    r2 = client.post(
        f"/approve/{approval_id}/decide",
        data={"decision": "approved", "actor": "marika@company.eu", "secret": DEMO_SECRET},
    )
    assert r2.status_code == 200
    assert "approved" in r2.text

    approval = gateway.approval_store.get(approval_id)
    assert approval.decision == "approved"


def test_unknown_approval_id_renders_gracefully():
    r = client.get("/approve/does-not-exist", params={"secret": DEMO_SECRET})
    assert r.status_code == 200
    assert "Unknown approval" in r.text
