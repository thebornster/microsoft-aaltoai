"""Ingress labelling: tag a tool result with (trust, residency, provenance)
from its manifest declaration, and feed it into the session taint store.

In production this label would come from Purview; for the demo it is
declared in the tool manifest, honestly.
"""
import datetime
from dataclasses import dataclass
from typing import Any

from gateway.manifest import ToolDef, ToolManifest
from gateway.taint import TaintStore, flatten_to_text


@dataclass
class Label:
    source_id: str
    trust: str
    residency: str
    ingested_at: str


def label_result(tool: ToolDef, source_id: str, result: Any) -> Label:
    emits = tool.emits or {"trust": "trusted", "residency": "internal"}
    return Label(
        source_id=source_id,
        trust=emits["trust"],
        residency=emits["residency"],
        ingested_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


def ingest_result(
    taint_store: TaintStore,
    manifest: ToolManifest,
    tool: ToolDef,
    source_id: str,
    result: Any,
) -> Label:
    label = label_result(tool=tool, source_id=source_id, result=result)
    taint_store.ingest(
        source_id=source_id,
        text=flatten_to_text(result),
        trust=label.trust,
        residency=label.residency,
        known_names=manifest.known_operator_names(),
    )
    return label
