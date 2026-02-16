"""GitHub Copilot authentication.

Supports:
  1. GITHUB_TOKEN environment variable (PAT or OAuth token)
  2. Cached OAuth token from previous device flow
  3. gh CLI token (~/.config/gh/hosts.yml)
  4. Interactive GitHub OAuth device flow

The GitHub token is exchanged for a short-lived Copilot session token
via the internal Copilot token endpoint.
"""

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# GitHub Copilot VS Code extension OAuth App — publicly known client ID.
# This is the same client ID used by the VS Code Copilot Chat extension
# to authenticate with GitHub via OAuth device flow.
# ---------------------------------------------------------------------------
COPILOT_CLIENT_ID = "Iv1.b507a08c87ecfe98"

GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"

CONFIG_DIR = Path.home() / ".config" / "claudex"
GITHUB_TOKEN_FILE = CONFIG_DIR / "github_token.json"


@dataclass
class CopilotToken:
    """Short-lived Copilot API session token (~30 min TTL)."""

    token: str
    expires_at: int

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 60s buffer)."""
        return time.time() >= self.expires_at - 60


def get_github_token() -> Optional[str]:
    """Try to obtain a GitHub token from multiple sources.

    Priority:
      1. GITHUB_TOKEN environment variable
      2. Cached token from previous device flow auth
      3. gh CLI config file
    """
    # 1. Environment variable
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    # 2. Cached from previous device flow
    if GITHUB_TOKEN_FILE.exists():
        try:
            data = json.loads(GITHUB_TOKEN_FILE.read_text())
            cached = data.get("oauth_token")
            if cached:
                return cached
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. gh CLI config
    gh_hosts = Path.home() / ".config" / "gh" / "hosts.yml"
    if gh_hosts.exists():
        try:
            content = gh_hosts.read_text()
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("oauth_token:"):
                    return stripped.split(":", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass

    return None


def device_flow_login(console=None) -> str:
    """Authenticate interactively via GitHub OAuth device flow.

    Opens a browser-style flow:
      1. Displays a URL + code for the user to enter on github.com
      2. Polls until the user authorizes
      3. Returns and caches the OAuth token

    Args:
        console: Optional Rich console for styled output.

    Returns:
        GitHub OAuth access token.
    """
    _print = console.print if console else print

    _print()
    _print("  [bold]GitHub authentication required[/bold]" if console else "  GitHub authentication required")
    _print("  Starting device flow...")
    _print()

    with httpx.Client(timeout=30) as client:
        # Step 1: Request device code
        resp = client.post(
            GITHUB_DEVICE_CODE_URL,
            data={
                "client_id": COPILOT_CLIENT_ID,
                "scope": "read:user",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        device_code = data["device_code"]
        user_code = data["user_code"]
        verification_uri = data["verification_uri"]
        interval = data.get("interval", 5)

        _print(f"  Open:  {verification_uri}")
        _print(f"  Code:  [bold cyan]{user_code}[/bold cyan]" if console else f"  Code:  {user_code}")
        _print()

        # Try to open browser automatically
        try:
            import webbrowser
            webbrowser.open(verification_uri)
        except Exception:
            pass

        _print("  Waiting for authorization", end="")
        sys.stdout.flush()

        # Step 2: Poll for completion
        while True:
            time.sleep(interval)
            resp = client.post(
                GITHUB_OAUTH_TOKEN_URL,
                data={
                    "client_id": COPILOT_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
            )
            result = resp.json()

            if "access_token" in result:
                oauth_token = result["access_token"]
                # Cache it
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                GITHUB_TOKEN_FILE.write_text(
                    json.dumps({"oauth_token": oauth_token, "created_at": int(time.time())})
                )
                GITHUB_TOKEN_FILE.chmod(0o600)
                print(" done!")
                return oauth_token

            error = result.get("error", "")
            if error == "authorization_pending":
                print(".", end="", flush=True)
                continue
            elif error == "slow_down":
                interval += 5
                continue
            elif error == "expired_token":
                print()
                raise SystemExit("  Device code expired. Please run again.")
            elif error == "access_denied":
                print()
                raise SystemExit("  Authorization denied by user.")
            else:
                desc = result.get("error_description", "")
                print()
                raise SystemExit(f"  Auth error: {error} — {desc}")


def get_github_user(github_token: str) -> Optional[dict]:
    """Fetch the authenticated GitHub user info."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/json",
                },
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


