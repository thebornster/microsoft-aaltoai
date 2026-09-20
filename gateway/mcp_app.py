"""ASGI entrypoint for the real MCP transport and approval surface.

Run standalone: `uvicorn gateway.mcp_app:app --port 8010`. The literal MCP
endpoint and the out-of-band approval page live on the same process so a
review URL remains usable when this is the only gateway process running.
"""
import os
import socket
from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlparse

from html import escape

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from mcp.server.transport_security import TransportSecuritySettings

from approval.app import router as approval_router
from gateway.instance import gateway
from gateway.ledger import verify_chain
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


@app.get("/deployment/data")
def deployment_data() -> dict:
    """Runtime proof of the deployed gateway, with no secrets or payloads."""
    public_url = os.environ.get("RAJA_PUBLIC_BASE_URL", "")
    host = urlparse(public_url).hostname or ""
    records = gateway.ledger.read_all()
    verified, bad_seq, reason = verify_chain(records)
    return {
        "platform": "Azure Container Apps" if ".azurecontainerapps.io" in host else "local/container",
        "region": os.environ.get("RAJA_DEPLOYMENT_REGION") or ("Sweden Central" if "swedencentral" in host else "local"),
        "hostname": host or socket.gethostname(),
        "revision": os.environ.get("RAJA_BUILD_TAG", "development"),
        "deployed_at": os.environ.get("RAJA_DEPLOYED_AT", "runtime"),
        "public_base_url": public_url or None,
        "mcp_endpoint": "/mcp",
        "control_surface": "/mcp/call",
        "tool_count": len(gateway.manifest.tools),
        "ledger": {"records": len(records), "verified": verified, "bad_seq": bad_seq, "message": reason},
    }


def _dashboard_payload() -> dict:
    records = gateway.ledger.read_all()
    counts = {decision: sum(1 for record in records if record.get("decision") == decision)
              for decision in ("ALLOW", "REVIEW", "DENY")}
    ok, bad_seq, reason = verify_chain(records)
    recent = []
    for record in records[-40:]:
        labels = record.get("arg_labels") or {}
        recent.append({
            "seq": record.get("seq"),
            "tool": record.get("tool"),
            "decision": record.get("decision"),
            "destination": record.get("destination_region") or "local / internal",
            "trust": labels.get("trust"),
            "residency": labels.get("residency"),
            "sources": labels.get("sources") or [],
            "rules": record.get("rules_fired") or [],
            "backend_invoked": bool(record.get("backend_invoked", False)),
            "timestamp": record.get("timestamp") or record.get("created_at"),
        })
    return {
        "status": "operational",
        "records": len(records),
        "counts": counts,
        "ledger": {"verified": ok, "bad_seq": bad_seq, "message": reason},
        "tools": len(gateway.manifest.tools),
        "recent": list(reversed(recent)),
    }


