"""Build OpenAI function-calling tool schemas from the Raja tool manifest,
so the agent's tool surface is generated from the same source of truth the
gateway enforces against.
"""
from typing import Any

from gateway.manifest import ToolManifest

# session_id/agent_id are gateway plumbing, injected by the client, not
# something the model should be asked to invent.
_PLUMBING_PROPS = {
    "session_id": {"type": "string", "description": "Raja session handle"},
    "agent_id": {"type": "string", "description": "Raja agent handle"},
}


def build_openai_tools(manifest: ToolManifest) -> list[dict[str, Any]]:
    tools = []
    for name, tool in manifest.tools.items():
        schema = dict(tool.input_schema) if tool.input_schema else {"type": "object", "properties": {}}
        properties = dict(schema.get("properties", {}))
        properties.update(_PLUMBING_PROPS)
        required = list(schema.get("required", [])) + ["session_id", "agent_id"]
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return tools
