"""ASGI entrypoint for the real MCP transport and approval surface.

Run standalone: `uvicorn gateway.mcp_app:app --port 8010`. The literal MCP
endpoint and the out-of-band approval page live on the same process so a
review URL remains usable when this is the only gateway process running.
"""
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlparse

from html import escape

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from mcp.server.transport_security import TransportSecuritySettings

from approval.app import router as approval_router
from gateway.instance import gateway
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


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing() -> HTMLResponse:
    rows = "".join(
        f"<tr><td><code>{escape(t.name)}</code></td><td>{escape(t.sink_class)}</td>"
        f"<td>{escape(t.destination_region or '-')}</td><td>{escape(t.description)}</td></tr>"
        for t in gateway.manifest.tools.values()
    )
    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Raja Gateway</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 760px; margin: 3rem auto; padding: 0 1rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd; vertical-align: top; }}
code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; border-radius: 4px; }}
</style></head><body>
<h1>Raja Gateway</h1>
<p>Deterministic policy gateway on the MCP tool boundary. Every value a tool returns
is labelled (<code>trust</code>, <code>residency</code>), tracked by provenance, and every
outgoing call is checked against <code>policy.yaml</code>. No LLM in the decision loop.</p>
<h2>Endpoints</h2>
<ul>
<li><code>POST /mcp</code> — MCP streamable HTTP (JSON-RPC; <code>initialize</code>, <code>tools/list</code>, <code>tools/call</code>)</li>
<li><code>GET <a href="/mcp/tools">/mcp/tools</a></code> — tool manifest as JSON</li>
<li><code>POST /mcp/call</code> — demo control surface used by the agent client and console</li>
<li><code>GET /approve/{{id}}</code> — out-of-band human approval page (URL-mode elicitation)</li>
<li><code>GET <a href="/healthz">/healthz</a></code></li>
</ul>
<h2>Governed tools</h2>
<table><tr><th>Tool</th><th>Sink class</th><th>Region</th><th>Description</th></tr>{rows}</table>
</body></html>""")


app.mount("/", mcp_app)
