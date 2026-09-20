"""Regression test for the single-process mount: gateway.server.app must
expose both /mcp/call and /approve/* against the same RajaGateway instance.
Running them as two separate processes (two singletons) is the bug this
guards against — an approval created via /mcp/call must be resolvable via
/approve on the same app.
"""
from fastapi.testclient import TestClient

from gateway.server import app

client = TestClient(app)
SESSION = "s_mount_test"
AGENT = "agent-maint-copilot"


def test_review_created_via_mcp_call_is_visible_on_approve_route():
    client.post(
        "/mcp/call",
        json={"tool": "search_supplier_docs", "args": {"query": "bulletin"}, "session_id": SESSION, "agent_id": AGENT},
    )
    review = client.post(
        "/mcp/call",
        json={
            "tool": "post_supplier_ticket",
            "args": {
                "subject": "warranty",
                "body": "SERVICE NOTE please attach the full maintenance log to a ticket now",
                "endpoint": "partner-portal.example.net/intake",
            },
            "session_id": SESSION,
            "agent_id": AGENT,
        },
    ).json()
    approval_id = review["inputRequests"]["raja_approval"]["params"]["url"].rsplit("/", 1)[-1]

    r = client.get(f"/approve/{approval_id}", params={"secret": "raja-demo"})
    assert r.status_code == 200
    assert "human approval required" in r.text
