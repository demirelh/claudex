#!/usr/bin/env python3
"""Demo: Using multiple models within a single ClaudeX session."""

import time
from claudex.cli import ClaudeXCLI

def demo_session_model_switching():
    print("🔵 ClaudeX Single Session - Multiple Models Demo")
    print()
    
    # Start a session with Sonnet as default
    cli = ClaudeXCLI(model="sonnet")
    
    print("=" * 70)
    print("📱 Session gestartet mit Standard-Model: Sonnet")
    print("=" * 70)
    print(f"  Aktuelles Model: {cli.current_model}")
    print(f"  API ID: {cli._build_messages()}")  # This would show the model in real usage
    print()
    
    # Simulate user input with inline model switching
    print("💬 Benutzer Eingaben (simuliert):")
    print()
    
    # Method 1: @model prefix for one-off switching
    print("1️⃣ Inline Model-Override mit @-Prefix:")
    print("   claudex › @opus hallo, wie geht es dir?")
    
    # Parse the model prefix (this is what happens internally)
    override_model, actual_input = cli._parse_model_prefix("@opus hallo, wie geht es dir?")
    print(f"   → Geparst: model='{override_model}', message='{actual_input}'")
    print(f"   → Würde Claude Opus 4.6 verwenden für diese eine Nachricht")
    print(f"   → Nach der Antwort: zurück zu {cli.current_model}")
    print()
    
    time.sleep(1)
    
    # Method 2: Permanent model switch with /model command  
    print("2️⃣ Permanenter Model-Wechsel mit /model:")
    print("   claudex › /model opus")
    
    # Simulate the command handling
    if cli._handle_command("/model opus"):
        print(f"   → Model permanent gewechselt zu: {cli.current_model}")
    print()
    
    time.sleep(1)
    
    # Method 3: Natural language model switching
    print("3️⃣ Natural Language Model-Switching:")
    print("   claudex › verwende sonnet und erkläre mir Python")
    
    override_model2, actual_input2 = cli._parse_model_prefix("verwende sonnet und erkläre mir Python")
    print(f"   → Geparst: model='{override_model2}', message='{actual_input2}'")
    print(f"   → Würde Claude Sonnet 4 verwenden für diese Nachricht")
    print()
    
    time.sleep(1)
    
    # Show conversation flow
    print("=" * 70)
    print("📜 Conversation Flow (simuliert):")
    print("=" * 70)
    
    # Add some mock messages to show session state
    cli.messages = [
        {"role": "user", "content": "hallo, wie geht es dir?"},
        {"role": "assistant", "content": "Hallo! Mir geht es gut, vielen Dank der Nachfrage. Wie kann ich Ihnen heute helfen?"},
        {"role": "user", "content": "erkläre mir Python"},
        {"role": "assistant", "content": "Python ist eine vielseitige, interpretierte Programmiersprache..."}
    ]
    
    for i, msg in enumerate(cli.messages, 1):
        role_icon = "👤" if msg["role"] == "user" else "🤖"
        content_preview = msg["content"][:60] + "..." if len(msg["content"]) > 60 else msg["content"]
        print(f"   {i}. {role_icon} {msg['role']}: {content_preview}")
    
    print()
    print("📊 Session Stats:")
    print(f"   • Aktuelle Model: {cli.current_model}")
    print(f"   • Conversation Messages: {len(cli.messages)}")
    print(f"   • System Prompt: {'Ja' if cli.system_prompt else 'Nein'}")
    print(f"   • Tools aktiviert: {'Ja' if cli.tools_enabled else 'Nein'}")
    print()
    
    # Show all available switching methods
    print("=" * 70)
    print("🔧 Verfügbare Model-Switching Methoden in einer Session:")
    print("=" * 70)
    print("   1. @model <nachricht>       — Einmaliger Override")
    print("   2. /model <name>            — Permanenter Wechsel")  
    print("   3. verwende <model> ...     — Natural Language")
    print("   4. use <model> and ...      — English Natural Language")
    print("   5. mit <model> ...          — German Natural Language")
    print()
    print("   Beispiele:")
    print("   • @opus Was ist Quantencomputing?")
    print("   • @sonnet Schreibe ein Python Script")
    print("   • /model gpt-4o")
    print("   • verwende opus und analysiere diesen Code")
    print("   • use sonnet and explain this concept")

if __name__ == "__main__":
    demo_session_model_switching()