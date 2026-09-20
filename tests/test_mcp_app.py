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
