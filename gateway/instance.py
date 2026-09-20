"""Single shared RajaGateway instance.

Both the MCP call surface (gateway/server.py) and the out-of-band approval
page (approval/app.py) must see the same in-memory approval_store and
taint sessions. They are mounted into one FastAPI app and served by one
uvicorn process — a separate process per app would each build its own
gateway with an empty approval_store, and "unknown approval_id" would
turn up. This module exists so both sides import the same instance
instead of one importing the other.
"""
import logging
import pathlib

from approval.teams import notify_review
from gateway.env import is_demo_mode, require_secret
from gateway.gateway import RajaGateway, build_gateway

logger = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).parent.parent

# fail-closed unless RAJA_DEMO_MODE=1 is set explicitly (gate 5) — see gateway/env.py
if is_demo_mode():
    logger.warning("RAJA_DEMO_MODE=1: running with demo defaults (insecure server key/secrets allowed).")
SERVER_KEY = require_secret("RAJA_SERVER_KEY", "dev-only-insecure-key").encode("utf-8")

gateway: RajaGateway = build_gateway(
    config_dir=ROOT / "config",
    ledger_path=ROOT / "data" / "ledger.jsonl",
    server_key=SERVER_KEY,
    state_db_path=ROOT / "data" / "state.db",
)
gateway.on_review = notify_review
