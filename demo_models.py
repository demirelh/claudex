#!/usr/bin/env python3
"""Demo script to show model configuration and behavior without authentication."""

import time
from claudex.models import resolve_model, get_model_id
from claudex.cli import ClaudeXCLI

def demo_models():
    print("🔵 ClaudeX Model Demo")
    print()
    
    # Test Opus configuration
    print("=" * 60)
    print("🎯 Model: Opus")
    print("=" * 60)
    
    cli_opus = ClaudeXCLI(model="opus")
    opus_model = resolve_model("opus")
    opus_id = get_model_id("opus")
    
    print(f"  Alias:       opus")
    print(f"  Full name:   {opus_model.name}")
    print(f"  API ID:      {opus_id}")
    print(f"  Provider:    {opus_model.provider}")
    print(f"  Description: {opus_model.description}")
    print(f"  Current CLI model: {cli_opus.current_model}")
    print()
    print("  Would send: 'hallo' → Claude Opus 4.6")
    print("  Expected response: Sophisticated greeting in German")
    
    print()
    time.sleep(2)  # Wait 2 seconds as requested
    
    # Test Sonnet configuration  
    print("=" * 60)
    print("🎯 Model: Sonnet")
    print("=" * 60)
    
    cli_sonnet = ClaudeXCLI(model="sonnet")
    sonnet_model = resolve_model("sonnet")
    sonnet_id = get_model_id("sonnet")
    
    print(f"  Alias:       sonnet")
    print(f"  Full name:   {sonnet_model.name}")
    print(f"  API ID:      {sonnet_id}")
    print(f"  Provider:    {sonnet_model.provider}")
    print(f"  Description: {sonnet_model.description}")
    print(f"  Current CLI model: {cli_sonnet.current_model}")
    print()
    print("  Would send: 'hallo' → Claude Sonnet 4")
    print("  Expected response: Balanced greeting in German")
    
    print()
    print("⚠️  Note: Actual API calls require GitHub Copilot Business subscription")
    print("    and would use these endpoints:")
    print(f"    • Opus:   https://api.githubcopilot.com/chat/completions (model: {opus_id})")
    print(f"    • Sonnet: https://api.githubcopilot.com/chat/completions (model: {sonnet_id})")

if __name__ == "__main__":
    demo_models()