@app.get("/dashboard/data")
def dashboard_data() -> dict:
    """Read-only, metadata-only view for the public judge dashboard."""
    return _dashboard_payload()


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    return HTMLResponse("""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raja · Live control room</title>
<style>
:root{--bg:#f6f1e7;--panel:#fffdf9;--line:#e4dccb;--ink:#221c14;--muted:#6e6355;--blue:#0f5fa8;--blue-tint:#e8f0f9;--red:#b3261e;--red-tint:#f9e3e1;--orange:#9a5a00;--orange-tint:#f8ecd8;--green:#2e7d32;--green-tint:#e6f2e6;--purple:#5c2d91}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px 'Segoe UI',Arial,sans-serif}a{color:var(--blue);text-decoration:none}
.shell{max-width:1240px;margin:auto;padding:25px 25px 60px}.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:20px}
.brand{font-weight:bold;letter-spacing:.08em}.brand i{display:inline-grid;place-items:center;background:var(--purple);color:white;border-radius:5px;width:29px;height:29px;font-style:normal;margin-right:9px}
.top small,.muted{color:var(--muted)}.nav a{margin-left:19px;font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.heading{display:flex;justify-content:space-between;align-items:end;padding:40px 0 25px}.heading h1{font-size:38px;letter-spacing:-.05em;margin:0 0 7px}.heading p{color:var(--muted);margin:0}.live{color:var(--blue);font-size:12px;font-weight:bold}.live:before{content:"";display:inline-block;width:8px;height:8px;background:var(--green);border-radius:50%;margin-right:7px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}.metric,.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:0 2px 6px #3a2c1a0d}.metric{padding:20px}.metric label{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.1em}.metric strong{font-size:33px;display:block;margin-top:12px}.metric em{font-style:normal;font-size:11px;color:var(--muted)}
.body{display:grid;grid-template-columns:1.45fr .8fr;gap:15px;margin-top:15px}.panel{padding:21px}.panel h2{font-size:16px;margin:0 0 18px}.panel-head{display:flex;justify-content:space-between;align-items:center}.refresh{color:var(--blue);font-size:11px;cursor:pointer}
table{width:100%;border-collapse:collapse}th{text-align:left;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em;padding:0 7px 12px}td{border-top:1px solid var(--line);padding:14px 7px;font-size:12px}td:first-child{color:var(--muted);font-family:monospace}.decision{font-size:10px;font-weight:bold;letter-spacing:.08em;padding:5px 8px;border-radius:3px}.ALLOW{color:var(--green);background:var(--green-tint)}.REVIEW{color:var(--orange);background:var(--orange-tint)}.DENY{color:var(--red);background:var(--red-tint)}
.proof{display:flex;align-items:center;gap:13px;border:1px solid #c9d9ea;background:var(--blue-tint);border-radius:8px;padding:14px;margin-bottom:20px}.proof strong{color:var(--blue);display:block;margin-bottom:4px}.proof span{color:var(--muted);font-size:12px}.ring{width:34px;height:34px;border-radius:50%;border:3px solid var(--blue);border-top-color:transparent;flex:none}
.bar{margin:17px 0}.barline{height:8px;background:var(--line);border-radius:5px;display:flex;overflow:hidden;margin-top:8px}.barline i{display:block}.barline .a{background:var(--green)}.barline .r{background:var(--orange)}.barline .d{background:var(--red)}.legend{display:flex;justify-content:space-between;color:var(--muted);font-size:11px}
.empty{color:var(--muted);padding:25px 7px;text-align:center}.foot{color:var(--muted);font:10px monospace;margin-top:30px}
@media(max-width:800px){.metrics{grid-template-columns:repeat(2,1fr)}.body{grid-template-columns:1fr}.heading{display:block}.heading .live{display:block;margin-top:18px}table{font-size:11px}.hide{display:none}}
</style></head><body><div class="shell">
<header class="top"><div class="brand"><i>R</i>RAJA <small>/ LIVE CONTROL ROOM</small></div><div class="nav"><a href="/">Overview</a><a href="/agent">Agent</a><a href="/mcp/tools">Tools</a></div></header>
<section class="heading"><div><h1>Decision intelligence</h1><p>Every governed action, its provenance, and its policy outcome.</p></div><div class="live">LIVE · AUTO-REFRESH 5S</div></section>
<section class="metrics"><div class="metric"><label>Total decisions</label><strong id="total">—</strong><em>append-only ledger</em></div><div class="metric"><label>Allowed</label><strong id="allow">—</strong><em>backend invoked</em></div><div class="metric"><label>Human review</label><strong id="review">—</strong><em>out-of-band approval</em></div><div class="metric"><label>Hard denied</label><strong id="deny">—</strong><em>blocked before egress</em></div></section>
<section class="body"><div class="panel"><div class="panel-head"><h2>Recent policy decisions</h2><span class="refresh" onclick="load()">↻ REFRESH</span></div><table><thead><tr><th>Seq</th><th>Tool</th><th>Outcome</th><th>Destination</th><th>Path</th></tr></thead><tbody id="feed"><tr><td colspan="5" class="empty">Loading decision feed…</td></tr></tbody></table></div>
<aside class="panel"><h2>Integrity & deployment proof</h2><div class="proof"><div class="ring"></div><div><strong id="chain">Verifying chain…</strong><span id="chain-copy">Checking cryptographic continuity</span></div></div><div class="bar"><div class="legend"><span>Decision mix</span><span id="mix">—</span></div><div class="barline"><i class="a" id="bar-a"></i><i class="r" id="bar-r"></i><i class="d" id="bar-d"></i></div></div><div class="bar"><div class="legend"><span>Governed surfaces</span><span id="tools">—</span></div></div><div id="azure-proof" class="proof" style="margin-top:22px"><div><strong>Verifying runtime…</strong><span>Reading deployment metadata from the gateway</span></div></div><p class="muted" style="line-height:1.55;font-size:12px">Raja makes no probabilistic policy decisions. It labels data at ingress, resolves exact provenance, evaluates every rule, and records the result before a sink can run.</p></aside></section>
<div class="foot">RAJA / SHA-256 HASH-CHAINED EVIDENCE / NO LLM IN THE DECISION LOOP</div></div>
<script>
const esc=s=>String(s??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function load(){try{const d=await fetch("/dashboard/data",{cache:"no-store"}).then(r=>r.json());const c=d.counts||{};const total=d.records||0;
document.querySelector("#total").textContent=total;document.querySelector("#allow").textContent=c.ALLOW||0;document.querySelector("#review").textContent=c.REVIEW||0;document.querySelector("#deny").textContent=c.DENY||0;document.querySelector("#tools").textContent=d.tools+" tools";
document.querySelector("#mix").textContent=total+" total";for(const [id,key] of [["a","ALLOW"],["r","REVIEW"],["d","DENY"]])document.querySelector("#bar-"+id).style.width=(total?(c[key]||0)/total*100:0)+"%";
const chain=document.querySelector("#chain");chain.textContent=d.ledger.verified?"Ledger verified":"Ledger integrity warning";chain.style.color=d.ledger.verified?"var(--blue)":"var(--red)";document.querySelector("#chain-copy").textContent=d.ledger.message;
document.querySelector("#feed").innerHTML=d.recent.length?d.recent.map(r=>`<tr><td>#${esc(r.seq)}</td><td><b>${esc(r.tool)}</b><br><span class="muted">${esc(r.trust||"unknown")} · ${esc(r.residency||"unlabelled")}</span></td><td><span class="decision ${esc(r.decision)}">${esc(r.decision)}</span></td><td>${esc(r.destination)}</td><td>${r.backend_invoked?"<span style='color:var(--green)'>invoked</span>":"<span style='color:var(--orange)'>held / blocked</span>"}</td></tr>`).join(""):'<tr><td colspan="5" class="empty">No decisions yet. Run the demo agent to populate the control room.</td></tr>';
}catch(e){document.querySelector("#chain").textContent="Dashboard unavailable";document.querySelector("#chain-copy").textContent="Retrying connection…"}}async function deployment(){try{const d=await fetch("/deployment/data",{cache:"no-store"}).then(r=>r.json());document.querySelector("#azure-proof").innerHTML=`<div><strong>${esc(d.platform)} · ${esc(d.region)}</strong><span>${esc(d.hostname)} · ${esc(d.revision)} · ${esc(d.tool_count)} tools · ${esc(d.mcp_endpoint)}</span></div>`}catch(e){document.querySelector("#azure-proof").innerHTML="<div><strong>Runtime metadata unavailable</strong></div>"}}load();deployment();setInterval(load,5000);setInterval(deployment,15000);
</script></body></html>""")


