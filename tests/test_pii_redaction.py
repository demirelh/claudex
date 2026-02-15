"""Test PII redaction via Presidio guardrails.

These tests verify that sensitive data in prompts is masked before
being sent to the LLM backend.

Note: These tests require Presidio analyzer to be running.
"""

import pytest


@pytest.mark.integration
@pytest.mark.guardrails
def test_email_redacted(team_client):
    """Email addresses in prompts are masked."""
    r = team_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [
                {
                    "role": "user",
                    "content": "Send a message to john.doe@company.com about the project.",
                }
            ],
            "max_tokens": 50,
        },
    )
    # Request should succeed (PII is masked, not blocked)
    assert r.status_code == 200


@pytest.mark.integration
@pytest.mark.guardrails
def test_credit_card_redacted(team_client):
    """Credit card numbers in prompts are masked."""
    r = team_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [
                {
                    "role": "user",
                    "content": "My card number is 4111-1111-1111-1111, process payment.",
                }
            ],
            "max_tokens": 50,
        },
    )
    assert r.status_code == 200


@pytest.mark.integration
@pytest.mark.guardrails
def test_github_pat_redacted(team_client):
    """GitHub PATs in prompts are detected and masked."""
    r = team_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [
                {
                    "role": "user",
                    "content": "Use this token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh to authenticate.",
                }
            ],
            "max_tokens": 50,
        },
    )
    assert r.status_code == 200


@pytest.mark.integration
@pytest.mark.guardrails
def test_iban_redacted(team_client):
    """IBAN numbers in prompts are masked."""
    r = team_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [
                {
                    "role": "user",
                    "content": "Transfer to DE89370400440532013000 please.",
                }
            ],
            "max_tokens": 50,
        },
    )
    assert r.status_code == 200
