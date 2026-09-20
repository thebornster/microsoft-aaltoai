# Raja — current state

Repo: https://github.com/thebornster/microsoft-aaltoai.git (pushed directly to `main`, no PRs — greenfield scaffold work, not a review cycle). Commit after every feature; keep doing that.

Full design/architecture/pitch: `raja-design-doc.md`. This file is the "where are we and what's decided" doc, written specifically so that a fresh session with zero prior context can read this one file and continue without re-deriving anything or asking clarifying questions.

**Workflow contract (standing instruction from the user, do not re-ask about this):** the user clears session context after every major checkpoint. When the user says "continue the build", read this file and proceed directly — do not ask what to do. Whenever you are about to report "P<n> is fully ready/done", assume the user will clear context right after reading your message: update this file's "NEXT ACTION" and status sections *before* giving that final summary, in the same turn, so the doc is never stale relative to what you just told the user.

## NEXT ACTION (read this first)

**The feature list is complete; the project is not yet “win-ready.”** Do not start Foundry Local or add broad new features. The next work is a short, ordered hardening program designed to remove judge-visible failure modes:

1. ~~**P0 — Demo reliability and truthful evidence.**~~ **Done this checkpoint** — see below.
2. ~~**P0 — Use the PDF as the runtime source.**~~ **Done previous checkpoint** — see below.
3. ~~**P1 — Close the protocol honesty gap.**~~ **Done this checkpoint** — see "Gate 3" section below.
4. **P1 — Make state and identity claims precise.** **← NEXT.** Keep the in-memory implementation for the demo, but add a durable state boundary (SQLite is sufficient for the hackathon) for session taint, approvals, and consumed nonces, with restart/replay tests. Derive `agent_id` from an authenticated boundary in the production-shaped path; retain client-owned IDs only in the demo adapter. Document the single-process limitation and the production migration path.
5. **P1 — Remove unsafe-looking defaults from the normal path.** Require `RAJA_SERVER_KEY` and approval authentication in production mode; fail closed when absent. Keep demo defaults only behind an explicit `RAJA_DEMO_MODE=1`, visibly labeled as demo-only. Add tests for missing-key and unauthorized-approval behavior.
6. **P1 — Strengthen judge evidence.** Add structured decision metadata to the response (`decision`, `rules_fired`, `regulations`, `sources`, `matched_entities`, `shingle_overlap`) instead of requiring consumers to parse human-readable error text. Add console tests for lineage and residency DOT generation, and a tamper test that demonstrates the exact broken sequence.
7. **P2 — Validate integrations and rehearse.** If a real Power Automate Workflows URL is available, test the Adaptive Card end to end; otherwise demonstrate the redacted payload locally and say “not live-connected.” Run the full demo from a clean shell, time it, record a fallback capture, and test the second-use rejection of a consumed requestState.
8. **P2 — Package the proof.** Add a concise judge-facing `DEMO.md` (commands, expected outputs, claims that are and are not made), a threat-model slide, an architecture/data-residency slide, and a 90-second fallback recording. Present Raja as complementary to Microsoft governance: static identity/scope is necessary; per-call provenance and destination policy close the confused-deputy gap.

**Definition of win-ready:** the judge can run one command, see the real PDF trigger a real agent decision, observe a hard legal DENY, observe an out-of-band REVIEW and exact-call retry, inspect a structured lineage record, tamper with the ledger, and reproduce the failure—without Azure/Teams credentials being the only path to evidence. Every claim in the pitch must be demonstrable or explicitly labeled as a prototype/next step.

## Build status vs. the design doc's priority list

