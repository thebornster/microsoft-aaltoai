"""Egress resolution: shingle/entity-match outgoing args against the session
taint store, merge matched source labels, and build the policy context.

Label merge is most-restrictive-wins per axis:
  trust: untrusted beats trusted
  residency: eu_personal beats eu_confidential beats internal beats public
"""
from dataclasses import dataclass
from typing import Any

from gateway.manifest import ToolDef
from gateway.taint import MatchResult, TaintStore

TRUST_RANK = {"trusted": 0, "untrusted": 1}
RESIDENCY_RANK = {"public": 0, "internal": 1, "eu_confidential": 2, "eu_personal": 3}


@dataclass
class ArgLabelResult:
    trust: str
    residency: str
    sources: list[str]
    matches: list[MatchResult]


def resolve_arg_labels(taint_store: TaintStore, value: Any) -> ArgLabelResult:
    matches = taint_store.resolve(value)
    if not matches:
        return ArgLabelResult(trust="trusted", residency="public", sources=[], matches=[])
    trust = max((m.trust for m in matches), key=lambda t: TRUST_RANK[t])
    residency = max((m.residency for m in matches), key=lambda r: RESIDENCY_RANK[r])
    return ArgLabelResult(
        trust=trust,
        residency=residency,
        sources=[m.source_id for m in matches],
        matches=matches,
    )


def build_policy_context(
    tool: ToolDef,
    arg_labels: ArgLabelResult,
    taint_store: TaintStore,
) -> dict[str, Any]:
    return {
        "tool": {
            "sink_class": tool.sink_class,
            "destination_region": tool.destination_region,
        },
        "arg_labels": {
            "trust": arg_labels.trust,
            "residency": arg_labels.residency,
        },
        "session": {
            "untrusted_ingested": taint_store.untrusted_ingested,
        },
    }
