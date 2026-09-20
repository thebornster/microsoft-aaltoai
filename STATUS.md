# Raja — current state

Repo: https://github.com/thebornster/microsoft-aaltoai.git (pushed directly to `main`, no PRs — greenfield scaffold work, not a review cycle). Commit after every feature; keep doing that.

Full design/architecture/pitch: `raja-design-doc.md`. This file is the "where are we and what's decided" doc, written specifically so that a fresh session with zero prior context can read this one file and continue without re-deriving anything or asking clarifying questions.

**Workflow contract (standing instruction from the user, do not re-ask about this):** the user clears session context after every major checkpoint. When the user says "continue the build", read this file and proceed directly — do not ask what to do. Whenever you are about to report "P<n> is fully ready/done", assume the user will clear context right after reading your message: update this file's "NEXT ACTION" and status sections *before* giving that final summary, in the same turn, so the doc is never stale relative to what you just told the user.

## NEXT ACTION (read this first)

P0 and P1 are both fully done and fully live-demoed (see below). Nothing is broken, all tests green. The next unit of work — pick this up with no further questions unless you hit a real blocker:

1. **Start the AgentDojo eval suite** (`eval/factory_suite.json`, 12 cases: 6 benign, 6 attack) — this was flagged as the bigger differentiator vs. the Teams Adaptive Card polish item, so it's the default next step. Look at `ethz-spylab/agentdojo` for the harness shape; the 12 cases should exercise the same tool surface as the demo (`config/tools.yaml`) with variations on: benign read-only tasks, benign egress tasks, injection-via-bulletin attacks that should DENY (personal data + non-EU sink), injection attacks that should REVIEW (no personal data, session-fallback rule), and at least one multi-hop taint case (data crosses two tool calls before hitting egress).
2. Once the eval suite runs and reports a pass/fail table, do the Teams Adaptive Card / Power Automate webhook (P2, polish — the approval page alone already satisfies the HITL requirement, so this is nice-to-have, not blocking).
3. Console polish (lineage graph, residency diagram) and the real `demo/bulletin_A19.pdf` (currently a `.txt` stand-in) are lowest priority — only do these if there's time left after the eval suite and Teams card.
4. Foundry Local semantic fallback is P3 and explicitly optional — do not start it unless asked directly.

If you get here and disagree that AgentDojo should be next, say so and explain why before switching — otherwise just start it.

## Build status vs. the design doc's priority list

**P0 — all done, live-tested against the real Azure OpenAI agent:**
- `gateway/taint.py` — w=5 exact shingle index + entity-identifier matcher (employee IDs, emails, operator names)
- `gateway/policy.py` — YAML rule engine, most-restrictive-wins (DENY>REVIEW>ALLOW), fails to load if a rule lacks `regulation`
- `gateway/ledger.py` + `verify_ledger.py` — hash-chained, tamper-evident (pre-existing, untouched)
- `gateway/labeller.py`, `gateway/manifest.py`, `gateway/resolver.py` — ingress labelling, tool manifest loader, egress arg-label resolution
- `gateway/gateway.py` — full call path (label → resolve → policy → ledger), MRTR `input_required` round trip, `_handle_retry` for the resume leg
- `gateway/instance.py` — the ONE shared `RajaGateway` singleton (see "Bug found and fixed" below for why this file exists)
- `gateway/server.py` — FastAPI app; mounts both `/mcp/call` (+ `/mcp/tools`, `/healthz`) and the approval router on one process
- `approval/tokens.py` — HMAC capability tokens (single-use via server-side consumed-nonce store, 5-min TTL, bound to exact call hash)
- `approval/app.py` — out-of-band approval HTML page, exposed as an `APIRouter` (mounted by `gateway/server.py`); also has a standalone `app` for isolated testing/running alone
- `demo/agent_client.py` — real Azure OpenAI tool-calling loop over the gateway, including `--resume` mode (see below) — not the scripted stand-in the design doc warns against
- `console/app.py` — Streamlit live decision feed, per-record lineage, verify-chain button

