"""YAML policy engine: deterministic ALLOW / REVIEW / DENY evaluation.

No AI in the decision loop. Every rule is evaluated against the call context;
outcomes are collected and the most restrictive wins (DENY > REVIEW > ALLOW).
"""
import fnmatch
import pathlib
from dataclasses import dataclass
from typing import Any

import yaml

SEVERITY = {"allow": 0, "review": 1, "deny": 2}


class PolicyError(RuntimeError):
    pass


@dataclass
class Rule:
    id: str
    regulation: str
    description: str
    when: dict[str, Any]
    then: str


@dataclass
class FiredRule:
    id: str
    regulation: str
    description: str
    decision: str


@dataclass
class PolicyDecision:
    decision: str
    fired_rules: list[FiredRule]


class PolicyEngine:
    def __init__(self, rules: list[Rule], eu_regions: list[str]) -> None:
        self.rules = rules
        self.eu_regions = eu_regions

    @classmethod
    def from_yaml(cls, path: pathlib.Path) -> "PolicyEngine":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        rules: list[Rule] = []
        for r in raw.get("rules", []):
            if "regulation" not in r or not r["regulation"]:
                raise PolicyError(f"rule '{r.get('id', '?')}' is missing required field 'regulation'")
            rules.append(
                Rule(
                    id=r["id"],
                    regulation=r["regulation"],
                    description=r.get("description", ""),
                    when=r["when"],
                    then=r["then"],
                )
            )
        return cls(rules=rules, eu_regions=raw.get("eu_regions", []))

    def _region_is_eu(self, region: str) -> bool:
        return any(fnmatch.fnmatch(region, pattern) for pattern in self.eu_regions)

    def _lookup(self, context: dict[str, Any], dotted_key: str) -> Any:
        node: Any = context
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def _condition_matches(self, context: dict[str, Any], key: str, expected: Any) -> bool:
        actual = self._lookup(context, key)
        if key == "tool.destination_region" and expected == "non_eu":
            return isinstance(actual, str) and not self._region_is_eu(actual)
        if key == "tool.destination_region" and expected == "eu":
            return isinstance(actual, str) and self._region_is_eu(actual)
        return actual == expected

    def _rule_fires(self, rule: Rule, context: dict[str, Any]) -> bool:
        return all(self._condition_matches(context, key, expected) for key, expected in rule.when.items())

    def evaluate(self, context: dict[str, Any]) -> PolicyDecision:
        fired: list[FiredRule] = []
        for rule in self.rules:
            if self._rule_fires(rule, context):
                fired.append(
                    FiredRule(
                        id=rule.id,
                        regulation=rule.regulation,
                        description=rule.description,
                        decision=rule.then,
                    )
                )
        if not fired:
            return PolicyDecision(decision="allow", fired_rules=[])
        worst = max(fired, key=lambda f: SEVERITY[f.decision])
        return PolicyDecision(decision=worst.decision, fired_rules=fired)
