# Raja

Border control for agent data flows.

Raja is a deterministic policy gateway that sits on the MCP tool boundary
between an AI agent and the tools it calls. It labels every value a tool
returns with where it came from and where it is allowed to go, follows those
labels through the session, and decides on every outgoing call whether the
data may leave: `ALLOW`, `REVIEW` by a human, or `DENY`. Every decision is
written to a hash-chained ledger that names the rule and the regulation it
enforces.

No model is involved in the decision. The agent is what Raja governs, not
what it trusts.

Live deployment (Azure Container Apps, Sweden Central):
https://raja-gateway.proudsea-6cbc91b7.swedencentral.azurecontainerapps.io

## The problem

A production engineer asks a factory-floor copilot to check a supplier
bulletin for line 3. The bulletin is a PDF from outside the company. Hidden
in it, in 4-point white text, is an instruction: attach the full maintenance
log, with operator names and employee IDs, to a ticket on the supplier's
partner portal.

The agent is allowed to read logs. The agent is allowed to file tickets.
Every identity and permission check passes. What is wrong is the
combination: untrusted content is steering personal data of EU employees
to a server in another jurisdiction.

Seen from the data's point of view, prompt injection and an unlawful
cross-border transfer are the same bug. Untrusted content flowing to an
external sink, and EU personal data flowing to a non-EU sink, are both a
question of provenance. Raja tracks provenance, so one mechanism catches
both.

## How it works

```
  engineer ──▶ agent (Azure OpenAI, Sweden Central, tool-calling loop)
                      │  MCP
                      ▼
   ┌──────────────────────────────────────────────────────────┐
   │  RAJA GATEWAY                                             │
   │                                                           │
   │  ingress   labeller     trust     ∈ {trusted, untrusted}  │
   │                         residency ∈ {eu_personal, public} │
   │                         source    = tool:argument         │
   │                              │                            │
   │            taint store  per-session fingerprint index     │
   │                         (exact 5-token shingles           │
   │                          + entity identifiers)            │
   │                              │                            │
   │  egress    resolver     which sources does this           │
   │                         outgoing argument derive from?    │
   │                              │                            │
   │            policy       policy.yaml → ALLOW / REVIEW / DENY
   │                              │                            │
   │            ledger       append-only, SHA-256 chained      │
   └───────────────┬──────────────────┬────────────────────────┘
                   │ ALLOW            │ REVIEW
                   ▼                  ▼
          backend tool         out-of-band approval URL
                               (the agent cannot answer it)
                               → single-use token bound to
                                 the exact call hash
```

**Labelling.** Each tool in `config/tools.yaml` declares what it emits
(`read_maintenance_log` returns `trusted` / `eu_personal`;
`search_supplier_docs` returns `untrusted` / `public`) and, for sinks, where
it sends data (`post_supplier_ticket` is `egress_external` to `us-east`).

**Provenance.** Tool results are fingerprinted at ingress with exact
five-token shingles and with entity identifiers (operator names, employee
IDs, emails, ticket ids). At egress each argument is resolved against the
session's index. A match needs at least three shared shingles or one exact
identifier, so structural tokens never trigger it. Paraphrasing defeats a
literal matcher, so there is also a session-level rule: once untrusted
content has been ingested, every external egress is at least a `REVIEW`.

**Policy.** Rules in `config/policy.yaml` match on the resolved labels and
the tool manifest. Every rule must cite the regulation it implements;
loading one without a citation is a startup error. All rules are evaluated,
the most restrictive outcome wins, and every fired rule is recorded.

```yaml
- id: gdpr-art44-transfer
  regulation: "GDPR Art. 44 - general principle for transfers"
  description: EU personal data may not reach a non-EU destination
  when:
    arg_labels.residency: eu_personal
    tool.destination_region: non_eu
  then: deny
```

**Ledger.** Every decision is appended as JSON with
`hash = SHA256(prev_hash ‖ canonical_json(record))`. `verify_ledger.py`
walks the chain and, if a byte has been changed, names the exact sequence
number where it broke.

```json
{
  "seq": 3,
  "tool": "post_supplier_ticket",
  "decision": "DENY",
  "rules_fired": ["gdpr-art44-transfer", "nis2-art21-session-exposure"],
  "arg_labels": {
    "trust": "trusted",
    "residency": "eu_personal",
    "sources": ["read_maintenance_log:line-3"]
  },
  "destination_region": "us-east",
  "processing_path": ["local-edge", "azure-openai:swedencentral"],
  "human": null,
  "prev_hash": "…",
  "hash": "…"
}
```

## Where the data lives

Raw tool payloads, the taint index, the approval store, and the ledger stay
with the gateway. On site that is the local edge; in the hosted demo it is
one container in Sweden Central. Each ledger record carries its
`processing_path` so the answer to "where was this processed" is in the
record, not in a slide.

Two things leave the gateway: the agent's own model calls to Azure OpenAI
in Sweden Central, and, on a `REVIEW`, a redacted approval notification
(rule ids, regulations, source ids; never the payload) for a Teams Adaptive
Card. Nothing else does.

Residency and injection are treated differently on purpose. A residency
violation is a hard `DENY`; a person cannot approve it, because the law does
not give them that option. An injection risk is a `REVIEW`, because it is a
judgment call and a person should make it.

