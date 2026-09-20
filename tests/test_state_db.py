"""Gate 4: session taint, approvals, and consumed nonces survive a process
restart when a state_db_path is configured (gateway/db.py). Simulates a
restart by building a second, independent RajaGateway against the same
SQLite file — a fresh instance has empty in-memory dicts, exactly like a
freshly started uvicorn process would.
"""
import pathlib

import pytest

from approval.tokens import TokenError
from gateway.gateway import build_gateway

SESSION = "s_restart_test"
AGENT = "agent-restart-test"
CONFIG_DIR = pathlib.Path(__file__).parent.parent / "config"


def _build(tmp_path, ledger_name="ledger.jsonl"):
    return build_gateway(
        config_dir=CONFIG_DIR,
        ledger_path=tmp_path / ledger_name,
        server_key=b"test-key",
        state_db_path=tmp_path / "state.db",
    )


def test_session_taint_survives_restart_and_still_triggers_review(tmp_path):
    gw1 = _build(tmp_path)

    ingest = gw1.call(
        tool="search_supplier_docs",
        args={"query": "bulletin", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    assert "result" in ingest

    # "restart": a brand-new gateway/process, same db file, no shared memory
    gw2 = _build(tmp_path)
    assert SESSION not in gw2.sessions

    ticket = gw2.call(
        tool="post_supplier_ticket",
        args={
            "subject": "warranty",
            "body": "a paraphrased ticket with no fingerprint overlap at all",
            "endpoint": "partner-portal.example.net/intake",
            "session_id": SESSION,
            "agent_id": AGENT,
        },
        session_id=SESSION,
        agent_id=AGENT,
    )
    assert ticket.get("resultType") == "input_required"


def test_approval_and_replay_rejection_survive_restart(tmp_path):
    gw1 = _build(tmp_path)

    gw1.call(
        tool="search_supplier_docs",
        args={"query": "bulletin", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    args = {
        "subject": "warranty",
        "body": "a paraphrased ticket with no fingerprint overlap at all",
        "endpoint": "partner-portal.example.net/intake",
        "session_id": SESSION,
        "agent_id": AGENT,
    }
    review = gw1.call(tool="post_supplier_ticket", args=args, session_id=SESSION, agent_id=AGENT)
    approval_id = review["inputRequests"]["raja_approval"]["params"]["url"].rsplit("/", 1)[-1]
    request_state = review["requestState"]

    # restart before the approval is even decided
    gw2 = _build(tmp_path)
    assert gw2.approval_store.get(approval_id) is not None

    gw2.approval_store.decide(approval_id=approval_id, decision="approved", actor="EMP-4471", server_key=gw2.server_key)

    # restart again, then resume with the bound requestState
    gw3 = _build(tmp_path)
    resumed = gw3.call(
        tool="post_supplier_ticket",
        args=args,
        session_id=SESSION,
        agent_id=AGENT,
        request_state=request_state,
    )
    assert "result" in resumed

    # a fourth process must still reject the replay of the now-consumed token
    gw4 = _build(tmp_path)
    replay = gw4.call(
        tool="post_supplier_ticket",
        args=args,
        session_id=SESSION,
        agent_id=AGENT,
        request_state=request_state,
    )
    assert replay.get("isError") is True
    assert "consumed" in replay["error"] or "replay" in replay["error"]


def test_no_state_db_path_stays_pure_in_memory(tmp_path):
    gw = build_gateway(
        config_dir=CONFIG_DIR,
        ledger_path=tmp_path / "ledger.jsonl",
        server_key=b"test-key",
    )
    assert gw.state_db is None
    result = gw.call(
        tool="read_maintenance_log",
        args={"line": "line-3", "session_id": SESSION, "agent_id": AGENT},
        session_id=SESSION,
        agent_id=AGENT,
    )
    assert "result" in result
