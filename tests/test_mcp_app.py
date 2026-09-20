from fastapi.testclient import TestClient

from gateway.mcp_app import app


def test_standalone_mcp_app_exposes_health_and_approval_routes():
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/approve/unknown?secret=raja-demo").status_code == 200
        landing = client.get("/")
        assert landing.status_code == 200
        assert "Open live control room" in landing.text
        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200
        assert "Decision intelligence" in dashboard.text
        agent = client.get("/agent")
        assert agent.status_code == 200
        assert "Run the browser agent" in landing.text
        assert "Summarise line 3 faults" in agent.text
        data = client.get("/dashboard/data")
        assert data.status_code == 200
        assert {"counts", "ledger", "recent"} <= data.json().keys()

        # one lifespan per process: the lineage check shares this client
        session = "lineage-test"
        client.post("/mcp/call", json={"tool": "read_maintenance_log", "args": {"line": "line-3"}, "session_id": session, "agent_id": "t"})
        denied = client.post("/mcp/call", json={
            "tool": "post_supplier_ticket",
            "args": {"subject": "x", "body": "EMP-4471 Jukka Nieminen gearbox vibration above threshold sensor B2"},
            "session_id": session, "agent_id": "t",
        }).json()
        assert denied["meta"]["decision"] == "DENY"
        latest = client.get("/dashboard/data").json()["recent"][0]
        assert latest["decision"] == "DENY"
        assert latest["destination_eu"] is False
        assert latest["sources"] == ["read_maintenance_log:line-3"]
        assert {"id": "gdpr-art44-transfer", "regulation": "GDPR Art. 44 - general principle for transfers"} in latest["rules"]
        assert latest["processing_path"][0] == "local-edge"
        assert latest["hash"] and latest["prev_hash"]
