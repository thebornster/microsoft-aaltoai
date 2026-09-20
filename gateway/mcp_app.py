"""ASGI entrypoint for the real MCP transport (gateway/mcp_server.py).

Run standalone: `uvicorn gateway.mcp_app:app --port 8010`. Kept as a
separate process from gateway/server.py's `/mcp/call` control surface
deliberately: the streamable-HTTP session manager owns its own ASGI
lifespan, and stacking it under the existing FastAPI app would require
composing two independent lifespans for no benefit — a real MCP client
only needs one port. It shares no in-memory state with gateway/server.py's
process; run the demo client against whichever surface you're proving.
"""
from gateway.mcp_server import server

app = server.streamable_http_app(stateless_http=True)
