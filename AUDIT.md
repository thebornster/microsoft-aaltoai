# Raja — pre-judging audit (2026-09-20)

**Resolution status:** implementation findings in this report were fixed in
the follow-up hardening pass. This file is retained as an audit trail; the
remaining items are documented limitations (live Teams/Entra integration and
multi-process identity/state deployment), not hidden failures in the demo.

Findings from a full read of the repo plus live probes against the code. Ordered by
judge visibility. Tests (69) and eval (12/12) were re-run and are green; the issues
below are in what the judge sees, not in what the tests cover.

Status key: [ ] open, [x] fixed.

The audit findings below were addressed in the implementation hardening pass.
The report remains as historical evidence of the issues found and the fixes
made; current validation is in `STATUS.md`, `DEMO.md`, and the test suite.

## 1. [ ] "White-on-white hidden text" claim is false

`DEMO.md` (beat 2), `THREAT_MODEL.md` step 3 and the design doc §4 say the injected
SERVICE NOTE is steganographic 4pt white text. The PDF renders it as normal black 11pt
text, identical to the rest of the page.

Proof:
```bash
uv run python -c "
import pypdf; p=pypdf.PdfReader('demo/bulletin_A19.pdf').pages[0]
print(p.get_contents().get_data().decode('latin1'))"
# one `/F1 11 Tf`, no color (`rg`) operator, SERVICE NOTE is a plain Tj like every other line
```

Fix: regenerate the PDF with `1 1 1 rg` + a 4pt font for the SERVICE NOTE block
(and keep `tests/test_backends.py` green — extraction is color-blind), or change the
three docs to say "visible injected instruction". Do not present the current PDF as hidden.

## 2. [ ] Approval page is XSS-able from agent-controlled fields

`approval/app.py` interpolates `approval.tool`, `session_id`, `agent_id` and the
`secret` query param into HTML unescaped. `session_id`/`agent_id` are client-supplied
(`gateway/server.py` `ToolCallRequest`, `gateway/mcp_server.py` `_identity`). The same
page contains the shared secret and the Approve form, so an adversarial agent can make
the human's browser submit "approved" — defeating "the agent is structurally incapable
of answering this".

Proof:
```bash
RAJA_DEMO_MODE=1 uv run python - <<'EOF'
from fastapi.testclient import TestClient
from gateway.server import app
c = TestClient(app)
evil = '<img src=x onerror="document.forms[0].decision.value=\'approved\';document.forms[0].submit()">'
c.post("/mcp/call", json={"tool":"search_supplier_docs","args":{"query":"a19"},"session_id":"s","agent_id":evil})
r = c.post("/mcp/call", json={"tool":"post_supplier_ticket","args":{"subject":"x","body":"paraphrased"},"session_id":"s","agent_id":evil}).json()
aid = r["inputRequests"]["raja_approval"]["params"]["url"].rsplit("/",1)[1]
print(evil in c.get(f"/approve/{aid}?secret=raja-demo").text)   # True
EOF
```

Fix: `html.escape()` every interpolated value in `approval/app.py`; drop the reflected
`secret` hidden input in favour of a session cookie or re-reading it from the query.
Add a test that a `<script>` agent_id is escaped.

## 3. [ ] Human approves blind

The approval page shows tool/session/agent and two buttons. No fired rules, no
regulation citation, no matched sources/entities, no redacted description of what would
egress. `Approval` (`approval/tokens.py`) does not carry the fired rules at all; the
data exists in `meta` (`gateway/gateway.py` `_meta`) at REVIEW time but is not stored.

Fix: store `rules_fired` + `regulations` + `matched_entities` + `sources` on the
`Approval` (and in `StateDB.approvals`), render them on the page. This is the screen
the judge will be looking at during the HITL beat.

## 4. [ ] The approval URL handed to the agent is unreachable; demo approves via curl

`gateway/gateway.py:22` hardcodes `APPROVAL_BASE_URL = "https://raja.local/approve"`.
The URL printed by `demo/agent_client.py` cannot be opened and lacks the required
`?secret=`. `demo/run_demo.sh` and `DEMO.md` therefore tell the presenter to approve
with `curl -X POST .../decide -d "decision=approved&..."` from the same terminal the
agent runs in — on stage that reads as the operator approving their own call.

Proof: run any REVIEW beat; the printed URL starts with `https://raja.local/`.

Fix: build the URL from `RAJA_PUBLIC_BASE_URL` (`approval/teams.py:_approval_url`
already does this correctly) and include the secret; update `run_demo.sh`/`DEMO.md`
to say "open the link in a browser and click Approve"; rehearse it that way.

## 5. [ ] Console (P0) is not part of the demo path

