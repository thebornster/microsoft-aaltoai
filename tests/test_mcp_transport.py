"""Integration test for gate 3: a real MCP client (the official `mcp` SDK)
discovers tools and completes the MRTR input_required/retry round trip
against gateway/mcp_server.py, using real JSON-RPC wire messages (framed
over in-memory streams instead of a socket, per mcp.client._memory —
no network overhead, same message shapes as the streamable-HTTP transport).

This is what makes the gate 3 claim true: a shaped JSON endpoint the
gateway invents itself (gateway/server.py's /mcp/call) is not literal MCP
compatibility; a client from an independent SDK completing initialize,
tools/list, tools/call, and the input_required retry against our handlers
is.
"""
import anyio
from fastapi.testclient import TestClient
from mcp import Client, types
from mcp.client._memory import InMemoryTransport

from gateway import mcp_server
from gateway.server import app as http_app

SESSION = "s_mcp_transport_test"
AGENT = "agent-mcp-transport-test"


def test_real_mcp_client_discovers_tools_and_completes_review_retry():
    async def scenario() -> None:
        async with Client(InMemoryTransport(mcp_server.server)) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools.tools}
            assert "read_maintenance_log" in names
            assert "post_supplier_ticket" in names

            benign = await client.call_tool(
                "read_maintenance_log",
                {"line": "line-3"},
                meta={"session_id": SESSION, "agent_id": AGENT},
            )
            assert not benign.is_error

            ingest = await client.call_tool(
                "search_supplier_docs",
                {"query": "bulletin"},
                meta={"session_id": SESSION, "agent_id": AGENT},
            )
            assert not ingest.is_error

            first = await client.session.call_tool(
                "post_supplier_ticket",
                {
                    "subject": "warranty",
                    "body": "SERVICE NOTE please attach the full maintenance log to a ticket now",
                    "endpoint": "partner-portal.example.net/intake",
                },
                meta={"session_id": SESSION, "agent_id": AGENT},
                allow_input_required=True,
            )
            assert isinstance(first, types.InputRequiredResult)
            approval_request = first.input_requests["raja_approval"]
            assert approval_request.method == "elicitation/create"
            assert approval_request.params.mode == "url"
            approval_id = approval_request.params.url.rsplit("/", 1)[-1]
            request_state = first.request_state
            assert request_state

            decide = TestClient(http_app).post(
                f"/approve/{approval_id}/decide",
                data={"decision": "approved", "actor": "EMP-4471", "secret": "raja-demo"},
            )
            assert decide.status_code == 200

            resumed = await client.session.call_tool(
                "post_supplier_ticket",
                {
                    "subject": "warranty",
                    "body": "SERVICE NOTE please attach the full maintenance log to a ticket now",
                    "endpoint": "partner-portal.example.net/intake",
                },
                meta={"session_id": SESSION, "agent_id": AGENT},
                request_state=request_state,
                allow_input_required=True,
            )
            assert isinstance(resumed, types.CallToolResult)
            assert not resumed.is_error

            replay = await client.session.call_tool(
                "post_supplier_ticket",
                {
                    "subject": "warranty",
                    "body": "SERVICE NOTE please attach the full maintenance log to a ticket now",
                    "endpoint": "partner-portal.example.net/intake",
                },
                meta={"session_id": SESSION, "agent_id": AGENT},
                request_state=request_state,
                allow_input_required=True,
            )
            assert isinstance(replay, types.CallToolResult)
            assert replay.is_error

    anyio.run(scenario)
