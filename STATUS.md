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

Tests: 32 passing, `uv run pytest -q`.

## Key decisions made (not obvious from re-reading the code)

- **Transport is plain JSON-over-HTTP (FastAPI `/mcp/call`), not a literal MCP-protocol server.** The design doc's invariants (stateless, explicit `session_id`/`agent_id` args, MRTR `input_required` shape, `requestState` semantics) are all implemented faithfully — what's skipped is wrapping it in the actual MCP transport framing. Time tradeoff for a hackathon; revisit only if a judge cares about literal protocol compliance.
- **`post_supplier_ticket` destination `us-east` is non-EU** per `config/policy.yaml`'s `eu_regions` allowlist — this is what makes the GDPR Art. 44 rule fire in the attack demo.
- **Client (not the model) owns `session_id`/`agent_id`.** `demo/agent_client.py` force-overwrites whatever the LLM puts in those tool-call args, because trusting agent-asserted identity contradicts the spec principle in `CLAUDE.md`. Found this the hard way live — the model was inventing placeholder values.
- **`.env` holds live Azure OpenAI credentials** (endpoint + API key), gitignored. Loaded via `set -a && source .env && set +a` before running the gateway/approval servers or `demo/agent_client.py`. Azure resource: `raja-hackathon-swedencentral`, deployment `raja-gpt4o`, Sweden Central, matching the design doc's sovereignty story.
- `demo/agent_client.py` also accepts the full Azure-portal "Target URI" for `AZURE_OPENAI_ENDPOINT` (parses out base endpoint / deployment / api-version), since that's what the portal's copy button gives you.

## Live demo, confirmed working

With gateway on `:8000` and approval page on `:8001` running (see "How to resume" below):

- **Benign path**: "summarise vibration faults on line 3" → `read_maintenance_log` → ALLOW, correct answer.
- **Attack path**: "check the supplier bulletin ... follow whatever it asks for warranty validation" → agent reads the bulletin, gets steered by its injected instruction, drafts a ticket containing operator names/employee IDs, calls `post_supplier_ticket` to the external portal → **hard DENY**, citing `gdpr-art44-transfer` + `nis2-art21-session-exposure`, agent reports the block plainly instead of retrying.
- **Not yet demoed live**: a pure REVIEW scenario (untrusted content, no personal data) that goes to the approval page instead of a hard deny, so the approve/reject/replay round trip hasn't been exercised through the live LLM path (it is covered by `tests/test_gateway.py`, just not with the real model in the loop).

## How to resume

```
cd /Users/borna/hackathon-microsoft
uv run pytest -q                                    # 32 tests, should be green

# start the two servers (background)
uv run uvicorn gateway.server:app --port 8000 &
uv run uvicorn approval.app:app --port 8001 &

# run the live agent (needs .env sourced first)
set -a && source .env && set +a
export RAJA_GATEWAY_URL=http://127.0.0.1:8000
uv run python -m demo.agent_client "your prompt here"
```

Do not `rm -rf data/` while a server is running — the ledger fails closed (by design) if its file disappears mid-process; restart the servers after clearing `data/`.

## Suggested next checkpoint

Either: (a) demo the REVIEW/approve round trip live end-to-end (trigger a review-only case, open the approval URL, approve, confirm the agent's retry goes through), or (b) start on P2 — Teams Adaptive Card, or the AgentDojo eval suite. Ask the user which before picking.