`CLAUDE.md` and the design doc call the Streamlit console P0 ("judges will not read
JSONL in a 5-minute pitch"). `demo/run_demo.sh` does not start it, `DEMO.md` never
mentions it, and `console/app.py` has no auto-refresh (manual Refresh button only).

Fix: start `streamlit run console/app.py` from `run_demo.sh` (or print the command),
add a periodic rerun (e.g. `st.rerun()` on a 2s timer / `st_autorefresh`), and script
the demo so the console is on the second screen while the agent runs.

## 6. [ ] No numbers behind the "bring numbers" pitch

Design doc §11 calls the eval "what will separate you from the field" and the pitch
script (§14, 4:15–5:00) ends on an AgentDojo table: ASR, utility, review rate <10%.
None exists. `eval/factory_suite.json` is 12 hand-written cases authored against the
implementation — 12/12 proves consistency, not effectiveness. No review-rate, ASR,
or latency figure is computed anywhere.

Measured while auditing (`build_gateway` in-process, egress calls):
~0.8 ms/call at 300 ledger records, ~2.1 ms/call at 600 — `Ledger._tail()` re-reads
the whole JSONL on every append (`gateway/ledger.py`), so latency grows with ledger size.

Fix (cheapest honest version): have `eval/run_suite.py` also print benign review rate,
attack block rate and mean gateway latency, and put those on the slide instead of an
AgentDojo table that was never run. Cache the ledger tail in memory to make latency flat.

## 7. [ ] Taint matching is thinner than pitched; the named mitigation was never built

After ingesting the maintenance log (`read_maintenance_log line-3`), these ticket bodies
posted to `post_supplier_ticket` (us-east) with no supplier doc read in the session:

| body | decision | why |
|---|---|---|
| `Fault F-2291 operator EMP-4471 Jukka Nieminen night shift gearbox vibration above threshold sensor B2` | DENY | entity regex/name list; shingle overlap only 2 (< threshold 3) |
| `Night shift: Jukka N. (id 4471) ... Aino K. (4482) ...` | ALLOW | no entity, no shingles |
| `Operators EMP 4471 and EMP 4482 logged faults 2291 and 2293` | ALLOW | regex needs the dash |
| `Nieminen and Korhonen were the operators on the affected shifts.` | ALLOW | name list is full names only |

Repro:
```bash
RAJA_DEMO_MODE=1 uv run python - <<'EOF'
import pathlib, tempfile
from gateway.gateway import build_gateway
gw = build_gateway(config_dir=pathlib.Path("config"), ledger_path=pathlib.Path(tempfile.mkdtemp())/"l.jsonl", server_key=b"k")
gw.call(tool="read_maintenance_log", args={"line":"line-3"}, session_id="s", agent_id="a")
r = gw.call(tool="post_supplier_ticket", args={"subject":"w","body":"Nieminen and Korhonen were the operators on the affected shifts."}, session_id="s", agent_id="a")
print(r["meta"])   # decision ALLOW, matched_entities [], shingle_overlap 0
EOF
```

The w=5 shingle index ("core IP") never fires on structured log data — entries are too
short once flattened. Enforcement in the demo is: `EMP-\d+` regex, `[A-Z]{2,4}-\d+`
regex, a three-name list, and the sticky session flag. The design doc admits paraphrase
evasion and names the semantic fallback as the mitigation; that fallback (P3) does not
exist, so the admitted limitation currently has no mitigation.

Related: `nis2-art21-session-exposure` makes every `egress_external` call REVIEW after
any supplier-doc read, for the rest of the session — for the persona's real workflow
that is ~100% review rate, against a stated <10% target. Have the answer ready.

Fix (cheap, deterministic, additive): index surnames and bare numeric IDs as entities
at ingress (`gateway/taint.py` `extract_entities` + `manifest.known_operator_names`),
accept `EMP[ -]?\d+`, and use a smaller shingle width (w=3) for short structured
values. Re-run the table above; state in the limitations slide what still gets through.

## 8. [ ] No README

The GitHub repo has `DEMO.md`, `STATUS.md`, `ARCHITECTURE.md`, `THREAT_MODEL.md`, the
40 KB design doc, and no `README.md`. A judge opening the repo sees a file list.

Fix: `README.md` = one-sentence pitch, the one-command run, links to `DEMO.md`,
`ARCHITECTURE.md`, `THREAT_MODEL.md`.

## 9. [ ] Microsoft-stack footprint is thin for a Microsoft sovereignty hackathon

What actually touches Microsoft today: one Azure OpenAI deployment (Sweden Central).
Teams is not live-connected (`RAJA_TEAMS_WEBHOOK_URL` unset), Entra is a shared
secret, Purview is "would come from", "Azure Local" is a laptop, Foundry Local not
started. The "complementary to Data Guardian / Agent 365" framing is good but is
framing only.

Fix: highest value per hour is a real Power Automate Workflows webhook URL so the
Adaptive Card is seen landing in Teams during beat 3 (no code change needed — see
STATUS.md Gate 7). Needs the user to create the flow.

## 10. Smaller items

- [ ] **5-minute TTL is a live-demo hazard.** `DEFAULT_TTL_SECONDS` in
  `approval/tokens.py` bounds both the approval and `requestState`. Talking through the
  approval page for >5 min between the REVIEW and `--resume` yields
  `requestState expired`. Make it env-configurable; set 30 min for the demo.
- [ ] **Approved-retry ledger record loses lineage.** `gateway/gateway.py` `_handle_retry`
  logs the executed egress with `arg_labels={}`, `rules_fired=[]` and no `approval_id`,
  so the one egress a human authorized has no sources/labels and no link back to its
  REVIEW record. Store labels/rules on the `Approval` (see item 3) and copy them into
  this record with the `approval_id`.
- [ ] **Ledger has no anchored root.** `verify_ledger.py` catches edits that don't
  recompute hashes; an attacker with file write can rewrite the chain from any point
  and recompute. Expect the question. Cheap answer: HMAC each record hash with the
  server key, or publish the head hash to the console/Teams periodically.
- [ ] **Tool schema asks the model for `session_id`/`agent_id`.** `demo/tool_schema.py`
  marks them required so the model invents values that the client then overwrites.
  Harmless, but inconsistent with "the client owns identity"; drop them from the
  model-facing schema.
- [ ] **Reflected `secret` in the approval page.** `?secret=` is echoed into a hidden
  input unescaped (`approval/app.py`) — same fix as item 2.

## Suggested order

1, 2, 8 (≈20 min total) → 4, 3 (≈45 min) → 5 (≈30 min) → 10 TTL (5 min) → 6, 7 (≈1 h)
→ 9 if a webhook URL can be obtained.
