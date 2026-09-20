import json
import pathlib
import threading
from typing import Any

from gateway.canonical import canonical_json, sha256_hex

GENESIS = "0" * 64


class LedgerError(RuntimeError):
    pass


def record_hash(prev_hash: str, record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return sha256_hex(prev_hash.encode("utf-8") + canonical_json(body))


class Ledger:
    """Append-only JSONL, each record chained to the previous by SHA256."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        records = self.read_all()
        self._next_seq = int(records[-1]["seq"]) + 1 if records else 0
        self._last_hash = str(records[-1]["hash"]) if records else GENESIS

    def read_all(self) -> list[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _tail(self) -> tuple[int, str]:
        records = self.read_all()
        if not records:
            return 0, GENESIS
        last = records[-1]
        return int(last["seq"]) + 1, str(last["hash"])

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            seq, prev_hash = self._next_seq, self._last_hash
            full = dict(record)
            full["seq"] = seq
            full["prev_hash"] = prev_hash
            full["hash"] = record_hash(prev_hash=prev_hash, record=full)
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(full, sort_keys=True, ensure_ascii=False) + "\n")
                    f.flush()
            except OSError as e:
                raise LedgerError(f"ledger append failed: {e}") from e
            self._next_seq, self._last_hash = seq + 1, full["hash"]
            return full


def verify_chain(records: list[dict[str, Any]]) -> tuple[bool, int | None, str]:
    """Returns (ok, first_bad_seq, reason)."""
    prev = GENESIS
    for i, rec in enumerate(records):
        if rec.get("seq") != i:
            return False, i, f"seq gap: expected {i}, got {rec.get('seq')}"
        if rec.get("prev_hash") != prev:
            return False, i, "prev_hash does not match previous record"
        expected = record_hash(prev_hash=prev, record=rec)
        if rec.get("hash") != expected:
            return False, i, "record hash mismatch (content altered)"
        prev = str(rec["hash"])
    return True, None, f"{len(records)} records verified"
