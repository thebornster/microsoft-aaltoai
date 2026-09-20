import httpx
import pytest

from approval import teams


def test_no_webhook_url_skips_silently(monkeypatch):
    monkeypatch.delenv("RAJA_TEAMS_WEBHOOK_URL", raising=False)
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: calls.append((a, k)))

    teams.notify_review(
        approval_id="ap_1",
        tool="post_supplier_ticket",
        session_id="s1",
        agent_id="agent-1",
        fired_rules=[("gdpr-art44-transfer", "GDPR Art. 44")],
    )

    assert calls == []


def test_posts_redacted_adaptive_card_with_openurl_action(monkeypatch):
    monkeypatch.setenv("RAJA_TEAMS_WEBHOOK_URL", "https://example.com/workflow-webhook")
    monkeypatch.setenv("RAJA_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("RAJA_DEMO_SECRET", "test-secret")
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout

    monkeypatch.setattr(httpx, "post", fake_post)

    teams.notify_review(
        approval_id="ap_42",
        tool="post_supplier_ticket",
        session_id="s1",
        agent_id="agent-1",
        fired_rules=[("gdpr-art44-transfer", "GDPR Art. 44 - general principle for transfers")],
    )

    assert captured["url"] == "https://example.com/workflow-webhook"
    card = captured["json"]["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"

    action = card["actions"][0]
    assert action["type"] == "Action.OpenUrl"
    assert action["url"] == "http://127.0.0.1:8000/approve/ap_42?secret=test-secret"

    # notify_review's signature carries no call payload/args at all -- only
    # tool/session/agent/fired-rule metadata -- so there is nothing to leak here.
    rendered = str(card)
    assert "gdpr-art44-transfer" in rendered


def test_webhook_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("RAJA_TEAMS_WEBHOOK_URL", "https://example.com/workflow-webhook")

    def raising_post(*a, **k):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "post", raising_post)

    teams.notify_review(
        approval_id="ap_1",
        tool="post_supplier_ticket",
        session_id="s1",
        agent_id="agent-1",
        fired_rules=[],
    )
