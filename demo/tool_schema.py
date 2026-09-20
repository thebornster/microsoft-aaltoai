"""Build OpenAI function-calling tool schemas from the Raja tool manifest,
so the agent's tool surface is generated from the same source of truth the
gateway enforces against.
"""
from typing import Any

from gateway.manifest import ToolManifest

def build_openai_tools(manifest: ToolManifest) -> list[dict[str, Any]]:
    tools = []
    for name, tool in manifest.tools.items():
        schema = dict(tool.input_schema) if tool.input_schema else {"type": "object", "properties": {}}
        properties = dict(schema.get("properties", {}))
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": list(schema.get("required", [])),
                    },
                },
            }
        )
    return tools
