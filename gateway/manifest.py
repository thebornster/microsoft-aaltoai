"""Tool manifest loader: config/tools.yaml -> typed tool definitions."""
import pathlib
from dataclasses import dataclass
from typing import Any

import yaml


class ManifestError(RuntimeError):
    pass


@dataclass
class ToolDef:
    name: str
    description: str
    sink_class: str
    input_schema: dict[str, Any]
    emits: dict[str, str] | None = None
    destination_region: str | None = None


@dataclass
class Operator:
    id: str
    name: str


class ToolManifest:
    def __init__(self, tools: dict[str, ToolDef], operators: list[Operator]) -> None:
        self.tools = tools
        self.operators = operators

    @classmethod
    def from_yaml(cls, path: pathlib.Path) -> "ToolManifest":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        tools: dict[str, ToolDef] = {}
        for name, t in raw.get("tools", {}).items():
            if "sink_class" not in t:
                raise ManifestError(f"tool '{name}' is missing required field 'sink_class'")
            tools[name] = ToolDef(
                name=name,
                description=t.get("description", ""),
                sink_class=t["sink_class"],
                input_schema=t.get("input_schema", {}),
                emits=t.get("emits"),
                destination_region=t.get("destination_region"),
            )
        operators = [Operator(id=o["id"], name=o["name"]) for o in raw.get("operators", [])]
        return cls(tools=tools, operators=operators)

    def get(self, name: str) -> ToolDef:
        if name not in self.tools:
            raise ManifestError(f"unknown tool '{name}'")
        return self.tools[name]

    def known_operator_names(self) -> list[str]:
        return [o.name for o in self.operators]
