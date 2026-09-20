# Raja — architecture & data residency (slide source)

One slide's worth of content, condensed for presentation. Full detail in
`raja-design-doc.md` §6–7 and the current implementation notes in
`STATUS.md`.

## The gateway sits on the MCP tool boundary

To the agent, Raja looks like an MCP server. To the real MCP servers
(and backends), Raja looks like a client. Zero changes to the agent.

```
  Marika ──▶ Agent (any MCP client, e.g. Azure OpenAI tool-calling loop)
                       │  MCP (2026-07-28), stateless MRTR
                       ▼
   ┌─────────────────────────────────────────────────────────┐
   │  RAJA GATEWAY                          (local edge)      │
   │                                                           │
   │  ingress ─▶ LABELLER    tag every tool result:            │
   │                         trust      ∈ {trusted, untrusted} │
   │                         residency  ∈ {eu_personal,        │
   │                                        eu_confidential,   │
   │                                        internal, public}  │
   │                         provenance = source id            │
   │                              │                             │
   │                              ▼                             │
   │             TAINT STORE   per-session fingerprint index    │
   │                         (exact w=5 shingles + entity ids)  │
   │                              │                             │
   │  egress  ─▶ RESOLVER    which labelled sources does this   │
   │                         outgoing argument derive from?     │
   │                              │                             │
   │                              ▼                             │
   │             POLICY ENGINE   policy.yaml → ALLOW/DENY/REVIEW│
   │                              │                             │
   │                              ▼                             │
   │             LEDGER      hash-chained, append-only          │
   └════════════════╤══════════════════════╤═══════════════════┘
                     │ ALLOW                │ REVIEW
                     ▼                      ▼
          real MCP servers        MRTR input_required
          + Azure OpenAI           (URL-mode elicitation)
          (Sweden Central)                 │
                                            ▼
                                  human approves out-of-band
                                  → signed, single-use
                                    capability token
                                    bound to the exact call hash
```

No AI in the decision loop. Labelling, fingerprinting, taint resolution,
and policy evaluation are all deterministic — exact token shingling and
index intersection, not a classifier.

## Two transports exist side by side, honestly labeled

| | Wire format | Used by |
|---|---|---|
| `gateway/server.py`'s `/mcp/call` | Plain JSON over HTTP (FastAPI) | The demo harness — agent client, console, local fallback, most tests. Was never literal MCP; the docstring says so. |
| `gateway/mcp_server.py` + `gateway/mcp_app.py` | Real MCP: JSON-RPC over streamable HTTP, official `mcp` SDK | Proven against an independent-SDK client in `tests/test_mcp_transport.py` — `initialize`, `tools/list`, `tools/call`, the full `input_required`/retry round trip. |

Both call into the same `RajaGateway.call()` — no duplicated policy logic.

## Local edge vs. cloud split — the actual sovereignty claim

**"Data never leaves" is false and a judge will catch it.** The precise
claim:

| Stays on local edge | Leaves local edge |
|---|---|
| Raw tool payloads, prompts, PDF content | The agent's own LLM calls → Azure OpenAI, Sweden Central (EU) |
| Labelling, fingerprinting, taint resolution | Approval notifications → Teams: **redacted metadata only** (tool name, rule ids + regulation citations, session/agent ids) — never the ticket body, never the bulletin content, never operator names |
| Policy evaluation, hash-chained ledger | |
| Session taint, approvals, consumed nonces (SQLite) | |

`approval/teams.py`'s Adaptive Card payload is built from a fixed set of
fields with no call-args parameter to accidentally leak — redaction is
structural, not a filter someone could forget to apply.

## Label model

```json
{
  "source_id": "supplier_docs/bulletin_A19.pdf",
  "trust": "untrusted",
  "residency": "public",
  "ingested_at": "2026-09-20T10:04:11Z"
}
```

Two independent axes, most-restrictive-wins on merge across sources:
- **trust**: `trusted` (the user's own words, system config) vs.
  `untrusted` (anything retrieved — documents, search results,
  third-party responses)
- **residency**: `eu_personal` > `eu_confidential` > `internal` > `public`

Labels are assigned at ingress by tool-manifest declaration — the honest
hackathon approach. In production this comes from Microsoft Purview
sensitivity labels; the manifest is a stand-in for that pipeline, declared
as such rather than presented as a finished integration.

## Durable state boundary

`gateway/db.py`'s `StateDB` (SQLite, WAL mode) sits behind the in-memory
`TaintStore`/`ApprovalStore` as a write-through durability layer: session
taint, pending/decided approvals, and consumed-nonce replay guards survive
a process restart. Single-process, single-writer — correct for this
deployment's one `uvicorn` worker, explicitly not a production
multi-replica store (would need Postgres or similar to scale beyond one
process).

## Complementary to Microsoft's governance stack

Entra Agent ID / Agent 365 / Purview cover **identity and static scope**.
Raja covers **per-call data flow inside an already-allowed scope** — the
layer a confused-deputy attack lives in, by construction. Same pattern as
Data Guardian (regional human approval + tamper-evident ledger for
Microsoft engineers accessing EU data), applied one layer up to
autonomous agents.
