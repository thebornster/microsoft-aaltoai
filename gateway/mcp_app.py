"""ASGI entrypoint for the real MCP transport and approval surface.

Run standalone: `uvicorn gateway.mcp_app:app --port 8010`. The literal MCP
endpoint and the out-of-band approval page live on the same process so a
review URL remains usable when this is the only gateway process running.
"""
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlparse

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from approval.app import router as approval_router
from gateway.mcp_server import server
from gateway.server import list_tools, mcp_call


def _transport_security() -> TransportSecuritySettings:
    """DNS-rebinding protection: localhost always, plus the public host when deployed."""
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    public = urlparse(os.environ.get("RAJA_PUBLIC_BASE_URL", ""))
    if public.netloc:
        hosts.append(public.netloc)
        origins.append(f"{public.scheme}://{public.netloc}")
    return TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins)


mcp_app = server.streamable_http_app(
    stateless_http=True,
    transport_security=_transport_security(),
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with mcp_app.router.lifespan_context(mcp_app):
        yield


app = FastAPI(title="Raja MCP Gateway", lifespan=lifespan)
app.include_router(approval_router)
# Demo harness control surface (gateway/server.py) on the same process, so the
# Azure OpenAI agent and local fallback can target one deployed URL.
app.add_api_route("/mcp/call", mcp_call, methods=["POST"])
app.add_api_route("/mcp/tools", list_tools, methods=["GET"])


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", mcp_app)
