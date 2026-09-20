# Raja

Raja is a deterministic MCP policy gateway that tracks trust and data residency
from tool ingress to egress, stopping prompt injection and unlawful transfers
before they reach an external sink.

## Run the demo

```bash
./demo/run_demo.sh
```

The script starts the gateway and local Streamlit console, then prints the
commands for the live Azure OpenAI client or deterministic fallback. In demo
mode, approval links include the explicit `RAJA_DEMO_SECRET` (default
`raja-demo`); set `RAJA_PUBLIC_BASE_URL` when opening the link from another
machine. See [DEMO.md](DEMO.md), [ARCHITECTURE.md](ARCHITECTURE.md), and
[THREAT_MODEL.md](THREAT_MODEL.md).

## Deploy it

The repository includes a production-secret-aware `Dockerfile` and an Azure
Container Apps quickstart in [DEPLOY.md](DEPLOY.md). The recommended hackathon
deployment is one gateway replica in Sweden Central with HTTPS ingress and
explicit `RAJA_SERVER_KEY`, `RAJA_DEMO_SECRET`, and `RAJA_PUBLIC_BASE_URL`
settings. The current SQLite state layer is intentionally single-replica; the
deployment guide calls out the persistent-storage and scaling boundary.

The deployed gateway includes a judge-facing product surface at `/`: a
responsive overview page and a live `/dashboard` control room. The dashboard
reads only sanitized decision metadata from the gateway's hash-chained ledger,
showing ALLOW/REVIEW/DENY outcomes, blocked-versus-invoked paths, and live
ledger verification without requiring a separate frontend deployment.

The deployed site also includes an in-browser agent playground at `/agent`.
Judges can click a safe task, a poisoned-bulletin attack, or a human-approval
task and watch the browser client call the real deployed gateway step by step.
The overview and dashboard read `/deployment/data` at runtime, exposing the
live Azure Container Apps host, region, revision tag, MCP endpoint, governed
tool count, and ledger verification.

To populate that dashboard from Azure with the complete proof sequence, run:

```bash
RAJA_DEMO_SECRET='your Azure approval secret' ./demo/run_deployed_demo.sh
```

Then open the printed `/dashboard` URL. The script uses the real deployed
gateway over HTTPS; it does not bypass policy or write fabricated dashboard
data.

## Why this fits the challenge

Raja uses the manufacturing scenario from the challenge brief: a factory-floor
copilot reads on-site maintenance records and supplier documents, then may act
on a supplier portal. It demonstrates:

- **Sovereignty:** explicit local-edge processing, EU/non-EU destination policy,
  residency map, and a tamper-evident audit ledger.
- **Privacy/security technique:** deterministic exact-shingle and
  entity-identifier provenance tracking, with no AI in the enforcement loop.
- **Responsible AI:** URL-mode out-of-band human approval for ambiguous
  external actions, while GDPR transfer violations are hard-denied.
- **End-to-end proof:** benign ALLOW, poisoned-PDF DENY, REVIEW/resume,
  replay rejection, explicit `backend_invoked: false` proof for blocked calls,
  and ledger verification using the same gateway.
