import json

from gateway.ledger import GENESIS, Ledger, verify_chain


def test_append_chains_records(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    r1 = ledger.append({"tool": "read_maintenance_log", "decision": "ALLOW"})
    r2 = ledger.append({"tool": "post_supplier_ticket", "decision": "DENY"})

    assert r1["seq"] == 0
    assert r1["prev_hash"] == GENESIS
    assert r2["seq"] == 1
    assert r2["prev_hash"] == r1["hash"]

    ok, bad_seq, _ = verify_chain(ledger.read_all())
    assert ok
    assert bad_seq is None


def test_tampering_is_detected(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = Ledger(path)
    ledger.append({"tool": "a", "decision": "ALLOW"})
    ledger.append({"tool": "b", "decision": "ALLOW"})
    ledger.append({"tool": "c", "decision": "ALLOW"})

    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["decision"] = "DENY"
    lines[1] = json.dumps(tampered, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    ok, bad_seq, reason = verify_chain(records)
    assert not ok
    assert bad_seq == 1
    assert "hash mismatch" in reason


def test_empty_ledger_verifies_ok():
    ok, bad_seq, reason = verify_chain([])
    assert ok
    assert bad_seq is None
