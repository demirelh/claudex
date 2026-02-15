"""Shared fixtures for the ClaudeX test suite."""

import os
import pytest
import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:4000")
MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-litellm-test-key")
# A virtual key for team-level tests (created in setup or test_auth)
TEAM_KEY = os.getenv("TEST_TEAM_KEY", "")


@pytest.fixture
def gateway_url():
    return GATEWAY_URL


@pytest.fixture
def master_key():
    return MASTER_KEY


@pytest.fixture
def team_key():
    return TEAM_KEY


@pytest.fixture
def admin_client():
    """HTTP client authenticated with master key."""
    return httpx.Client(
        base_url=GATEWAY_URL,
        headers={
            "Authorization": f"Bearer {MASTER_KEY}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


@pytest.fixture
def team_client():
    """HTTP client authenticated with a team virtual key."""
    key = TEAM_KEY or MASTER_KEY  # Fallback to master for local dev
    return httpx.Client(
        base_url=GATEWAY_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    )


@pytest.fixture
def anon_client():
    """HTTP client with no authentication."""
    return httpx.Client(
        base_url=GATEWAY_URL,
        headers={"Content-Type": "application/json"},
        timeout=10.0,
    )
