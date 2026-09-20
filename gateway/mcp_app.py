"""ASGI entrypoint for the real MCP transport and approval surface.

Run standalone: `uvicorn gateway.mcp_app:app --port 8010`. The literal MCP
endpoint and the out-of-band approval page live on the same process so a
review URL remains usable when this is the only gateway process running.
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from approval.app import router as approval_router
from gateway.mcp_server import server

mcp_app = server.streamable_http_app(stateless_http=True)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with mcp_app.router.lifespan_context(mcp_app):
        yield


app = FastAPI(title="Raja MCP Gateway", lifespan=lifespan)
app.include_router(approval_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", mcp_app)
