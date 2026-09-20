# Raja — current state

Repo: https://github.com/thebornster/microsoft-aaltoai.git (pushed directly to `main`, no PRs yet — this is greenfield scaffold work, not a review cycle). Commit after every feature; keep doing that.

Full design/architecture/pitch: `raja-design-doc.md`. This file is just "where are we and what's decided" so a fresh session doesn't have to re-derive it.

## Build status vs. the design doc's priority list

**P0 — all done and live-tested:**
- `gateway/taint.py` — w=5 exact shingle index + entity-identifier matcher (employee IDs, emails, operator names)
- `gateway/policy.py` — YAML rule engine, most-restrictive-wins (DENY>REVIEW>ALLOW), fails to load if a rule lacks `regulation`
- `gateway/ledger.py` + `verify_ledger.py` — hash-chained, tamper-evident (pre-existing, untouched)
- `gateway/labeller.py`, `gateway/manifest.py`, `gateway/resolver.py` — ingress labelling, tool manifest loader, egress arg-label resolution
- `gateway/gateway.py` + `gateway/server.py` — full call path (label → resolve → policy → ledger), MRTR `input_required` round trip, stateless HTTP (`session_id`/`agent_id` as explicit args, no `Mcp-Session-Id`)
- `approval/tokens.py` + `approval/app.py` — HMAC capability tokens (single-use via server-side consumed-nonce store, 5-min TTL, bound to call hash), out-of-band approval page
- `demo/agent_client.py` — **real** Azure OpenAI tool-calling loop over the gateway (not the scripted stand-in the design doc warns against)
- `console/app.py` — Streamlit live decision feed, per-record lineage, verify-chain button
- Live benign path and live attack path both run end-to-end successfully (see "Live demo, confirmed working" below)

**P1 — done:**
- Approval page + capability tokens + requestState round trip (above)
- Session-exposure fallback rule (`nis2-art21-session-exposure` in `config/policy.yaml`)
- `verify_ledger.py` (was already scaffolded)

**P1/P2 — not started:**
- Teams Adaptive Card / Power Automate Workflows webhook (P2 — polish, approval page alone satisfies HITL criterion)
- AgentDojo eval + `eval/factory_suite.json` 12-case suite (P2 — big differentiator, do after demo is solid)
- Console polish (lineage graph, residency diagram) (P2)
- Real `demo/bulletin_A19.pdf` — currently a plain-text stand-in at `demo/bulletin_A19.txt` with the same injected payload text; no PDF-writer dependency added yet
- Foundry Local semantic fallback (P3, explicitly optional)

Tests: 33 passing, `uv run pytest -q`.

## Key decisions made (not obvious from re-reading the code)

- **Transport is plain JSON-over-HTTP (FastAPI `/mcp/call`), not a literal MCP-protocol server.** The design doc's invariants (stateless, explicit `session_id`/`agent_id` args, MRTR `input_required` shape, `requestState` semantics) are all implemented faithfully — what's skipped is wrapping it in the actual MCP transport framing. Time tradeoff for a hackathon; revisit only if a judge cares about literal protocol compliance.
- **`post_supplier_ticket` destination `us-east` is non-EU** per `config/policy.yaml`'s `eu_regions` allowlist — this is what makes the GDPR Art. 44 rule fire in the attack demo.
- **Client (not the model) owns `session_id`/`agent_id`.** `demo/agent_client.py` force-overwrites whatever the LLM puts in those tool-call args, because trusting agent-asserted identity contradicts the spec principle in `CLAUDE.md`. Found this the hard way live — the model was inventing placeholder values.
- **`.env` holds live Azure OpenAI credentials** (endpoint + API key), gitignored. Loaded via `set -a && source .env && set +a` before running the gateway/approval servers or `demo/agent_client.py`. Azure resource: `raja-hackathon-swedencentral`, deployment `raja-gpt4o`, Sweden Central, matching the design doc's sovereignty story.
- `demo/agent_client.py` also accepts the full Azure-portal "Target URI" for `AZURE_OPENAI_ENDPOINT` (parses out base endpoint / deployment / api-version), since that's what the portal's copy button gives you.

## Live demo, confirmed working

Gateway and approval page are now ONE process on `:8000` (see "Key decisions" below for why — this changed this checkpoint). Start it per "How to resume".

- **Benign path**: "summarise vibration faults on line 3" → `read_maintenance_log` → ALLOW, correct answer.
- **Attack path**: "check the supplier bulletin ... follow whatever it asks for warranty validation" → agent reads the bulletin, gets steered by its injected instruction, drafts a ticket containing operator names/employee IDs, calls `post_supplier_ticket` to the external portal → **hard DENY**, citing `gdpr-art44-transfer` + `nis2-art21-session-exposure`, agent reports the block plainly instead of retrying.
- **REVIEW round trip — now demoed live end-to-end**: prompt asks the agent to file a ticket summarizing the bulletin *without* operator names/IDs. Shingle/entity match on the paraphrased body doesn't fire (model paraphrases too much), but the session-level fallback (`nis2-art21-session-exposure`) correctly still catches it since untrusted content was ingested this session → REVIEW, not ALLOW. Agent prints the approval URL and stops (does not self-approve). Human approves via `POST /approve/{id}/decide` (or the HTML form). Running `python -m demo.agent_client --resume` replays the exact original call with the bound `requestState`, the gateway consumes the single-use capability token, executes the ticket, and the agent reports success. Ledger + `verify_ledger.py` confirmed clean across the whole sequence (28 records, chain OK).

## Bug found and fixed this checkpoint

Gateway (`:8000`) and approval page (`:8001`) as **separate uvicorn processes** each built their own `RajaGateway` singleton (`build_gateway(...)` ran once per process) — so an approval created via `/mcp/call` on 8000 was invisible to `/approve` on 8001 ("unknown approval_id"). Found by actually running the REVIEW round trip live, not by unit tests (they used `TestClient` in one process, which masked it).

Fix: `gateway/instance.py` now holds the one shared `RajaGateway`; `approval/app.py` exposes an `APIRouter` (plus a standalone `app` for isolated testing); `gateway/server.py` mounts that router. One `uvicorn gateway.server:app` process now serves both `/mcp/call` and `/approve/*`. Regression test: `tests/test_server_mount.py`.

## How to resume

```
cd /Users/borna/hackathon-microsoft
uv run pytest -q                                    # 33 tests, should be green

# one process now serves both /mcp/call and /approve/*
uv run uvicorn gateway.server:app --port 8000 &

# run the live agent (needs .env sourced first)
set -a && source .env && set +a
export RAJA_GATEWAY_URL=http://127.0.0.1:8000
uv run python -m demo.agent_client "your prompt here"

# if the agent hits a REVIEW, approve/reject it (approval_id is in the printed URL):
curl -X POST http://127.0.0.1:8000/approve/<id>/decide -d "decision=approved&actor=EMP-4471&secret=raja-demo"
# then let the agent complete the call:
uv run python -m demo.agent_client --resume
```

Do not `rm -rf data/` while the server is running — the ledger fails closed (by design) if its file disappears mid-process; restart the server after clearing `data/`.

## Suggested next checkpoint

P0/P1 are now fully done and fully live-demoed (benign, hard-deny attack, and REVIEW/approve/resume round trip). Next is P2: Teams Adaptive Card / Power Automate webhook, or the AgentDojo eval suite (`eval/factory_suite.json`, 12 cases). Ask the user which before picking.
