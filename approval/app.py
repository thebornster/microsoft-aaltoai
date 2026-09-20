"""Out-of-band approval page (URL-mode MRTR target).

The MCP agent is structurally incapable of answering this: it only ever
sees a URL and can retry the original call to discover the outcome. A
human must open this page and click Approve/Reject themselves.

Demo auth: a shared secret query param. Production: Entra sign-in.
"""
import os

from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.responses import HTMLResponse

from approval.tokens import TokenError
from gateway.server import gateway

DEMO_SECRET = os.environ.get("RAJA_DEMO_SECRET", "raja-demo")

app = FastAPI(title="Raja Approval")


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


@app.get("/approve/{approval_id}", response_class=HTMLResponse)
def approval_page(approval_id: str, secret: str | None = Query(default=None)) -> HTMLResponse:
    _require_secret(secret)
    approval = gateway.approval_store.get(approval_id)
    if approval is None:
        return _page("<h1>Unknown approval</h1>")

    if approval.decision != "pending":
        return _page(f"<h1>Already {approval.decision}</h1><p>by {approval.decided_by}</p>")

    return _page(f"""
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


@app.post("/approve/{approval_id}/decide", response_class=HTMLResponse)
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
