"""Stateless HTTP surface for the Raja gateway, matching the MCP
2026-07-28 pattern: a tool call either returns a result, an MRTR
input_required payload, or isError. No Mcp-Session-Id — session_id and
agent_id are explicit call arguments, per spec.

Also mounts the out-of-band approval page (approval/app.py) on the same
app so both sides share one RajaGateway instance — see gateway/instance.py.
"""
from fastapi import FastAPI
from pydantic import BaseModel

from approval.app import router as approval_router
from gateway.instance import gateway

app = FastAPI(title="Raja Gateway")
app.include_router(approval_router)


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
