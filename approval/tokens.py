"""Capability tokens and requestState signing for MRTR URL-mode approvals.

A capability token is bound to the exact call bytes (tool, args, session_id,
agent_id) via the caller-supplied call_hash. It is single-use: consumption is
tracked server-side in a nonce store, because HMAC verification alone cannot
prevent replay within the TTL window.

requestState is the opaque blob the gateway hands the MCP client and gets
echoed back on retry: {approval_id, call_hash, exp}, HMAC-signed so the
client cannot forge or tamper with it.
"""
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass

from gateway.canonical import canonical_json, sha256_hex

DEFAULT_TTL_SECONDS = 5 * 60


class TokenError(RuntimeError):
    pass


def _sign(server_key: bytes, payload: bytes) -> str:
    return hmac.new(server_key, payload, hashlib.sha256).hexdigest()


def make_request_state(server_key: bytes, approval_id: str, call_hash: str, exp: float) -> str:
    body = canonical_json({"approval_id": approval_id, "call_hash": call_hash, "exp": exp})
    sig = _sign(server_key, body)
    return f"{body.decode('utf-8')}.{sig}"


def verify_request_state(server_key: bytes, request_state: str) -> dict[str, object]:
    try:
        body_str, sig = request_state.rsplit(".", 1)
    except ValueError as e:
        raise TokenError("malformed requestState") from e
    body = body_str.encode("utf-8")
    expected_sig = _sign(server_key, body)
    if not hmac.compare_digest(sig, expected_sig):
        raise TokenError("requestState signature invalid")
    parsed = json.loads(body)
    if time.time() > float(parsed["exp"]):
        raise TokenError("requestState expired")
    return parsed


@dataclass
class Approval:
    approval_id: str
    call_hash: str
    tool: str
    session_id: str
    agent_id: str
    created_at: float
    exp: float
    decision: str = "pending"  # pending | approved | rejected
    decided_by: str | None = None
    decided_at: float | None = None
    capability_token: str | None = None
    consumed: bool = False


class ApprovalStore:
    """Server-side approval + single-use consumed-nonce store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._approvals: dict[str, Approval] = {}
        self._consumed_nonces: set[str] = set()

    def create(self, call_hash: str, tool: str, session_id: str, agent_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Approval:
        approval_id = secrets.token_urlsafe(16)
        now = time.time()
        approval = Approval(
            approval_id=approval_id,
            call_hash=call_hash,
            tool=tool,
            session_id=session_id,
            agent_id=agent_id,
            created_at=now,
            exp=now + ttl_seconds,
        )
        with self._lock:
            self._approvals[approval_id] = approval
        return approval

    def get(self, approval_id: str) -> Approval | None:
        with self._lock:
            return self._approvals.get(approval_id)

    def decide(self, approval_id: str, decision: str, actor: str, server_key: bytes) -> Approval:
        if decision not in ("approved", "rejected"):
            raise TokenError(f"invalid decision '{decision}'")
        with self._lock:
            approval = self._approvals.get(approval_id)
            if approval is None:
                raise TokenError("unknown approval_id")
            if approval.decision != "pending":
                raise TokenError(f"approval already {approval.decision}")
            if time.time() > approval.exp:
                raise TokenError("approval expired")
            approval.decision = decision
            approval.decided_by = actor
            approval.decided_at = time.time()
            if decision == "approved":
                nonce = secrets.token_hex(16)
                approval.capability_token = _sign(
                    server_key,
                    canonical_json(
                        {
                            "tool": approval.tool,
                            "call_hash": approval.call_hash,
                            "session_id": approval.session_id,
                            "agent_id": approval.agent_id,
                            "nonce": nonce,
                        }
                    ),
                ) + f".{nonce}"
            return approval

    def consume(self, approval_id: str, call_hash: str) -> Approval:
        """Validate + consume the capability token for a matching retried call.

        Raises TokenError if: unknown, not approved, call_hash mismatch
        (bound bytes changed), expired, or already consumed (replay).
        """
        with self._lock:
            approval = self._approvals.get(approval_id)
            if approval is None:
                raise TokenError("unknown approval_id")
            if approval.decision != "approved":
                raise TokenError(f"approval is {approval.decision}, not approved")
            if approval.call_hash != call_hash:
                raise TokenError("call_hash mismatch: retried call does not match the approved bytes")
            if time.time() > approval.exp:
                raise TokenError("capability token expired")
            nonce_key = f"{approval.approval_id}:{approval.capability_token}"
            if nonce_key in self._consumed_nonces or approval.consumed:
                raise TokenError("capability token already consumed (replay)")
            self._consumed_nonces.add(nonce_key)
            approval.consumed = True
            return approval
