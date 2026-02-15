"""Test authentication and authorization."""

import pytest


def test_no_auth_rejected(anon_client):
    """Request without auth header is rejected."""
    r = anon_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 401


def test_invalid_key_rejected(gateway_url):
    """Request with invalid key is rejected."""
    import httpx

    r = httpx.post(
        f"{gateway_url}/v1/chat/completions",
        headers={
            "Authorization": "Bearer sk-invalid-key-12345",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
        },
        timeout=10,
    )
    assert r.status_code == 401


def test_master_key_accepted(admin_client):
    """Master key can access admin endpoints."""
    r = admin_client.get("/key/info")
    # Should not return 401 (may return 400 if no key param, but not 401)
    assert r.status_code != 401


def test_create_virtual_key(admin_client):
    """Admin can create a virtual key with budget limits."""
    r = admin_client.post(
        "/key/generate",
        json={
            "max_budget": 5.0,
            "budget_duration": "30d",
            "models": ["gpt-4.1-mini"],
            "metadata": {"team": "test", "env": "ci"},
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "key" in data
    assert data["key"].startswith("sk-")