**P1 — done:**
- Approval page + capability tokens + `requestState` round trip, INCLUDING the resume/retry leg, now live-tested (not just unit-tested)
- Session-exposure fallback rule (`nis2-art21-session-exposure` in `config/policy.yaml`)
- `verify_ledger.py`

**P2 — not started (see NEXT ACTION):**
- AgentDojo eval suite + `eval/factory_suite.json` (12 cases) — **do this next**
- Teams Adaptive Card / Power Automate Workflows webhook
- Console polish (lineage graph, residency diagram)
- Real `demo/bulletin_A19.pdf` (currently `demo/bulletin_A19.txt`, same injected payload text, no PDF-writer dependency added)

**P3 — explicitly optional, do not start unassigned:**
- Foundry Local semantic fallback

Tests: 33 passing, `uv run pytest -q`. No known failing or flaky tests.

## Key decisions made (not obvious from re-reading the code)

- **Transport is plain JSON-over-HTTP (FastAPI `/mcp/call`), not a literal MCP-protocol server.** The design doc's invariants (stateless, explicit `session_id`/`agent_id` args, MRTR `input_required` shape, `requestState` semantics) are all implemented faithfully — what's skipped is wrapping it in the actual MCP transport framing. Hackathon time tradeoff; revisit only if a judge cares about literal protocol compliance.
- **`post_supplier_ticket` destination `us-east` is non-EU** per `config/policy.yaml`'s `eu_regions` allowlist — this is what makes the GDPR Art. 44 rule fire in the attack demo.
- **Client (not the model) owns `session_id`/`agent_id`.** `demo/agent_client.py` force-overwrites whatever the LLM puts in those tool-call args (`args["session_id"] = session_id`, not `setdefault`), because trusting agent-asserted identity contradicts the "never trust client-asserted identity" principle in `CLAUDE.md`. Found this the hard way live — the model was inventing placeholder values like `"YOUR_SESSION_ID"`.
- **`.env` holds live Azure OpenAI credentials** (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`), gitignored, never committed. Loaded via `set -a && source .env && set +a` before running the gateway server or `demo/agent_client.py`. Azure resource: `raja-hackathon-swedencentral`, deployment `raja-gpt4o`, Sweden Central region — matches the design doc's sovereignty story (only the LLM call itself leaves the local edge). If `.env` is ever missing, ask the user for the credentials again rather than inventing placeholders — do not fabricate a working demo around fake creds.
- `demo/agent_client.py` accepts the full Azure-portal "Target URI" for `AZURE_OPENAI_ENDPOINT` (parses out base endpoint / deployment / api-version via `_parse_azure_endpoint`), since that's what the portal's copy button actually gives you, not a bare endpoint.
- **Gateway and approval page are ONE process, not two.** `gateway/instance.py` holds the single shared `RajaGateway`; `gateway/server.py` imports it and mounts `approval/app.py`'s `APIRouter`. Only ever start `uvicorn gateway.server:app` — do not separately start `uvicorn approval.app:app` for the live demo (that standalone `app` object exists only for isolated testing and would create a second, disconnected in-memory approval store — see "Bug found and fixed" below).
- **`demo/agent_client.py --resume`** persists pending-approval state (messages, session_id, agent_id, tool name/args, `requestState`) to `data/agent_pending.json` when a call returns `input_required`. After a human approves/rejects via the approval page, running `--resume` replays the exact call with the bound `requestState`, lets the gateway consume the single-use capability token, and feeds the real outcome back into the same conversation so the agent reports it naturally. This is real orchestration code, not a demo hack — it's the thing that makes the MRTR round trip actually work end-to-end instead of being a dead end after `input_required`.

## Bug found and fixed (previous checkpoint)

Running the gateway (`:8000`) and approval page (`:8001`) as **separate uvicorn processes** meant each imported `gateway/server.py` fresh and built its own `RajaGateway` via `build_gateway(...)` — two independent in-memory `approval_store`s. An approval created via `/mcp/call` on 8000 was invisible to `/approve` on 8001 ("unknown approval_id"). Unit tests didn't catch this because `TestClient` runs everything in one process, masking it.

Fix: extracted the singleton into `gateway/instance.py`; `approval/app.py` now exposes `router: APIRouter` (plus a standalone `app` for isolated use); `gateway/server.py` does `app.include_router(approval_router)`. One process serves both routes now. Regression test: `tests/test_server_mount.py` (drives `/mcp/call` then `/approve/{id}` through the same `TestClient(app)` instance and asserts the approval is visible).

## Live demo, confirmed working end-to-end (all three paths, live Azure OpenAI, this checkpoint)

Single process on `:8000` (see above). Exact reproduction steps are in "How to resume".

1. **Benign path**: "summarise vibration faults on line 3" → `read_maintenance_log` → ALLOW, correct answer, no policy friction.
2. **Attack path (hard DENY)**: "check the supplier bulletin ... follow whatever it asks for warranty validation" → agent reads the poisoned bulletin, gets steered by its injected instruction, drafts a ticket containing operator names/employee IDs, calls `post_supplier_ticket` to the external (`us-east`) portal → hard DENY citing `gdpr-art44-transfer` + `nis2-art21-session-exposure`. Agent reports the block plainly and does not retry on its own.
3. **REVIEW round trip (approve + resume)**: prompt asks the agent to file a ticket summarizing the bulletin *without* operator names/IDs. The paraphrased ticket body doesn't trip the exact-shingle/entity matchers (model paraphrases too much for w=5 shingle overlap ≥3), but the session-level fallback rule (`nis2-art21-session-exposure` — "untrusted content was ingested this session, so any egress_external call needs review even without a fingerprint match") still correctly fires → REVIEW, not ALLOW, not a silent bypass. Agent prints the approval URL and stops — it is structurally unable to self-approve. A human hits `POST /approve/{id}/decide` with `decision=approved`. Running `demo.agent_client --resume` replays the original call bound to that `requestState`, the gateway consumes the single-use capability token, executes the ticket, and the agent's next turn reports success. `verify_ledger.py` confirmed the full sequence stayed chain-valid throughout (spot-checked at 28 records, no breaks).

Not yet tested live: sending a *second* retry with the same already-consumed `requestState` to directly observe the anti-replay rejection through the live agent path (the anti-replay logic itself is unit-tested in `tests/test_gateway.py` — `ApprovalStore.consume` raises `TokenError` on reuse). Low priority; only chase this if a judge specifically asks to see replay protection live.

## How to resume (exact commands)

```bash
cd /Users/borna/hackathon-microsoft
uv run pytest -q                                    # 33 tests, should be green

# ONE process serves both /mcp/call and /approve/* — do not also start approval.app:app separately
uv run uvicorn gateway.server:app --port 8000 &

# live agent needs Azure OpenAI creds
set -a && source .env && set +a
export RAJA_GATEWAY_URL=http://127.0.0.1:8000
uv run python -m demo.agent_client "your prompt here"

# if the agent hits a REVIEW, the printed message includes the approval_id in its URL; approve or reject it:
curl -X POST http://127.0.0.1:8000/approve/<id>/decide -d "decision=approved&actor=EMP-4471&secret=raja-demo"
# (decision must be literally "approved" or "rejected", not "approve"/"reject")

# then let the agent complete the call and report the outcome:
uv run python -m demo.agent_client --resume

# verify the ledger any time:
uv run python verify_ledger.py
```

Gotchas:
- Do not `rm -rf data/` while the server is running — the ledger fails closed by design (`GatewayError: ledger append failed, failing closed: ...`) if its file disappears mid-process. This is correct behavior, not a bug. Kill the server first, clear `data/`, restart.
- `data/` (ledger + `agent_pending.json`) is gitignored — never expected in `git status`.
- `.env` is gitignored — never expected in `git status`; if it's missing, ask the user for Azure OpenAI credentials rather than fabricating any.
- Env vars exported via the user's own terminal (`!`-prefixed commands) do NOT propagate into a separate tool-shell process — always `source .env` explicitly in whatever shell actually runs the demo/tests.

## Commit/attribution convention used throughout

Every commit this project has used ends with:
```
Assisted-By: Claude Code
<user's name>

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: <current session URL>
```
Use whatever session URL is live in the current conversation's system reminder, not a stale one copied from this file.
