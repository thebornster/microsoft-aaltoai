"""Standalone ledger chain verifier: python verify_ledger.py data/ledger.jsonl"""
import json
import pathlib
import sys

from gateway.ledger import verify_chain


def main(path: str) -> int:
    records = [json.loads(l) for l in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    ok, bad_seq, reason = verify_chain(records=records)
    if ok:
        print(f"OK: {reason}")
        return 0
    print(f"TAMPERED at seq={bad_seq}: {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/ledger.jsonl"))
