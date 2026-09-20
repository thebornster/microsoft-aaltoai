import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def call_hash(tool: str, args: dict[str, Any], session_id: str, agent_id: str) -> str:
    return sha256_hex(canonical_json({"tool": tool, "args": args, "session_id": session_id, "agent_id": agent_id}))
