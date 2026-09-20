"""Power Automate Workflows webhook + Adaptive Card delivery for REVIEW
notifications.

O365 Connectors were permanently disabled 18-22 May 2026; Workflows
webhooks are the only supported path, and interactive buttons don't
render for MessageCard payloads via Workflows -- use an Adaptive Card
with Action.OpenUrl pointing at the Raja approval page instead.

Only redacted metadata goes out: tool name, fired rule ids/regulations,
session/agent ids. The raw call payload never leaves the local edge --
that's the whole point of the edge/cloud split.

Delivery is best-effort. The approval page is the actual HITL gate; this
is a convenience ping (P2 polish per the design doc). A webhook failure
must never block or fail the gateway call.
"""
import logging
import os

import httpx

logger = logging.getLogger("raja.teams")


def _approval_url(approval_id: str) -> str:
    base_url = os.environ.get("RAJA_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    secret = os.environ.get("RAJA_DEMO_SECRET", "raja-demo")
    return f"{base_url}/approve/{approval_id}?secret={secret}"


def _adaptive_card(tool: str, session_id: str, agent_id: str, fired_rules: list[tuple[str, str]], approval_url: str) -> dict:
    rule_text = "\n\n".join(f"**{rule_id}** -- {regulation}" for rule_id, regulation in fired_rules) or "no rules fired"
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": [
            {"type": "TextBlock", "text": "Raja: human approval required", "weight": "bolder", "size": "medium"},
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Tool", "value": tool},
                    {"title": "Session", "value": session_id},
                    {"title": "Agent", "value": agent_id},
                ],
            },
            {"type": "TextBlock", "text": rule_text, "wrap": True},
            {
                "type": "TextBlock",
                "text": "Redacted metadata only -- the full call payload stays on the local edge.",
                "wrap": True,
                "isSubtle": True,
                "size": "small",
            },
        ],
        "actions": [{"type": "Action.OpenUrl", "title": "Review on Raja", "url": approval_url}],
    }


def notify_review(approval_id: str, tool: str, session_id: str, agent_id: str, fired_rules: list[tuple[str, str]]) -> None:
    webhook_url = os.environ.get("RAJA_TEAMS_WEBHOOK_URL")
    if not webhook_url:
        logger.info("RAJA_TEAMS_WEBHOOK_URL not set, skipping Teams notification for approval %s", approval_id)
        return
    card = _adaptive_card(
        tool=tool,
        session_id=session_id,
        agent_id=agent_id,
        fired_rules=fired_rules,
        approval_url=_approval_url(approval_id),
    )
    payload = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}
    try:
        httpx.post(webhook_url, json=payload, timeout=5.0)
    except httpx.HTTPError as e:
        logger.warning("Teams webhook delivery failed (non-blocking): %s", e)
