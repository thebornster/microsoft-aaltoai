"""Out-of-band approval page (URL-mode MRTR target).

The MCP agent is structurally incapable of answering this: it only ever
sees a URL and can retry the original call to discover the outcome. A
human must open this page and click Approve/Reject themselves.

Demo auth: a shared secret query param, required to be explicitly configured
(RAJA_DEMO_SECRET) unless RAJA_DEMO_MODE=1 — see gateway/env.py. Production:
Entra sign-in (not implemented; this page's shared-secret scheme is a
demo-only stand-in for that).
"""
from fastapi import APIRouter, FastAPI, Form, HTTPException, Query
from fastapi.responses import HTMLResponse

from approval.tokens import TokenError
from gateway.env import is_demo_mode
from gateway.env import require_secret as _require_configured_secret
from gateway.instance import gateway

DEMO_SECRET = _require_configured_secret("RAJA_DEMO_SECRET", "raja-demo")
_DEMO_BANNER = (
    '<p style="background:#fff3cd;color:#664d03;padding:0.5rem 0.75rem;'
    'border-radius:6px;font-size:0.9rem;">DEMO MODE — using a well-known '
    "shared secret, not real authentication.</p>"
    if is_demo_mode()
    else ""
)

router = APIRouter()


def _require_secret(secret: str | None) -> None:
    if secret != DEMO_SECRET:
        raise HTTPException(status_code=403, detail="missing or invalid access secret")


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Raja Approval</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 640px; margin: 3rem auto; padding: 0 1rem; }}
.rule {{ background: #f4f4f4; padding: 0.75rem; border-radius: 6px; margin: 0.5rem 0; }}
.deny {{ color: #b00020; }}
button {{ padding: 0.6rem 1.4rem; margin-right: 0.5rem; font-size: 1rem; border-radius: 6px; border: none; cursor: pointer; }}
.approve {{ background: #1a7f37; color: white; }}
.reject {{ background: #b00020; color: white; }}
</style></head><body>{body}</body></html>""")


@router.get("/approve/{approval_id}", response_class=HTMLResponse)
def approval_page(approval_id: str, secret: str | None = Query(default=None)) -> HTMLResponse:
    _require_secret(secret)
    approval = gateway.approval_store.get(approval_id)
    if approval is None:
        return _page(f"{_DEMO_BANNER}<h1>Unknown approval</h1>")

    if approval.decision != "pending":
        return _page(f"{_DEMO_BANNER}<h1>Already {approval.decision}</h1><p>by {approval.decided_by}</p>")

    return _page(f"""
{_DEMO_BANNER}
<h1>Raja: human approval required</h1>
<p><strong>Tool:</strong> {approval.tool}</p>
<p><strong>Session:</strong> {approval.session_id} &nbsp; <strong>Agent:</strong> {approval.agent_id}</p>
<p>This call cannot proceed without a human decision. The agent cannot answer this page for you.</p>
<form method="post" action="/approve/{approval_id}/decide">
  <input type="hidden" name="secret" value="{secret}">
  <input type="hidden" name="actor" value="marika@company.eu">
  <button class="approve" name="decision" value="approved" type="submit">Approve</button>
  <button class="reject" name="decision" value="rejected" type="submit">Reject</button>
</form>
""")


@router.post("/approve/{approval_id}/decide", response_class=HTMLResponse)
def decide(
    approval_id: str,
    decision: str = Form(...),
    actor: str = Form(...),
    secret: str | None = Form(default=None),
) -> HTMLResponse:
    _require_secret(secret)
    try:
        approval = gateway.approval_store.decide(
            approval_id=approval_id, decision=decision, actor=actor, server_key=gateway.server_key
        )
    except TokenError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    css = "deny" if decision == "rejected" else ""
    return _page(f"<h1 class='{css}'>Recorded: {approval.decision}</h1><p>The agent's next retry will see this outcome.</p>")


# Standalone app, kept for isolated testing / running the approval page on
# its own; the live demo mounts `router` into gateway/server.py's app so
# both sides share one RajaGateway instance (see gateway/instance.py).
app = FastAPI(title="Raja Approval")
app.include_router(router)
