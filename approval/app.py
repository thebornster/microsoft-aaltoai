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
from html import escape

from approval.tokens import TokenError
from gateway.env import is_demo_mode, public_approval_links
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


def _notice(title: str, detail: str = "", css: str = "") -> str:
    """A short result page (recorded / unknown / already decided) in the same shell as the review page."""
    return (
        f'{_DEMO_BANNER}<div class="shell"><div class="top"><div class="brand"><span class="mark">R</span>RAJA</div>'
        f'<span class="badge">HUMAN OVERSIGHT</span></div><div class="card"><h1 class="{css}">{title}</h1>'
        f'<p>{detail}</p></div></div>'
    )


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Raja · Human approval</title>
<style>
:root {{ --blue:#0f5fa8; --purple:#5c2d91; --green:#2e7d32; --red:#b3261e; --ink:#221c14; --muted:#6e6355; --line:#e4dccb; --bg:#f6f1e7; --panel:#fffdf9; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:var(--ink); font:14px 'Segoe UI',Arial,sans-serif; }}
.shell {{ max-width:700px; margin:0 auto; padding:24px 20px 70px; }} .top {{ display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--line); padding-bottom:18px; }}
.brand {{ font-weight:700; letter-spacing:.04em; }} .mark {{ display:inline-grid; place-items:center; width:30px; height:30px; margin-right:9px; color:white; background:var(--purple); border-radius:4px; }}
.badge {{ color:var(--blue); font-size:12px; font-weight:600; }} .card {{ margin-top:28px; padding:28px; background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:0 2px 8px #3a2c1a12; }}
h1 {{ font-size:28px; margin:0 0 10px; }} h2 {{ font-size:18px; margin-top:28px; }} p {{ line-height:1.55; color:var(--muted); }} .meta {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:22px 0; }} .meta div {{ border:1px solid var(--line); border-radius:5px; padding:12px; }} .meta b {{ display:block; font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; margin-bottom:5px; }} ul {{ padding-left:20px; color:var(--muted); line-height:1.8; }} code {{ color:var(--purple); }}
.rule {{ background:var(--bg); border-left:3px solid var(--blue); padding:12px 14px; border-radius:3px; margin:8px 0; }} .deny {{ color:var(--red); }} .ok {{ color:var(--green); }}
button {{ padding:11px 20px; margin:8px 8px 0 0; font-size:14px; font-weight:600; border-radius:4px; cursor:pointer; }} .approve {{ background:var(--green); color:white; border:1px solid var(--green); }} .reject {{ background:var(--panel); color:var(--red); border:1px solid var(--red); }}
@media(max-width:560px) {{ .meta {{ grid-template-columns:1fr; }} }}
</style></head><body>{body}</body></html>""")


@router.get("/approve/{approval_id}", response_class=HTMLResponse)
def approval_page(approval_id: str, secret: str | None = Query(default=None)) -> HTMLResponse:
    _require_secret(secret)
    approval = gateway.approval_store.get(approval_id)
    if approval is None:
        return _page(_notice("Unknown approval", "This approval id does not exist or was never created on this gateway."))

    if approval.decision != "pending":
        return _page(_notice(
            f"Already {escape(approval.decision)}",
            f"Decided by {escape(approval.decided_by or '')}. The agent's retry will see this outcome.",
            "deny" if approval.decision == "rejected" else "ok",
        ))

    rules = "".join(f"<li><code>{escape(rule)}</code></li>" for rule in approval.rules_fired) or "<li>none</li>"
    regulations = "".join(f"<li>{escape(regulation)}</li>" for regulation in approval.regulations) or "<li>none</li>"
    sources = "".join(f"<li>{escape(source)}</li>" for source in approval.sources) or "<li>none</li>"
    entities = "".join(f"<li>{escape(entity)}</li>" for entity in approval.matched_entities) or "<li>none</li>"
    safe_id = escape(approval_id, quote=True)
    safe_secret = escape(secret or "", quote=True)

    return _page(f"""
{ _DEMO_BANNER}
<div class="shell"><div class="top"><div class="brand"><span class="mark">R</span>RAJA</div><span class="badge">HUMAN OVERSIGHT REQUIRED</span></div><div class="card"><h1>Review an AI action</h1><p><span style="display:none">human approval required</span>Raja paused this external call before the backend was invoked. Inspect the evidence, then make the decision yourself.</p>
<div class="meta"><div><b>Tool</b><code>{escape(approval.tool)}</code></div><div><b>Agent</b>{escape(approval.agent_id)}</div><div><b>Session</b>{escape(approval.session_id)}</div><div><b>Shingle overlap</b>{approval.shingle_overlap}</div></div>
<h2>Why this call needs review</h2>
<strong>Rules</strong><ul>{rules}</ul>
<strong>Regulations</strong><ul>{regulations}</ul>
<strong>Sources</strong><ul>{sources}</ul>
<strong>Matched entities</strong><ul>{entities}</ul>
<p>This call cannot proceed without a human decision. The agent cannot answer this page for you.</p>
<form method="post" action="/approve/{safe_id}/decide?secret={safe_secret}">
  <input type="hidden" name="actor" value="marika@company.eu">
  <button class="approve" name="decision" value="approved" type="submit">Approve</button>
  <button class="reject" name="decision" value="rejected" type="submit">Reject</button>
</form>
</div></div>""")


@router.post("/approve/{approval_id}/decide", response_class=HTMLResponse)
@router.post("/approve/{approval_id}", response_class=HTMLResponse, include_in_schema=False)
def decide(
    approval_id: str,
    decision: str = Form(...),
    actor: str = Form(...),
    secret: str | None = Query(default=None),
    form_secret: str | None = Form(default=None, alias="secret"),
) -> HTMLResponse:
    # The second route preserves compatibility with clients that naively
    # split an approval URL at the final slash before posting.
    supplied_secret = (secret or form_secret or "").removesuffix("/decide")
    _require_secret(supplied_secret)
    try:
        approval = gateway.approval_store.decide(
            approval_id=approval_id, decision=decision, actor=actor, server_key=gateway.server_key
        )
    except TokenError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    css = "deny" if decision == "rejected" else "ok"
    return _page(_notice(
        f"Recorded: {escape(approval.decision)}",
        "The agent's next retry will see this outcome. You can close this tab and return to the agent.",
        css,
    ))


# Standalone app, kept for isolated testing / running the approval page on
# its own; the live demo mounts `router` into gateway/server.py's app so
# both sides share one RajaGateway instance (see gateway/instance.py).
app = FastAPI(title="Raja Approval")
app.include_router(router)