**Gate 1 done (this checkpoint):** `demo/preflight.py` checks Python deps, config load (with regulation-citation count), PDF readability + injected-instruction presence, `data/` writability, whether the gateway is already up, and reports (non-blocking) whether Azure OpenAI and Teams webhook creds are present — exits 1 on any real failure, 0 otherwise. `demo/local_fallback.py` is a deterministic, non-LLM HTTP client that drives the real gateway (`/mcp/call`, `/approve/*`) through all four demo beats — benign ALLOW, poisoned-bulletin hard DENY, paraphrased REVIEW with human approval and exact-call resume, and a second-use replay of the same `requestState` (this is also the first live confirmation of the anti-replay rejection the STATUS doc previously flagged as unit-tested-only). `demo/run_demo.sh` is the one command: runs preflight, starts `uvicorn gateway.server:app` if not already listening on `/healthz` (waits up to 15s), detects live-agent vs. fallback mode from the Azure env vars, and prints the exact copy-pasteable commands for whichever mode applies plus the ledger-verify step. `RAJA_RESET_DEMO_STATE=1` optionally clears only `data/ledger.jsonl` and `data/agent_pending.json` (never `.env`/`config/`) before starting. New tests: `tests/test_preflight.py` covers the four pure-logic checks (dependencies, config, PDF, ledger writability) under pytest; `demo/local_fallback.py` itself was run live against the actual running gateway process and all four beats passed, `verify_ledger.py` confirmed 99 chain-valid records afterward.

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

