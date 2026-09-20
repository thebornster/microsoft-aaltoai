import pathlib

import pytest

from gateway.policy import PolicyEngine, PolicyError

POLICY_PATH = pathlib.Path(__file__).parent.parent / "config" / "policy.yaml"


def test_loads_real_policy_and_requires_regulation(tmp_path):
    engine = PolicyEngine.from_yaml(POLICY_PATH)
    assert len(engine.rules) == 4
    for rule in engine.rules:
        assert rule.regulation


def test_missing_regulation_is_a_load_error(tmp_path):
    bad = tmp_path / "policy.yaml"
    bad.write_text(
        """
version: 1
eu_regions: [eu-north]
rules:
  - id: no-regulation
    description: missing the required field
    when: { arg_labels.trust: untrusted }
    then: review
""",
        encoding="utf-8",
    )
    with pytest.raises(PolicyError):
        PolicyEngine.from_yaml(bad)


def test_untrusted_egress_is_review():
    engine = PolicyEngine.from_yaml(POLICY_PATH)
    decision = engine.evaluate(
        {
            "tool": {"sink_class": "egress_external", "destination_region": "us-east"},
            "arg_labels": {"trust": "untrusted", "residency": "public"},
            "session": {"untrusted_ingested": True},
        }
    )
    assert decision.decision == "review"
    fired_ids = {r.id for r in decision.fired_rules}
    assert "nis2-art21-untrusted-egress" in fired_ids


def test_eu_personal_to_non_eu_is_hard_deny_and_wins_over_review():
    engine = PolicyEngine.from_yaml(POLICY_PATH)
    decision = engine.evaluate(
        {
            "tool": {"sink_class": "egress_external", "destination_region": "us-east"},
            "arg_labels": {"trust": "untrusted", "residency": "eu_personal"},
            "session": {"untrusted_ingested": True},
        }
    )
    assert decision.decision == "deny"
    assert any(r.id == "gdpr-art44-transfer" for r in decision.fired_rules)
    # most-restrictive-wins: deny beats the review rules that also fired
    assert len(decision.fired_rules) > 1


def test_eu_personal_to_eu_destination_is_allowed():
    engine = PolicyEngine.from_yaml(POLICY_PATH)
    decision = engine.evaluate(
        {
            "tool": {"sink_class": "egress_internal", "destination_region": "eu-north"},
            "arg_labels": {"trust": "trusted", "residency": "eu_personal"},
            "session": {"untrusted_ingested": False},
        }
    )
    assert decision.decision == "allow"
    assert decision.fired_rules == []


def test_readonly_trusted_call_is_allowed():
    engine = PolicyEngine.from_yaml(POLICY_PATH)
    decision = engine.evaluate(
        {
            "tool": {"sink_class": "read_only", "destination_region": None},
            "arg_labels": {"trust": "trusted", "residency": "eu_personal"},
            "session": {"untrusted_ingested": False},
        }
    )
    assert decision.decision == "allow"