@app.get("/agent", response_class=HTMLResponse, include_in_schema=False)
def agent_playground() -> HTMLResponse:
    """A browser-native, deterministic agent demo on the same origin."""
    return HTMLResponse("""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raja · Agent playground</title>
<style>
:root{--bg:#f6f1e7;--bg2:#fbf8f1;--panel:#fffdf9;--line:#e4dccb;--ink:#221c14;--muted:#6e6355;--blue:#0f5fa8;--red:#b3261e;--orange:#9a5a00;--orange-tint:#f8ecd8;--green:#2e7d32;--purple:#5c2d91}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,var(--bg),var(--bg2));color:var(--ink);font:14px 'Segoe UI',Arial,sans-serif}a{color:var(--blue);text-decoration:none}
.shell{max-width:1050px;margin:auto;padding:25px}.top{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:20px}.brand{font-weight:bold;letter-spacing:.08em}.brand i{display:inline-grid;place-items:center;background:var(--purple);color:white;border-radius:5px;width:29px;height:29px;font-style:normal;margin-right:9px}.nav a{margin-left:20px;font-size:12px;text-transform:uppercase}
.hero{padding:65px 0 35px}.eyebrow{color:var(--purple);font:11px monospace;letter-spacing:.13em;text-transform:uppercase}.hero h1{font-size:50px;letter-spacing:-.06em;margin:17px 0 13px}.hero p{color:var(--muted);font-size:17px;line-height:1.5;max-width:680px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}.card,.console{background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:0 2px 6px #3a2c1a0d}.card{padding:19px;text-align:left;color:var(--ink);cursor:pointer;font:inherit}.card:hover{border-color:var(--blue);transform:translateY(-2px)}.card strong{display:block;font-size:16px;margin-bottom:8px}.card span{color:var(--muted);font-size:13px;line-height:1.4}.tag{color:var(--blue);font:10px monospace;text-transform:uppercase;display:block;margin-bottom:15px}.tag.red{color:var(--red)}.tag.orange{color:var(--orange)}
.console{margin-top:16px;padding:20px;min-height:275px}.console-head{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:14px}.console h2{font-size:15px;margin:0}.status{color:var(--blue);font:11px monospace}.log{font:13px monospace;line-height:1.75;white-space:pre-wrap;color:var(--muted);padding-top:10px}.log .ok{color:var(--green)}.log .warn{color:var(--orange)}.log .bad{color:var(--red)}button{background:var(--blue);color:#fff;border:0;border-radius:7px;padding:10px 15px;font-weight:bold;cursor:pointer}.approval{display:none;background:var(--orange-tint);border:1px solid var(--orange);padding:15px;border-radius:9px;margin-top:15px;color:var(--ink)}.approval span{color:var(--muted)}.approval a{display:inline-block;margin-top:10px;border:1px solid var(--orange);padding:8px 11px;color:var(--orange);border-radius:6px;background:var(--panel)}.continue{display:none;margin-top:10px}.foot{color:var(--muted);font:10px monospace;margin-top:28px}@media(max-width:700px){.grid{grid-template-columns:1fr}.hero h1{font-size:39px}.nav a{margin-left:8px}}
</style></head><body><div class="shell">
<header class="top"><div class="brand"><i>R</i>RAJA <span style="color:var(--muted);font-weight:normal">/ AGENT PLAYGROUND</span></div><div class="nav"><a href="/">Overview</a><a href="/dashboard">Dashboard</a><a href="/deployment/data">Runtime proof</a></div></header>
<main class="hero"><div class="eyebrow">A real browser client · same MCP boundary</div><h1>Ask the agent to act.</h1><p>Pick a goal below. The browser sends real tool calls to the deployed Raja gateway. Watch the agent read data, encounter policy, and stop before an unsafe sink.</p>
<div class="grid"><button class="card" onclick="run('safe')"><span class="tag">01 / safe task</span><strong>Summarise line 3 faults</strong><span>Read trusted maintenance data. Should pass without friction.</span></button><button class="card" onclick="run('deny')"><span class="tag red">02 / attack</span><strong>Follow the supplier bulletin</strong><span>Read a poisoned PDF and attempt to send personal data outside the EU.</span></button><button class="card" onclick="run('review')"><span class="tag orange">03 / oversight</span><strong>File a safe follow-up</strong><span>Paraphrase the request. Raja still requires a human approval.</span></button></div></main>
<section class="console"><div class="console-head"><h2>Agent activity</h2><span class="status" id="status">READY</span></div><div class="log" id="log">Choose a goal to start the agent…</div><div class="approval" id="approval"><b>Human approval required</b><br><span>The agent cannot approve this request. Open the approval page, make the decision, then return here.</span><br><a id="approval-link" target="_blank" rel="noopener">Open approval page ↗</a><br><button class="continue" id="continue" onclick="resume()">Continue after approval</button></div></section>
<div class="foot">TRANSPARENT DEMO CLIENT · POLICY DECISIONS ARE MADE BY RAJA · NO BROWSER SECRET OR LLM KEY IS EXPOSED</div></div>
<script>
let session="",state="",reviewArgs=null;const logEl=document.querySelector("#log"),statusEl=document.querySelector("#status");
function line(text,cls=""){logEl.innerHTML+=`<div class="${cls}">${text}</div>`}function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
async function call(tool,args,retry=false){const body={tool,args,session_id:session,agent_id:"browser-demo-agent"};if(retry){body.requestState=state;body.inputResponses={raja_approval:{action:"accept"}}}const r=await fetch("/mcp/call",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});return r.json()}
function start(){session="browser-"+crypto.randomUUID().slice(0,8);state="";reviewArgs=null;logEl.innerHTML="";document.querySelector("#approval").style.display="none";document.querySelector("#continue").style.display="none";statusEl.textContent="RUNNING"}
async function run(kind){start();try{if(kind==="safe"){line("→ Agent: read maintenance log for line 3");const r=await call("read_maintenance_log",{line:"line-3"});line("✓ ALLOW · trusted EU personal data stayed inside the governed flow","ok");line("  Agent received "+esc(r.result.entries.length)+" maintenance entries.");}
if(kind==="deny"){line("→ Agent: search supplier documents for warranty A19");await call("search_supplier_docs",{query:"warranty A19"});line("→ Agent: read line 3 maintenance log");const r=await call("read_maintenance_log",{line:"line-3"});const body=r.result.entries.map(e=>e.operator_id+" "+e.operator_name+": "+e.description).join("; ");line("→ Agent: attach full log to external supplier ticket");const out=await call("post_supplier_ticket",{subject:"Warranty validation for bulletin A19",body:"Per bulletin A19, attaching full maintenance log: "+body,endpoint:"partner-portal.example.net/intake"});line("✕ DENY · GDPR transfer blocked before backend invocation","bad");line("  Rules: "+esc((out.meta?.rules_fired||["gdpr-art44-transfer"]).join(", "))); }
if(kind==="review"){line("→ Agent: search supplier documents for warranty A19");await call("search_supplier_docs",{query:"warranty A19"});reviewArgs={subject:"Bulletin A19 follow-up",body:"Filing the supplier follow-up ticket summarising recent line issues without listing anyone by name.",endpoint:"partner-portal.example.net/intake"};line("→ Agent: file external follow-up ticket");const out=await call("post_supplier_ticket",reviewArgs);if(out.resultType==="input_required"){state=out.requestState;const url=out.inputRequests.raja_approval.params.url;document.querySelector("#approval-link").href=url;document.querySelector("#approval").style.display="block";document.querySelector("#continue").style.display="inline-block";line("! REVIEW · Raja paused the call for out-of-band approval","warn");line("  The agent is structurally unable to approve this itself.");statusEl.textContent="WAITING FOR HUMAN";return}}
statusEl.textContent="COMPLETE";line("Done. Open the Dashboard tab to inspect the ledger evidence.","ok")}catch(e){statusEl.textContent="ERROR";line("Gateway error: "+esc(e),"bad")}}
async function resume(){const btn=document.querySelector("#continue");btn.disabled=true;line("→ Agent: retrying the exact approved call");let out;try{out=await call("post_supplier_ticket",reviewArgs,true)}catch(e){line("Gateway error: "+esc(e),"bad");statusEl.textContent="ERROR";btn.disabled=false;return}
if(out.result){line("✓ ALLOW AFTER APPROVAL · supplier backend invoked","ok");statusEl.textContent="COMPLETE";document.querySelector("#approval").style.display="none";line("Done. Open the Dashboard tab to inspect the full lineage.","ok");return}
if(out.resultType==="input_required"){line("! Still waiting for a human decision. Open the approval page, click Approve, then Continue again.","warn");statusEl.textContent="WAITING FOR HUMAN";btn.disabled=false;return}
line("✕ Resume rejected: "+esc(out.error),"bad");line("  The gateway refused the retry. Rejected, expired, or replayed approvals cannot be resumed; start the scenario again.","bad");statusEl.textContent="ERROR"}
</script></body></html>""")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing() -> HTMLResponse:
    tools = list(gateway.manifest.tools.values())
    tool_cards = "".join(
        f'<div class="tool"><div class="tool-top"><code>{escape(t.name)}</code>'
        f'<span class="pill {"egress" if t.sink_class == "egress_external" else "read"}">'
        f'{escape(t.sink_class.replace("_", " "))}</span></div>'
        f'<p>{escape(t.description)}</p><small>{escape(t.destination_region or "local / internal")}</small></div>'
        for t in tools
    )
    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raja · Sovereign AI control plane</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');