**P2 feature work — complete; hardening remains (see NEXT ACTION):**
- Eval suite done: `eval/factory_suite.json` (12 declarative cases, 6 benign / 6 attack) + `eval/run_suite.py` (runner, prints a pass/fail table, `uv run python -m eval.run_suite`), wrapped by `tests/test_eval_suite.py` so it runs under pytest too. See "Eval suite" section below for design notes.
- Teams Adaptive Card / Power Automate Workflows webhook done: `approval/teams.py`. See "Teams notification" section below for design notes.
- Console polish done: `console/app.py` now has two tabs — "Decision feed & lineage" (per-record lineage as a graphviz DAG: source ingress calls → egress sink, colored by trust/residency, with fired rules as a dashed side-note) and "Residency map" (one node per destination region actually used across the ledger, EU-bordered vs. non-EU, colored by the worst decision that region saw). Pure-function DOT builders (`_origin_index`, `_lineage_dot`, `_residency_dot`) — no new dependency added, `st.graphviz_chart` accepts a raw DOT string directly, no `graphviz` pip package or system `dot` binary needed. Verified with a headless `streamlit run` smoke test (HTTP 200, no traceback) against the real ledger, plus a standalone script exec'ing just the function defs (no ScriptRunContext) with synthetic multi-source records to eyeball the DOT output. **Remaining hardening:** add focused pytest coverage for the pure DOT builders and the tamper-display path.
- **Gate 2 done:** `gateway/backends.py`'s `search_supplier_docs` now extracts text from `demo/bulletin_A19.pdf` via `pypdf.PdfReader` at call time — the `.txt` fixture is no longer read anywhere at runtime (only remaining reference is `tests/test_backends.py`, which moves it aside to prove the backend doesn't need it). `pypdf` was already a declared dependency (used previously only in a one-off verification script). PDF extraction differs from the `.txt` only in blank-line whitespace (single vs. double `\n` between paragraphs); the shingle tokenizer (`gateway/taint.py`'s `_WORD_RE`) is word-based and ignores whitespace, so taint matching is unaffected — confirmed by rerunning `eval/run_suite.py`, still 12/12 (both DENY cases and the REVIEW fingerprint case still fire off the PDF-extracted text). Two new tests in `tests/test_backends.py`: one renames the `.txt` aside and calls the backend to prove it doesn't need it, one asserts the returned text matches a fresh independent PDF extraction. The displayed PDF, the backend's actual input, and the narrative are now the same object.

**Gate 3 done (this checkpoint):** the literal MCP wire surface, not just the shaped-JSON `/mcp/call` endpoint. `gateway/mcp_server.py` builds a `mcp.server.lowlevel.Server` (the official `mcp` SDK, added as a real dependency, version 2.2.0) with `on_list_tools`/`on_call_tool` handlers that translate the manifest into real `types.Tool` objects and forward calls into the same `gateway.instance.gateway.call()` used everywhere else — no duplicated policy logic. The REVIEW branch returns the SDK's actual `types.InputRequiredResult` with a real `types.ElicitRequest`/`ElicitRequestURLParams` (`mode="url"`), which turned out to be a byte-for-byte match for the design doc's own MRTR wire format — the 2026-07-28 spec's `input_required`/`elicitation/create`/`requestState` shapes are exactly what this SDK version implements, not an invention of ours. `gateway/mcp_app.py` exposes this as a standalone ASGI app (`server.streamable_http_app(stateless_http=True)`) runnable via `uvicorn gateway.mcp_app:app --port 8010` — kept as a separate process from `gateway/server.py` deliberately, since the streamable-HTTP session manager owns its own ASGI lifespan and composing two lifespans under one FastAPI app buys nothing a real MCP client needs. New test `tests/test_mcp_transport.py` drives the real `mcp` SDK `Client` (an independent code path from anything we wrote) through `list_tools()`, a benign `call_tool()`, and the full REVIEW round trip: gets a real `InputRequiredResult` back, approves out-of-band via the existing `/approve/{id}/decide` HTTP route, retries with the bound `requestState` via `allow_input_required=True` and gets a real `CallToolResult`, then replays the same now-consumed `requestState` and confirms it's rejected. Uses `mcp.client._memory.InMemoryTransport` (real JSON-RPC message framing over in-memory streams, no socket) rather than a live port — fast and deterministic, and still genuine wire framing, not in-process direct dispatch (which the SDK explicitly skips JSON-RPC framing for). Manually verified `gateway/mcp_app.py` also boots for real: `uvicorn gateway.mcp_app:app --port 8010` + a raw `curl` JSON-RPC `initialize` POST to `/mcp` returned `200`.
- **`gateway/server.py`'s `/mcp/call` is unchanged and still the demo harness's control surface** (`demo/agent_client.py`, `demo/local_fallback.py`, the console, most existing tests) — it was not literally MCP-compatible before and still isn't; its docstring now says so explicitly and points to `gateway/mcp_server.py` for the real thing. No existing test or demo script needed to change.
- **Not yet wired into `demo/run_demo.sh` or the pitch/demo narrative.** The real MCP surface exists and is proven by an independent-SDK integration test, but the live demo still runs over `/mcp/call`. Revisit only if a judge specifically wants to point a real MCP client (e.g. an MCP Inspector) at the running gateway; the smallest next step would be `uvicorn gateway.mcp_app:app` alongside the main process on a second port.

**P3 — explicitly optional, do not start unassigned:**
- Foundry Local semantic fallback

Tests: 47 passing, `uv run pytest -q`. No known failing or flaky tests.

## Key decisions made (not obvious from re-reading the code)

- **Two transports now exist side by side, on purpose.** `gateway/server.py`'s `/mcp/call` is plain JSON-over-HTTP (FastAPI) — the demo harness's internal control surface, never literal MCP. `gateway/mcp_server.py` + `gateway/mcp_app.py` is the literal MCP wire protocol (JSON-RPC over streamable HTTP via the official `mcp` SDK), proven against an independent-SDK client in `tests/test_mcp_transport.py` (see "Gate 3" section below). Both call into the same `gateway.instance.gateway.call()` — no duplicated policy logic.
- **`post_supplier_ticket` destination `us-east` is non-EU** per `config/policy.yaml`'s `eu_regions` allowlist — this is what makes the GDPR Art. 44 rule fire in the attack demo.
- **Client (not the model) owns `session_id`/`agent_id`.** `demo/agent_client.py` force-overwrites whatever the LLM puts in those tool-call args (`args["session_id"] = session_id`, not `setdefault`), because trusting agent-asserted identity contradicts the "never trust client-asserted identity" principle in `CLAUDE.md`. Found this the hard way live — the model was inventing placeholder values like `"YOUR_SESSION_ID"`.
- **`.env` holds live Azure OpenAI credentials** (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`), gitignored, never committed. Loaded via `set -a && source .env && set +a` before running the gateway server or `demo/agent_client.py`. Azure resource: `raja-hackathon-swedencentral`, deployment `raja-gpt4o`, Sweden Central region — matches the design doc's sovereignty story (only the LLM call itself leaves the local edge). If `.env` is ever missing, ask the user for the credentials again rather than inventing placeholders — do not fabricate a working demo around fake creds.
- `demo/agent_client.py` accepts the full Azure-portal "Target URI" for `AZURE_OPENAI_ENDPOINT` (parses out base endpoint / deployment / api-version via `_parse_azure_endpoint`), since that's what the portal's copy button actually gives you, not a bare endpoint.
- **Gateway and approval page are ONE process, not two.** `gateway/instance.py` holds the single shared `RajaGateway`; `gateway/server.py` imports it and mounts `approval/app.py`'s `APIRouter`. Only ever start `uvicorn gateway.server:app` — do not separately start `uvicorn approval.app:app` for the live demo (that standalone `app` object exists only for isolated testing and would create a second, disconnected in-memory approval store — see "Bug found and fixed" below).
- **`demo/agent_client.py --resume`** persists pending-approval state (messages, session_id, agent_id, tool name/args, `requestState`) to `data/agent_pending.json` when a call returns `input_required`. After a human approves/rejects via the approval page, running `--resume` replays the exact call with the bound `requestState`, lets the gateway consume the single-use capability token, and feeds the real outcome back into the same conversation so the agent reports it naturally. This is real orchestration code, not a demo hack — it's the thing that makes the MRTR round trip actually work end-to-end instead of being a dead end after `input_required`.

## Eval suite

- **Scripted against `gateway.call()` directly, not through the LLM.** Per the design doc's own distinction ("the scripted client is a gateway regression harness, never the demo"), the eval suite is that harness formalized: `eval/factory_suite.json` declares 12 cases (tool + args steps, expected final decision, optionally expected fired-rule ids or an error substring), `eval/run_suite.py` replays each case's steps through a fresh `RajaGateway` (isolated tmp ledger + session per case) and classifies the final response as ALLOW/REVIEW/DENY/ERROR. No AgentDojo package dependency was added — the 2026 AgentDojo harness shape (declarative task suite, benign vs. attack split, pass/fail table) was borrowed, not the library itself, since the gateway's decision logic is deterministic and framework-agnostic already (see `gateway/gateway.py`'s own docstring). Revisit only if a judge specifically wants literal `ethz-spylab/agentdojo` integration.
- **12 cases, 6 benign / 6 attack, all passing:** benign covers plain read-only calls, an untainted egress (internal and external), trusted eu_personal data flowing to an internal EU sink (allowed — only non-EU destinations are restricted), and untrusted content ingested but egressed only internally (session-fallback rule is scoped to `egress_external` only, confirmed here). Attack covers: injected-bulletin narrative producing a hard DENY (`a1`), the same DENY with no injection framing at all — pure data exfil (`a2`, isolates `gdpr-art44-transfer` alone), a verbatim bulletin span tripping the exact-shingle matcher into REVIEW (`a3`), a paraphrased ticket that dodges both matchers but still gets caught by the session-exposure fallback rule (`a4` — the same scenario that was live-demoed), a multi-hop case where untrusted bulletin text and eu_personal log data are ingested via two separate prior calls and combined in a third call's egress (`a5` — the only case that exercises `aiact-art14-cross-source`, though it's always dominated by the DENY-severity `gdpr-art44-transfer` once eu_personal residency is involved, since the manifest has no residency tier between `public` and `eu_personal` — noted as an observation, not something to fix), and a capability-token tamper test where a retry swaps in different args than the ones bound to `requestState` (`a6` — confirms the hash-mismatch check runs before the approval-state check, so tampering is rejected structurally, not just by convention).
- **`rules_fired` / `error_contains` assertions are substring checks against the response text**, not a structured field — the gateway's DENY/REVIEW responses embed fired rule ids in the human-readable `error`/`message` string (`gateway/gateway.py`'s `fired_desc`/`fired` construction), there's no separate machine-readable rules array on the wire. Fine for a regression harness; would need a real field if this ever needs to be machine-consumed by something other than this suite.

## Teams notification

- **`approval/teams.py` is a best-effort side-notification, not part of the HITL gate.** The approval page (`/approve/{id}`) is still the actual authority — REVIEW/DENY/ALLOW is decided there regardless of whether Teams delivery succeeds. `notify_review()` catches its own `httpx.HTTPError` and logs a warning rather than raising, and the hook that calls it in `gateway/gateway.py`'s REVIEW branch wraps the call in a bare `try/except Exception` too, so a Teams outage can never turn into a blocked gateway call. This matches the design doc's own P2 framing: "the approval page alone already satisfies the HITL requirement."
- **Wired as an optional constructor attribute (`RajaGateway.on_review`), not hardcoded into `gateway.py`.** `build_gateway()`'s signature is unchanged; `gateway/instance.py` sets `gateway.on_review = notify_review` after construction. This keeps `gateway/gateway.py` framework-agnostic and free of any HTTP-side-effect dependency in its default state — every test that calls `build_gateway()` directly (all of `tests/test_gateway.py`, `eval/run_suite.py`) gets `on_review=None` and fires no network calls at all. Only the live server (`gateway/server.py` → `gateway/instance.py`) has it wired in.
- **Redacted by construction, not by a filter.** `notify_review()`'s signature only takes `approval_id, tool, session_id, agent_id, fired_rules` — there is no call-args/payload parameter to accidentally leak, so the Adaptive Card can't carry raw body content even by mistake. Matches the design doc's edge/cloud split: only metadata crosses to Teams, the payload stays on the local edge.
- **No O365 Connector, no MessageCard.** Posts a plain Adaptive Card (`type: AdaptiveCard`, schema 1.5) with a single `Action.OpenUrl` action pointing at the approval page, inside the Workflows-expected envelope (`{"type": "message", "attachments": [...]}`), per the design doc's note that O365 Connectors were disabled May 2026 and that interactive buttons don't render for MessageCard via Workflows.
- **Approval URL is assembled inside `approval/teams.py`, not passed in from `gateway.py`.** `RAJA_PUBLIC_BASE_URL` (default `http://127.0.0.1:8000`) + `RAJA_DEMO_SECRET` (default `raja-demo`, same default `approval/app.py` already uses) are read at call time (not import time, so tests can `monkeypatch.setenv` per-test) and combined into a clickable `.../approve/{id}?secret=...` URL — this keeps secret-handling entirely inside the approval layer rather than spreading it into the policy/gateway core.
- **Not live-tested against a real Power Automate Workflows webhook** — `RAJA_TEAMS_WEBHOOK_URL` is unset in this environment, so `notify_review()` no-ops (logs and returns) on every real REVIEW in the live demo today. Unit tests mock `httpx.post` to verify the card shape, redaction, and non-blocking-failure behavior. If a judge wants to see the live card, you'll need a real Workflows webhook URL from the user first — do not fabricate one.

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

For judging day, prefer the one-command path: `./demo/run_demo.sh` (preflight + start gateway if needed + print the exact next commands for whichever mode — live agent or local fallback — is available). `RAJA_RESET_DEMO_STATE=1 ./demo/run_demo.sh` also clears `data/ledger.jsonl`/`data/agent_pending.json` first. If Azure creds aren't set, run `uv run python -m demo.local_fallback` directly — it reproduces all four narrative beats over the real gateway HTTP surface with no LLM involved.

For development/manual control:

```bash
cd /Users/borna/hackathon-microsoft
uv run pytest -q                                    # 46 tests, should be green
uv run python -m eval.run_suite                     # eval suite pass/fail table (12/12 should pass)

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
