"""Test health endpoints."""

import httpx
import pytest


def test_health_liveliness(gateway_url):
    """Gateway liveliness probe returns 200."""
    r = httpx.get(f"{gateway_url}/health/liveliness", timeout=10)
    assert r.status_code == 200


def test_health_readiness(gateway_url):
    """Gateway readiness probe returns 200 when DB is connected."""
    r = httpx.get(f"{gateway_url}/health/readiness", timeout=10)
    assert r.status_code == 200


def test_health_root(gateway_url):
    """Root health endpoint returns 200."""
    r = httpx.get(f"{gateway_url}/health", timeout=10)
    assert r.status_code == 200