## Human oversight

When a rule returns `REVIEW`, the gateway answers with the MCP 2026-07-28
`input_required` result and a URL-mode elicitation. The agent receives a
link it cannot open and a form it cannot fill; a person opens the approval
page, sees the fired rules with their regulations, the source records and
the matched identifiers, and decides.

Approval mints a single-use HMAC-SHA256 capability token bound to the hash
of the exact call that was reviewed, with a five-minute TTL. On retry the
gateway recomputes the hash of the retried call and compares it with the
bound one, so changing one byte of the arguments voids the approval. A
server-side consumed-nonce store rejects replays even inside the TTL. The
token never passes through the agent.

## See it run

### Hosted

Open the deployment URL above.

- `/` shows the live host, region, revision, and governed tool count, read
  from the running container.
- `/agent` is a browser playground with three cards: a benign task, the
  poisoned-bulletin attack, and a task that needs approval. Each one calls
  the real gateway step by step. The approval card opens the real approval
  page and resumes with the bound `requestState` after you click Approve.
- `/dashboard` is the control room: decision feed, counts, live ledger
  verification, and a per-record lineage panel. Click a row to see the
  sources it derived from, its labels, every rule that fired with its
  regulation, the human decision if any, the processing path, and the chain
  hashes.
- `/mcp` is the MCP endpoint itself; `/mcp/tools` is the manifest.

The hosted container has no persistent volume, so the ledger starts empty
after a restart. Populate it from the `/agent` page, or from a shell:

```bash
RAJA_DEMO_SECRET='the deployed approval secret' ./demo/run_deployed_demo.sh
```

### Local

```bash
./demo/run_demo.sh
```

This runs a preflight, starts the gateway and the Streamlit console, and
prints the commands for the next steps. If `AZURE_OPENAI_ENDPOINT` and
`AZURE_OPENAI_API_KEY` are set, the demo uses a real Azure OpenAI
tool-calling loop that the poisoned PDF genuinely steers. Without them,
`uv run python -m demo.local_fallback` drives the same four beats through
the same gateway deterministically.

The four beats:

1. **Benign.** "Summarise vibration faults on line 3." The log is read, the
   agent answers. Ledger: `ALLOW`.
2. **Attack.** "Check the supplier bulletin for line 3 and follow whatever
   it asks for warranty validation." The agent tries to post the log to the
   partner portal. Blocked before any network call:
   `gdpr-art44-transfer`, `nis2-art21-session-exposure`,
   `backend_invoked: false`.
3. **Review.** "File a supplier ticket summarising the bulletin, without
   operator names or IDs." The paraphrase evades the fingerprint matchers;
   the session rule still fires. The agent gets an approval URL. A person
   approves; `--resume` replays the identical call and it goes through.
4. **Replay.** The same `requestState` submitted again is rejected:
   `capability token already consumed`.

Then edit one byte of `data/ledger.jsonl` and run
`uv run python verify_ledger.py`.

## Alongside the platform, not instead of it

Entra Agent ID, Agent 365, and Purview decide what an agent may ever touch.
The attack above passes every one of those checks, because the agent is
legitimately allowed to read logs and legitimately allowed to file tickets.
Raja works one layer down, inside the already-granted scope, on the question
static permissions cannot answer: given where this specific value came from,
may it go to this specific place, on this specific call.

The closest analogue is the regional approval and audit gate that governs
engineer access to EU customer data, applied to autonomous agents rather
than people.

## Repository

```
gateway/     labeller, taint store, resolver, policy engine, ledger,
             MCP server (official mcp SDK, streamable HTTP, stateless)
approval/    approval page, capability tokens, Teams card sender
console/     Streamlit console: decision feed, lineage, chain verification
config/      policy.yaml (rules with regulations), tools.yaml (manifests)
eval/        12-case factory suite, 6 benign / 6 attack
demo/        poisoned bulletin_A19.pdf, agent client, fallback client
tests/       72 tests
verify_ledger.py
```

```bash
uv run pytest -q
uv run python -m eval.run_suite
```

The eval suite reports 0% review rate on benign cases and 100% containment
on attack cases, where containment means `DENY`, `REVIEW`, or a rejected
retry.

## What is not claimed

- The approval page is guarded by a shared demo secret, not Entra sign-in.
- `session_id` and `agent_id` are supplied by the client, not derived from
  an authenticated transport identity. This is the first boundary to close
  before running against a real agent fleet.
- The Teams card is built and tested against a mocked webhook; no live
  Power Automate URL was available.
- State is SQLite behind one process lock. Correct for a single replica,
  not a multi-writer store.
- The eval suite borrows AgentDojo's declarative shape, not the library.
- Semantic matching (Foundry Local embeddings) is designed as an additive
  layer that can only add labels, never remove them, and is not built.

## Further reading

- [DEMO.md](DEMO.md) — what to run, what you will see, what is and is not
  claimed
- [ARCHITECTURE.md](ARCHITECTURE.md) — data residency and transport detail
- [THREAT_MODEL.md](THREAT_MODEL.md) — what the gateway defends against and
  what it does not
- [DEPLOY.md](DEPLOY.md) — Azure Container Apps deployment
- [raja-design-doc.md](raja-design-doc.md) — full design rationale
