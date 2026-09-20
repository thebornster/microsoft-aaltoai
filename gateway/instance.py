"""Single shared RajaGateway instance.

Both the MCP call surface (gateway/server.py) and the out-of-band approval
page (approval/app.py) must see the same in-memory approval_store and
taint sessions. They are mounted into one FastAPI app and served by one
uvicorn process — a separate process per app would each build its own
gateway with an empty approval_store, and "unknown approval_id" would
turn up. This module exists so both sides import the same instance
instead of one importing the other.
"""
import os
import pathlib

from approval.teams import notify_review
from gateway.gateway import RajaGateway, build_gateway

ROOT = pathlib.Path(__file__).parent.parent
SERVER_KEY = os.environ.get("RAJA_SERVER_KEY", "dev-only-insecure-key").encode("utf-8")

gateway: RajaGateway = build_gateway(
    config_dir=ROOT / "config",
    ledger_path=ROOT / "data" / "ledger.jsonl",
    server_key=SERVER_KEY,
)
gateway.on_review = notify_review
