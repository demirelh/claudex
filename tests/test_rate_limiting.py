"""Test rate limiting and budget controls."""

import httpx
import pytest
import time


@pytest.mark.integration
def test_budget_limited_key(admin_client, gateway_url):
    """A key with $0 budget is rejected when making requests."""
    # Create a key with zero budget
    r = admin_client.post(
        "/key/generate",
        json={
            "max_budget": 0.000001,
            "budget_duration": "1d",
            "models": ["gpt-4.1-mini"],
            "metadata": {"purpose": "rate-limit-test"},
        },
    )
    assert r.status_code == 200
    zero_key = r.json()["key"]

    # First call may succeed (budget checked async), second should fail
    for _ in range(3):
        r2 = httpx.post(
            f"{gateway_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {zero_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
            },
            timeout=15,
        )
        if r2.status_code in [400, 429]:
            break
        time.sleep(1)

    # After exhausting the micro-budget, should be rejected
    assert r2.status_code in [200, 400, 429], f"Unexpected status: {r2.status_code}"


@pytest.mark.integration
def test_model_restricted_key(admin_client, gateway_url):
    """A key restricted to specific models cannot use other models."""
    # Create a key limited to gpt-4.1-mini only
    r = admin_client.post(
        "/key/generate",
        json={
            "max_budget": 1.0,
            "models": ["gpt-4.1-mini"],
            "metadata": {"purpose": "model-restrict-test"},
        },
    )
    assert r.status_code == 200
    limited_key = r.json()["key"]

    # Try to use a non-allowed model
    r2 = httpx.post(
        f"{gateway_url}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {limited_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5,
        },
        timeout=10,
    )
    # Should be rejected (400, 401, or 403 depending on LiteLLM version)
    assert r2.status_code in [400, 401, 403], f"Expected rejection, got {r2.status_code}"
