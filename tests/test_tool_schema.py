import pathlib

from demo.tool_schema import build_openai_tools
from gateway.manifest import ToolManifest

MANIFEST_PATH = pathlib.Path(__file__).parent.parent / "config" / "tools.yaml"


def test_builds_one_schema_per_tool_with_plumbing_args():
    manifest = ToolManifest.from_yaml(MANIFEST_PATH)
    tools = build_openai_tools(manifest)
    names = {t["function"]["name"] for t in tools}
    assert names == set(manifest.tools.keys())

    by_name = {t["function"]["name"]: t for t in tools}
    ticket = by_name["post_supplier_ticket"]["function"]
    assert "session_id" in ticket["parameters"]["properties"]
    assert "agent_id" in ticket["parameters"]["properties"]
    assert "session_id" in ticket["parameters"]["required"]
    assert "subject" in ticket["parameters"]["required"]
