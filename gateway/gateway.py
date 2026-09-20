"""Raja gateway core: ingress labelling, egress resolution, policy
evaluation, MRTR review round-trip, and ledger recording — framework
agnostic so it's testable without HTTP. server.py wraps this in FastAPI.
"""
import datetime
import logging
import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable

from approval.tokens import ApprovalStore, TokenError, make_request_state, verify_request_state
from gateway.backends import BACKENDS, BackendError
from gateway.canonical import call_hash as compute_call_hash
from gateway.ledger import Ledger
from gateway.labeller import ingest_result
from gateway.manifest import ToolManifest
from gateway.policy import PolicyEngine
from gateway.resolver import build_policy_context, resolve_arg_labels
from gateway.taint import TaintStore

APPROVAL_BASE_URL = "https://raja.local/approve"
PROCESSING_PATH = ["local-edge", "azure-openai:swedencentral"]

logger = logging.getLogger(__name__)

# args keys that carry session plumbing, not egress payload
_PLUMBING_KEYS = {"session_id", "agent_id"}


class GatewayError(RuntimeError):
    pass


@dataclass
class SessionState:
    taint_store: TaintStore = field(default_factory=TaintStore)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class RajaGateway:
    def __init__(
        self,
        manifest: ToolManifest,
        policy_engine: PolicyEngine,
        ledger: Ledger,
        server_key: bytes,
        on_review: Callable[..., None] | None = None,
    ) -> None:
        self.manifest = manifest
        self.policy_engine = policy_engine
        self.ledger = ledger
        self.server_key = server_key
        self.approval_store = ApprovalStore()
        self.sessions: dict[str, SessionState] = {}
        # optional REVIEW notification hook (e.g. approval.teams.notify_review),
        # wired in by gateway/instance.py; never allowed to block or fail a call
        self.on_review = on_review

    def _session(self, session_id: str) -> SessionState:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionState()
        return self.sessions[session_id]

    def _payload_args(self, args: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in args.items() if k not in _PLUMBING_KEYS}

    def _log(self, **fields: Any) -> dict[str, Any]:
        record = {"ts": _now_iso(), "processing_path": PROCESSING_PATH, **fields}
        try:
            return self.ledger.append(record)
        except Exception as e:
            raise GatewayError(f"ledger append failed, failing closed: {e}") from e

    def call(
        self,
        tool: str,
        args: dict[str, Any],
        session_id: str,
        agent_id: str,
        input_responses: dict[str, Any] | None = None,
        request_state: str | None = None,
    ) -> dict[str, Any]:
        if not session_id or not agent_id:
            return {"isError": True, "error": "session_id and agent_id are required"}
        try:
            tool_def = self.manifest.get(tool)
        except Exception as e:
            return {"isError": True, "error": str(e)}

        if request_state is not None:
            return self._handle_retry(tool_def_name=tool, args=args, session_id=session_id, agent_id=agent_id, request_state=request_state)

        session = self._session(session_id)

        if tool_def.sink_class == "read_only":
            return self._call_read_only(tool_def=tool_def, args=args, session=session, session_id=session_id, agent_id=agent_id)

        return self._call_egress(tool_def=tool_def, args=args, session=session, session_id=session_id, agent_id=agent_id)

    def _execute_backend(self, tool: str, args: dict[str, Any]) -> Any:
        try:
            return BACKENDS[tool](args)
        except BackendError as e:
            raise GatewayError(str(e)) from e

    def _call_read_only(self, tool_def, args, session, session_id, agent_id) -> dict[str, Any]:
        result = self._execute_backend(tool_def.name, args)
        source_id = f"{tool_def.name}:{args.get('line') or args.get('query') or session_id}"
        label = ingest_result(
            taint_store=session.taint_store,
            manifest=self.manifest,
            tool=tool_def,
            source_id=source_id,
            result=result,
        )
        self._log(
            session=session_id,
            agent_id=agent_id,
            tool=tool_def.name,
            decision="ALLOW",
            rules_fired=[],
            arg_labels={"trust": label.trust, "residency": label.residency, "sources": [source_id]},
            destination_region=None,
            human=None,
        )
        return {"result": result}

    def _call_egress(self, tool_def, args, session, session_id, agent_id) -> dict[str, Any]:
        payload = self._payload_args(args)
        arg_labels = resolve_arg_labels(session.taint_store, payload)
        context = build_policy_context(tool=tool_def, arg_labels=arg_labels, taint_store=session.taint_store)
        decision = self.policy_engine.evaluate(context)

        rules_fired = [r.id for r in decision.fired_rules]
        label_record = {
            "trust": arg_labels.trust,
            "residency": arg_labels.residency,
            "sources": arg_labels.sources,
        }

        if decision.decision == "allow":
            result = self._execute_backend(tool_def.name, args)
            self._log(
                session=session_id,
                agent_id=agent_id,
                tool=tool_def.name,
                decision="ALLOW",
                rules_fired=rules_fired,
                arg_labels=label_record,
                destination_region=tool_def.destination_region,
                human=None,
            )
            return {"result": result}

        if decision.decision == "deny":
            self._log(
                session=session_id,
                agent_id=agent_id,
                tool=tool_def.name,
                decision="DENY",
                rules_fired=rules_fired,
                arg_labels=label_record,
                destination_region=tool_def.destination_region,
                human=None,
            )
            fired = ", ".join(f"{r.id} ({r.regulation})" for r in decision.fired_rules)
            return {"isError": True, "error": f"denied: {fired}"}

        # review
        ch = compute_call_hash(tool=tool_def.name, args=args, session_id=session_id, agent_id=agent_id)
        approval = self.approval_store.create(call_hash=ch, tool=tool_def.name, session_id=session_id, agent_id=agent_id)
        self._log(
            session=session_id,
            agent_id=agent_id,
            tool=tool_def.name,
            decision="REVIEW",
            rules_fired=rules_fired,
            arg_labels=label_record,
            destination_region=tool_def.destination_region,
            human={"decision": "PENDING", "approval_id": approval.approval_id},
        )
        req_state = make_request_state(self.server_key, approval.approval_id, ch, approval.exp)
        fired_desc = "; ".join(f"{r.id}: {r.description}" for r in decision.fired_rules)

        if self.on_review is not None:
            try:
                self.on_review(
                    approval_id=approval.approval_id,
                    tool=tool_def.name,
                    session_id=session_id,
                    agent_id=agent_id,
                    fired_rules=[(r.id, r.regulation) for r in decision.fired_rules],
                )
            except Exception as e:
                logger.warning("on_review notification hook failed (non-blocking): %s", e)
        return {
            "resultType": "input_required",
            "inputRequests": {
                "raja_approval": {
                    "method": "elicitation/create",
                    "params": {
                        "mode": "url",
                        "url": f"{APPROVAL_BASE_URL}/{approval.approval_id}",
                        "message": f"Raja: this call needs human approval ({fired_desc})",
                    },
                }
            },
            "requestState": req_state,
        }

    def _handle_retry(self, tool_def_name: str, args: dict[str, Any], session_id: str, agent_id: str, request_state: str) -> dict[str, Any]:
        try:
            state = verify_request_state(self.server_key, request_state)
        except TokenError as e:
            return {"isError": True, "error": f"invalid requestState: {e}"}

        approval_id = str(state["approval_id"])
        bound_call_hash = str(state["call_hash"])
        retried_hash = compute_call_hash(tool=tool_def_name, args=args, session_id=session_id, agent_id=agent_id)
        if retried_hash != bound_call_hash:
            return {"isError": True, "error": "retried call does not match the reviewed call (args changed)"}

        approval = self.approval_store.get(approval_id)
        if approval is None:
            return {"isError": True, "error": "unknown approval"}

        if approval.decision == "pending":
            return {
                "resultType": "input_required",
                "inputRequests": {
                    "raja_approval": {
                        "method": "elicitation/create",
                        "params": {
                            "mode": "url",
                            "url": f"{APPROVAL_BASE_URL}/{approval_id}",
                            "message": "Raja: still waiting for human approval",
                        },
                    }
                },
                "requestState": request_state,
            }

        if approval.decision == "rejected":
            self._log(
                session=session_id,
                agent_id=agent_id,
                tool=tool_def_name,
                decision="DENY",
                rules_fired=[],
                arg_labels={},
                destination_region=None,
                human={"decision": "REJECT", "by": approval.decided_by, "at": approval.decided_at},
            )
            return {"isError": True, "error": f"rejected by {approval.decided_by}"}

        try:
            self.approval_store.consume(approval_id=approval_id, call_hash=retried_hash)
        except TokenError as e:
            return {"isError": True, "error": str(e)}

        result = self._execute_backend(tool_def_name, args)
        self._log(
            session=session_id,
            agent_id=agent_id,
            tool=tool_def_name,
            decision="ALLOW",
            rules_fired=[],
            arg_labels={},
            destination_region=self.manifest.get(tool_def_name).destination_region,
            human={"decision": "APPROVE", "by": approval.decided_by, "at": approval.decided_at},
        )
        return {"result": result}


def build_gateway(config_dir: pathlib.Path, ledger_path: pathlib.Path, server_key: bytes) -> RajaGateway:
    manifest = ToolManifest.from_yaml(config_dir / "tools.yaml")
    policy_engine = PolicyEngine.from_yaml(config_dir / "policy.yaml")
    ledger = Ledger(ledger_path)
    return RajaGateway(manifest=manifest, policy_engine=policy_engine, ledger=ledger, server_key=server_key)