def get_copilot_token(github_token: str, debug: bool = False) -> CopilotToken:
    """Exchange a GitHub token for a short-lived Copilot session token.

    Args:
        github_token: GitHub OAuth or PAT token.
        debug: If True, print extra diagnostic info.

    Returns:
        CopilotToken with session token and expiry.

    Raises:
        SystemExit: If token exchange fails (wrong permissions, no Copilot access).
    """
    # Optionally fetch user info for diagnostics
    user_info = None
    if debug:
        user_info = get_github_user(github_token)
        if user_info:
            login = user_info.get('login', '?')
            name = user_info.get('name', '')
            plan = user_info.get('plan', {}).get('name', '?')
            print(f"  [debug] GitHub user: {login} ({name})")
            print(f"  [debug] Plan: {plan}")
            print(f"  [debug] Token: {github_token[:8]}...{github_token[-4:]}")
        else:
            print(f"  [debug] Could not fetch user info")

    with httpx.Client(timeout=30) as client:
        resp = client.get(
            COPILOT_TOKEN_URL,
            headers={
                "Authorization": f"token {github_token}",
                "Accept": "application/json",
                "Editor-Version": "vscode/1.96.0",
                "Editor-Plugin-Version": "copilot-chat/0.24.0",
                "User-Agent": "ClaudeX-CLI/0.1.0",
            },
        )

        if debug:
            print(f"  [debug] Copilot token endpoint: {resp.status_code}")

        if resp.status_code == 401:
            # Token is invalid — clear cached token
            if GITHUB_TOKEN_FILE.exists():
                GITHUB_TOKEN_FILE.unlink()
            raise SystemExit(
                "  GitHub token rejected (401).\n"
                "  Set GITHUB_TOKEN env var or run again to re-authenticate."
            )

        if resp.status_code == 403:
            raise SystemExit(
                "  Copilot access denied (403).\n"
                "  Ensure your GitHub account has an active Copilot Business subscription."
            )

        if resp.status_code == 404:
            # Try to give a helpful error with account info
            if not user_info:
                user_info = get_github_user(github_token)
            login = user_info.get('login', 'unknown') if user_info else 'unknown'
            raise SystemExit(
                f"  Copilot access not available (404).\n"
                f"\n"
                f"  Logged in as: {login}\n"
                f"\n"
                f"  Possible causes:\n"
                f"  1. This account has no Copilot Business/Enterprise subscription\n"
                f"  2. Your org admin hasn't assigned a Copilot seat to this account\n"
                f"  3. You authenticated with the wrong GitHub account\n"
                f"\n"
                f"  To fix:\n"
                f"  • Check your Copilot status: https://github.com/settings/copilot\n"
                f"  • Re-login with your Copilot-enabled account:\n"
                f"      claudex --logout && claudex\n"
                f"  • Use --debug for more info: claudex --debug"
            )

        resp.raise_for_status()
        data = resp.json()

        return CopilotToken(
            token=data["token"],
            expires_at=data["expires_at"],
        )


def clear_cached_token():
    """Remove cached GitHub token and show which sources remain."""
    removed = False
    if GITHUB_TOKEN_FILE.exists():
        GITHUB_TOKEN_FILE.unlink()
        removed = True

    # Warn about other token sources that will still be used
    remaining = []
    if os.environ.get("GITHUB_TOKEN"):
        remaining.append("GITHUB_TOKEN environment variable")
    gh_hosts = Path.home() / ".config" / "gh" / "hosts.yml"
    if gh_hosts.exists():
        remaining.append(f"gh CLI config ({gh_hosts})")

    return removed, remaining


def ensure_auth(console=None, debug: bool = False) -> tuple[str, CopilotToken]:
    """Full authentication flow.

    1. Try to get an existing GitHub token
    2. If none found, run interactive device flow
    3. Exchange GitHub token for Copilot session token

    Args:
        console: Optional Rich console for styled output.
        debug: If True, print diagnostic info.

    Returns:
        Tuple of (github_token, copilot_token).
    """
    github_token = get_github_token()

    if not github_token:
        github_token = device_flow_login(console)

    try:
        copilot_token = get_copilot_token(github_token, debug=debug)
    except SystemExit:
        raise
    except Exception as e:
        # Token might be stale — try device flow
        _print = console.print if console else print
        _print(f"  Token exchange failed: {e}")
        _print("  Trying interactive login...")
        clear_cached_token()
        github_token = device_flow_login(console)
        copilot_token = get_copilot_token(github_token, debug=debug)

    return github_token, copilot_token
