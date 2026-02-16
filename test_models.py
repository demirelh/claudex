#!/usr/bin/env python3
"""Test script to send 'hallo' with opus and sonnet models."""

import asyncio
import time
from claudex.cli import ClaudeXCLI

async def test_models():
    print("🔵 Testing ClaudeX with different models...")
    print()
    
    # Test with Opus
    print("=" * 60)
    print("🎯 Testing with Opus (claude-opus-4.6)")
    print("=" * 60)
    
    cli_opus = ClaudeXCLI(model="opus")
    # Skip auth for this demo - would normally authenticate
    try:
        # This would normally require authentication
        await cli_opus._send_message("hallo")
    except Exception as e:
        print(f"Expected auth error with Opus: {e}")
    
    print()
    time.sleep(2)  # Wait 2 seconds
    
    # Test with Sonnet
    print("=" * 60)
    print("🎯 Testing with Sonnet (claude-sonnet-4)")
    print("=" * 60)
    
    cli_sonnet = ClaudeXCLI(model="sonnet")
    try:
        # This would normally require authentication
        await cli_sonnet._send_message("hallo")
    except Exception as e:
        print(f"Expected auth error with Sonnet: {e}")

if __name__ == "__main__":
    asyncio.run(test_models())