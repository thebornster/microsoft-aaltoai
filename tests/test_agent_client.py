from demo.agent_client import _parse_azure_endpoint


def test_parses_full_target_uri_from_azure_portal():
    raw = (
        "https://raja-hackathon-swedencentral.openai.azure.com/openai/deployments/"
        "raja-gpt4o/chat/completions?api-version=2025-01-01-preview"
    )
    base, deployment, api_version = _parse_azure_endpoint(raw)
    assert base == "https://raja-hackathon-swedencentral.openai.azure.com"
    assert deployment == "raja-gpt4o"
    assert api_version == "2025-01-01-preview"


def test_parses_bare_resource_endpoint():
    base, deployment, api_version = _parse_azure_endpoint("https://raja-hackathon-swedencentral.openai.azure.com")
    assert base == "https://raja-hackathon-swedencentral.openai.azure.com"
    assert deployment is None
    assert api_version is None
