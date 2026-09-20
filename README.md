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
