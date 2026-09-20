# Project: RAJA (Border control for agent data flows)

## 1. Project Mission & Core Insight
Raja is a deterministic policy gateway sitting on the MCP tool boundary. It unifies prompt injection defense and data residency by tracking data flow, not by using LLM classifiers. 
* **Core Insight:** Prompt injection (untrusted content flowing to an egress sink) and data residency violations (EU data flowing to a non-EU sink) are the same bug. 
* **Mechanism:** Raja attaches a two-axis label (`trust`, `residency`) to every value returned by a tool, tracks that value's provenance via exact-shingle matching, and evaluates outgoing tool arguments against a YAML policy engine.

## 2. Architectural Invariants (NEVER VIOLATE THESE)
* **No AI in the Decision Loop:** Policy enforcement is deterministic. Do not use LLMs to classify intent or evaluate rules. Use exact token shingling (w=5) and index intersection for taint resolution.
* **Edge vs. Cloud Split:** Raw payloads, taint indices, and the ledger live EXCLUSIVELY on the local edge (Azure Local). Only the agent's LLM calls (Azure OpenAI, Sweden Central) and redacted approval metadata (Teams) leave the edge.
* **Deny vs. Review:** Residency violations (e.g., GDPR Art. 44) result in a hard `DENY`. A human cannot override the law. Injection risks result in `REVIEW`.
* **Out-of-Band Approvals ONLY:** Do not use MCP form-mode elicitation (which agents can auto-approve). Use URL-mode MRTR elicitation (`resultType: "input_required"` with an approval URL). The agent must be structurally incapable of answering the prompt.
* **Capability Tokens, Not Grants:** Approvals generate a single-use HMAC-SHA256 token bound to the exact call hash with a 5-minute TTL. Changing one byte of the payload voids the token. HMAC alone cannot enforce single-use: maintain a server-side consumed-nonce store and reject replays even within TTL. On retry, validate the token's bound call hash against the retried call's hash before forwarding.
* **Stateless Transport, Stateful Taint:** MCP 2026-07-28 is stateless, but taint tracking is per-session stateful. Every call MUST carry `(agent_id, session_id)`. The taint index is persisted server-side keyed by `session_id`; never assume an in-memory connection survives between calls.
* **Policy Precedence (most-restrictive-wins):** When multiple rules fire, `DENY` > `REVIEW` > `ALLOW`. Evaluate all rules, collect outcomes, take the max severity, and record every fired rule in the ledger.
* **Every Rule Names Its Regulation:** `regulation` is a required field on every rule in `policy.yaml` (e.g. `GDPR Art. 44`, `NIS2 Art. 21(2)(e)`, `EU AI Act Art. 14`). Rule ids carry the article (`gdpr-art44-transfer`). The citation is copied into every ledger record and shown in the console. Loading a rule without `regulation` is a startup error.
* **Real LLM Agent in the Demo:** The demo client is a real Azure OpenAI (Sweden Central) tool-calling loop over the gateway's MCP tools. The poisoned document must actually steer the model. The scripted client (`run_attack.py`) is a regression harness for gateway tests only, never the demo. This does not contradict "No AI in the Decision Loop": the agent is the thing being governed, the gateway is what governs it.
* **MRTR Wire Format (spec-exact):** On REVIEW return `{resultType: "input_required", inputRequests: {raja_approval: {method: "elicitation/create", params: {mode: "url", url, message}}}, requestState}`. `requestState` is an opaque HMAC-signed blob `{approval_id, call_hash, exp}`. On retry the client echoes `inputResponses.raja_approval.action` and `requestState`; the gateway verifies the signature, recomputes the retried call's hash against the bound one, looks up the approval server-side, and consumes the capability token. `action: "accept"` from the client carries no authority. The capability token never transits the MCP client. `Mcp-Session-Id` is retired; `session_id`/`agent_id` are explicit handles in call arguments, which is the spec-recommended pattern.
* **Two Deterministic Taint Matchers:** (1) exact w=5 shingles with `>=3` overlap; (2) entity-level identifiers (operator names from the known list, employee IDs, emails, serials, ticket ids) extracted at ingress and indexed individually — a single identifier match inherits the source label. Plus the session-level fallback rule: once untrusted content is ingested in a session, every `egress_external` call is at least REVIEW. Semantic embeddings remain P3 and may only add labels, never remove them.

## 3. Tech Stack & Dependencies
* **Language:** Python 3.12+ (Strict typing required).
* **Protocol:** MCP (specifically the 2026-07-28 spec with stateless Multi-Round Trip Requests).
* **Teams Integration:** Power Automate Workflows webhooks + Adaptive Cards with `Action.OpenUrl`. (CRITICAL: O365 Connectors were deprecated in May 2026; do not use them).
* **UI:** Streamlit (for the local console, lineage mapping, and ledger verification). The console is P0, not polish: live decision feed, per-record lineage (sources -> labels -> rules -> decision), verify-chain button that names the broken seq.
* **Eval:** AgentDojo (ethz-spylab/agentdojo).

## 4. Directory Structure
* `/gateway/` - MCP gateway, labeller, taint resolver (shingle index), YAML policy engine, hash-chained ledger.
* `/approval/` - Out-of-band approval page (URL-mode), HMAC capability token logic, Teams webhook sender.
* `/console/` - Streamlit app for live decisions, data lineage, and ledger verification.
* `/config/` - `policy.yaml` (rules) and `tools.yaml` (manifests with data classification).
* `/eval/` - AgentDojo runner and `factory_suite.json` (12 cases).
* `/demo/` - Demo assets (e.g., poisoned `bulletin_A19.pdf`).
* `verify_ledger.py` - Standalone SHA256 chain verifier.

## 5. Coding Guidelines & AI Instructions
* **Fail Closed:** If taint resolution errors, or the ledger fails to append, the tool call must fail.
* **Ledger Formatting:** Append-only JSON. `hash = SHA256(prev_hash ‖ canonical_json(record \ {hash}))` — the `hash` field is excluded from its own input. `canonical_json` = UTF-8, sorted keys, no insignificant whitespace. Genesis `prev_hash` = 64 zero chars. Must be tamper-evident.
* **Taint Match Threshold:** A match requires a minimum overlap (default `>=3` shared w=5 shingles) to avoid false positives from common/structural tokens. Strip JSON structural tokens and a small stopword set before shingling. Record the matched span + shingle count in the decision. False positives here inflate the review rate, which is a reported metric — do not match on single incidental shingles.
* **Avoid Bloat:** Keep functions small. When modifying the Taint Store (`taint.py`), prioritize exact-shingle performance. Semantic fallback (Foundry Local embeddings) is P3 and should not block the core deterministic logic.
* **Do Not Hallucinate APIs:** Strictly follow the 2026 MCP spec for `input_required` returns.
