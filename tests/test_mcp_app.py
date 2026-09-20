from fastapi.testclient import TestClient

from gateway.mcp_app import app


def test_standalone_mcp_app_exposes_health_and_approval_routes():
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/approve/unknown?secret=raja-demo").status_code == 200
