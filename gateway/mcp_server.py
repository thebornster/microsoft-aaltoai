"""Real MCP (2026-07-28) transport for Raja, built on the official `mcp`
SDK's streamable-HTTP server. This is the literal discovery/call surface a
real MCP client speaks: `initialize`, `tools/list`, `tools/call`, including
the MRTR `input_required`/retry round trip via the SDK's own
`InputRequiredResult` and `ElicitRequestURLParams` types.

It is a thin translation layer only. All policy/taint/ledger logic still
lives in gateway.gateway.RajaGateway — this module just speaks the wire
protocol and forwards to gateway.instance.gateway.call(). Session/agent
identity travels in `_meta` per the spec's guidance for stateless
application-level handles (Mcp-Session-Id is retired).
"""
from __future__ import annotations

from typing import Any

from mcp import types
from mcp.server.lowlevel import Server

from gateway.instance import gateway


async def _on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
    tools = [
        types.Tool(name=name, description=tool.description, inputSchema=tool.input_schema)
        for name, tool in gateway.manifest.tools.items()
    ]
    return types.ListToolsResult(tools=tools)


def _identity(params: types.CallToolRequestParams) -> tuple[str | None, str | None]:
    meta = (params.meta or {}) if params.meta else {}
    arguments = params.arguments or {}
    session_id = meta.get("session_id") or arguments.get("session_id")
    agent_id = meta.get("agent_id") or arguments.get("agent_id")
    return session_id, agent_id


def _error_result(message: str) -> types.CallToolResult:
    return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text=message)])


async def _on_call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult | types.InputRequiredResult:
    session_id, agent_id = _identity(params)
    if not session_id or not agent_id:
        return _error_result("session_id and agent_id are required (pass via _meta)")

    outcome = gateway.call(
        tool=params.name,
        args=dict(params.arguments or {}),
        session_id=session_id,
        agent_id=agent_id,
        input_responses=None,
        request_state=params.request_state,
    )

    if outcome.get("resultType") == "input_required":
        raja_approval = outcome["inputRequests"]["raja_approval"]["params"]
        return types.InputRequiredResult(
            inputRequests={
                "raja_approval": types.ElicitRequest(
                    params=types.ElicitRequestURLParams(
                        message=raja_approval["message"],
                        url=raja_approval["url"],
                    ),
                ),
            },
            requestState=outcome["requestState"],
        )

    if outcome.get("isError"):
        return _error_result(str(outcome.get("error")))

    result = outcome.get("result")
    structured = result if isinstance(result, dict) else None
    return types.CallToolResult(content=[types.TextContent(type="text", text=str(result))], structuredContent=structured)


server = Server(
    name="raja-gateway",
    version="0.1.0",
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)
