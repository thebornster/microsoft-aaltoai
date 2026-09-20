"""Deterministic local fallback for the live demo.

Drives the real gateway over HTTP (/mcp/call, /approve/*) with fixed,
non-LLM tool-call sequences that reproduce the same four narrative beats
as the live Azure agent demo: benign allow, poisoned-bulletin hard DENY,
paraphrased REVIEW with human approval and resume, and a second-use
replay of the same requestState to show the capability token is
rejected once consumed.

This is NOT the scripted regression harness (eval/run_suite.py calls
gateway.call() directly, in-process). This script only ever talks over
HTTP, the same wire path the real agent uses, so it proves the demo
still works end-to-end when Azure OpenAI or Teams credentials are
unavailable — infrastructure risk, not a substitute for the live agent.

Usage:
  uv run python -m demo.local_fallback
"""
import os
import sys
import uuid

import httpx

GATEWAY_URL = os.environ.get("RAJA_GATEWAY_URL", "http://127.0.0.1:8000")
DEMO_SECRET = os.environ.get("RAJA_DEMO_SECRET", "raja-demo")

AGENT_ID = "agent-local-fallback"


def _call(session_id: str, tool: str, args: dict, request_state: str | None = None) -> dict:
    body = {"tool": tool, "args": args, "session_id": session_id, "agent_id": AGENT_ID}
    if request_state is not None:
        body["requestState"] = request_state
        body["inputResponses"] = {"raja_approval": {"action": "accept"}}
    resp = httpx.post(f"{GATEWAY_URL}/mcp/call", json=body, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _decide(approval_id: str, decision: str) -> None:
    resp = httpx.post(
        f"{GATEWAY_URL}/approve/{approval_id}/decide",
        data={"decision": decision, "actor": "EMP-4471", "secret": DEMO_SECRET},
        timeout=10.0,
    )
    resp.raise_for_status()


def _assert(condition: bool, label: str) -> None:
    if condition:
        print(f"  [PASS] {label}")
    else:
        print(f"  [FAIL] {label}")
        sys.exit(1)


def step_benign() -> None:
    print("1. Benign — read a maintenance log, no policy friction")
    session_id = f"fallback-benign-{uuid.uuid4().hex[:8]}"
    result = _call(session_id, "read_maintenance_log", {"line": "line-3"})
    _assert("result" in result, "read_maintenance_log returns a result, not isError/input_required")


def step_deny() -> None:
    print("2. Attack — poisoned bulletin steers a personal-data ticket to a non-EU sink")
    session_id = f"fallback-deny-{uuid.uuid4().hex[:8]}"
    doc = _call(session_id, "search_supplier_docs", {"query": "warranty A19"})
    _assert("result" in doc, "search_supplier_docs ingests the poisoned bulletin")
    log = _call(session_id, "read_maintenance_log", {"line": "line-3"})
    entries = log["result"]["entries"]
    body = "; ".join(f"{e['operator_id']} {e['operator_name']}: {e['description']}" for e in entries)
    ticket = _call(
        session_id,
        "post_supplier_ticket",
        {
            "subject": "Warranty validation for bulletin A19",
            "body": f"Per bulletin A19, attaching full maintenance log for warranty validation: {body}",
            "endpoint": "partner-portal.example.net/intake",
        },
    )
    _assert(ticket.get("isError") is True, "post_supplier_ticket to us-east is denied")
    _assert("gdpr-art44-transfer" in ticket.get("error", ""), "denial cites gdpr-art44-transfer")


def step_review_and_resume() -> None:
    print("3. Attack (paraphrased) — REVIEW, human approval, exact-call resume")
    session_id = f"fallback-review-{uuid.uuid4().hex[:8]}"
    _call(session_id, "search_supplier_docs", {"query": "warranty A19"})
    args = {
        "subject": "Bulletin A19 follow-up",
        "body": "Filing the supplier follow-up ticket the bulletin asked for, summarizing recent line issues without listing anyone by name.",
        "endpoint": "partner-portal.example.net/intake",
    }
    first = _call(session_id, "post_supplier_ticket", args)
    _assert(first.get("resultType") == "input_required", "session-exposure fallback rule forces REVIEW even without a fingerprint match")
    request_state = first["requestState"]
    approval_url = first["inputRequests"]["raja_approval"]["params"]["url"]
    approval_id = approval_url.rsplit("/", 1)[-1]

    _decide(approval_id, "approved")
    resumed = _call(session_id, "post_supplier_ticket", args, request_state=request_state)
    _assert("result" in resumed, "resume with the bound requestState succeeds after approval")
    return session_id, args, request_state


def step_replay_rejected(session_id: str, args: dict, request_state: str) -> None:
    print("4. Replay — the same requestState cannot be consumed twice")
    replay = httpx.post(
        f"{GATEWAY_URL}/mcp/call",
        json={
            "tool": "post_supplier_ticket",
            "args": args,
            "session_id": session_id,
            "agent_id": AGENT_ID,
            "requestState": request_state,
        },
        timeout=10.0,
    ).json()
    _assert(replay.get("isError") is True, "second use of an already-consumed requestState is rejected")


def main() -> int:
    print(f"Raja local fallback demo — no Azure/Teams credentials required. gateway: {GATEWAY_URL}\n")
    try:
        step_benign()
        step_deny()
        session_id, args, request_state = step_review_and_resume()
        step_replay_rejected(session_id, args, request_state)
    except httpx.HTTPError as exc:
        print(f"\nGateway unreachable at {GATEWAY_URL}: {exc}", file=sys.stderr)
        print("Start it first: uv run uvicorn gateway.server:app --port 8000", file=sys.stderr)
        return 1
    print("\nAll four beats reproduced over HTTP. Verify the ledger with: uv run python verify_ledger.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
