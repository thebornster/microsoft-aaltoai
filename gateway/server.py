"""Stateless HTTP surface for the Raja gateway, matching the MCP
2026-07-28 pattern: a tool call either returns a result, an MRTR
input_required payload, or isError. No Mcp-Session-Id — session_id and
agent_id are explicit call arguments, per spec.
"""
import os
import pathlib

from fastapi import FastAPI
from pydantic import BaseModel

from gateway.gateway import RajaGateway, build_gateway

ROOT = pathlib.Path(__file__).parent.parent
SERVER_KEY = os.environ.get("RAJA_SERVER_KEY", "dev-only-insecure-key").encode("utf-8")

app = FastAPI(title="Raja Gateway")
gateway: RajaGateway = build_gateway(
    config_dir=ROOT / "config",
    ledger_path=ROOT / "data" / "ledger.jsonl",
    server_key=SERVER_KEY,
)


class ToolCallRequest(BaseModel):
    tool: str
    args: dict
    session_id: str
    agent_id: str
    inputResponses: dict | None = None
    requestState: str | None = None


@app.post("/mcp/call")
def mcp_call(req: ToolCallRequest) -> dict:
    return gateway.call(
        tool=req.tool,
        args=req.args,
        session_id=req.session_id,
        agent_id=req.agent_id,
        input_responses=req.inputResponses,
        request_state=req.requestState,
    )


@app.get("/mcp/tools")
def list_tools() -> dict:
    return {
        name: {"description": t.description, "input_schema": t.input_schema}
        for name, t in gateway.manifest.tools.items()
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