:root {{ --ink:#221c14; --muted:#6e6355; --line:#e4dccb; --bg:#f6f1e7; --bg2:#fbf8f1; --panel:#fffdf9; --blue:#0f5fa8; --blue-tint:#e8f0f9; --purple:#5c2d91; --orange:#9a5a00; --orange-tint:#f8ecd8; --green:#2e7d32; --green-tint:#e6f2e6; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:linear-gradient(135deg,var(--bg),var(--bg2)); color:var(--ink); font-family:'Space Grotesk','Segoe UI',sans-serif; }}
.wrap {{ max-width:1160px; margin:auto; padding:28px 26px 80px }} nav {{ display:flex; justify-content:space-between; align-items:center; }}
.brand {{ display:flex; gap:11px; align-items:center; font-weight:700; letter-spacing:.04em }} .mark {{ width:34px; height:34px; background:var(--purple); border-radius:5px; display:grid; place-items:center; color:white; font-family:'DM Mono'; }}
nav a {{ color:var(--muted); text-decoration:none; margin-left:22px; font-size:14px }} nav a:hover {{ color:var(--blue) }}
.hero {{ display:grid; grid-template-columns:1.25fr .75fr; gap:70px; align-items:center; padding:100px 0 86px }}
.eyebrow {{ color:var(--blue); font:12px 'DM Mono'; text-transform:uppercase; letter-spacing:.16em }} h1 {{ font-size:clamp(45px,7vw,82px); line-height:.96; letter-spacing:-.065em; margin:20px 0 25px; max-width:700px }} h1 span {{ color:var(--blue) }}
.lead {{ color:var(--muted); font-size:19px; line-height:1.55; max-width:620px }} .actions {{ margin-top:32px; display:flex; gap:13px; flex-wrap:wrap }}
.btn {{ border:1px solid var(--blue); color:#fff; background:var(--blue); border-radius:4px; padding:13px 19px; text-decoration:none; font-weight:600 }} .btn.alt {{ background:var(--panel); color:var(--blue); border-color:var(--line) }}
.orb {{ border:1px solid var(--line); border-radius:8px; background:var(--panel); padding:28px; box-shadow:0 10px 30px #3a2c1a14 }} .orb-title {{ font:12px 'DM Mono'; color:var(--muted) }}
.signal {{ display:flex; gap:13px; align-items:center; margin:25px 0 30px }} .dot {{ width:12px; height:12px; border-radius:50%; background:var(--green); box-shadow:0 0 14px var(--green) }} .signal strong {{ font-size:25px }} .signal small {{ display:block; color:var(--muted) }}
.flow {{ display:flex; justify-content:space-between; gap:8px; align-items:center; color:var(--muted); font:11px 'DM Mono' }} .node {{ border:1px solid var(--line); border-radius:5px; padding:13px 8px; text-align:center; color:var(--ink); flex:1; background:var(--bg) }} .arrow {{ color:var(--blue) }}
.section {{ border-top:1px solid var(--line); padding-top:45px; margin-top:18px }} h2 {{ font-size:30px; letter-spacing:-.04em; margin:0 0 12px }} .sub {{ color:var(--muted); margin:0 0 28px }}
.grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px }} .card,.tool {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:21px; box-shadow:0 2px 6px #3a2c1a0d }} .card b {{ color:var(--blue); font:14px 'DM Mono' }} .card h3 {{ margin:13px 0 8px }} .card p,.tool p {{ color:var(--muted); line-height:1.5; margin:0; font-size:14px }}
.tools {{ display:grid; grid-template-columns:repeat(2,1fr); gap:12px }} .tool-top {{ display:flex; justify-content:space-between; gap:10px; align-items:center }} code {{ color:var(--purple); font:13px 'DM Mono' }} .pill {{ border-radius:20px; padding:4px 9px; font:10px 'DM Mono'; text-transform:uppercase }} .pill.read {{ background:var(--green-tint); color:var(--green) }} .pill.egress {{ background:var(--orange-tint); color:var(--orange) }} .tool small {{ color:var(--muted); display:block; margin-top:15px; font:11px 'DM Mono' }}
.footer {{ margin-top:70px; color:var(--muted); font:11px 'DM Mono'; display:flex; justify-content:space-between; gap:20px }} .footer a {{ color:var(--blue) }}
@media(max-width:780px) {{ .hero {{ grid-template-columns:1fr; padding:70px 0 }} .grid,.tools {{ grid-template-columns:1fr }} nav a {{ margin-left:10px }} .hide-mobile {{ display:none }} }}
</style></head><body>
<div class="wrap"><nav><div class="brand"><div class="mark">R</div> RAJA <span class="hide-mobile" style="color:var(--muted);font-weight:400">/ sovereign AI control plane</span></div><div><a href="/agent">RUN AGENT ↗</a><a href="/dashboard">LIVE DASHBOARD ↗</a><a href="/mcp/tools">API MANIFEST ↗</a></div></nav>
<main class="hero"><div><div class="eyebrow">MCP policy gateway · Sweden Central</div><h1>Make every AI action <span>provable.</span></h1><p class="lead">Raja sits between an agent and its tools. It tracks trust, residency, and provenance—then blocks unlawful transfers and holds risky actions for a real human.</p><div class="actions"><a class="btn" href="/agent">Run the browser agent</a><a class="btn alt" href="/dashboard">Open live control room</a></div></div>
<div class="orb"><div class="orb-title">LIVE RUNTIME PROOF</div><div class="signal"><div class="dot"></div><div><strong id="runtime-status">Connecting…</strong><small id="runtime-copy">Reading the deployed gateway</small></div></div><div class="flow"><div class="node">browser<br><small>client</small></div><div class="arrow">→</div><div class="node">MCP<br><small id="runtime-mcp">/mcp</small></div><div class="arrow">→</div><div class="node">policy<br><small id="runtime-tools">… tools</small></div></div></div></main>
<section class="section"><h2>One boundary. Two threats.</h2><p class="sub">Prompt injection and data residency are both data-flow violations. Raja governs them with the same deterministic pipeline.</p><div class="grid"><div class="card"><b>01 / LABEL</b><h3>Trust + residency</h3><p>Every tool result is labelled as trusted or untrusted, EU personal, confidential, internal, or public.</p></div><div class="card"><b>02 / TRACE</b><h3>Exact provenance</h3><p>Five-token shingles and entity identifiers follow values across calls without an AI classifier in the decision loop.</p></div><div class="card"><b>03 / ENFORCE</b><h3>Hard deny or review</h3><p>GDPR transfer violations stop. Untrusted external actions pause for URL-mode human approval.</p></div></div></section>
<section class="section"><h2>Governed tool surface</h2><p class="sub">The deployed gateway exposes {len(tools)} tools through the official MCP transport.</p><div class="tools">{tool_cards}</div></section>
<div class="footer"><span>RAJA / DETERMINISTIC AI GOVERNANCE</span><span>NO LLM IN THE DECISION LOOP · <a href="/healthz">HEALTHZ</a> · <a href="/deployment/data">RUNTIME PROOF</a></span></div></div>
<script>fetch("/deployment/data",{{cache:"no-store"}}).then(r=>r.json()).then(d=>{{document.querySelector("#runtime-status").textContent=d.platform+" · "+d.region;document.querySelector("#runtime-copy").textContent=d.hostname+" · "+d.revision;document.querySelector("#runtime-tools").textContent=d.tool_count+" governed tools";document.querySelector("#runtime-mcp").textContent=d.mcp_endpoint}}).catch(()=>{{document.querySelector("#runtime-status").textContent="Runtime unavailable";document.querySelector("#runtime-copy").textContent="Retry the connection"}})</script>
</body></html>""")


app.mount("/", mcp_app)
