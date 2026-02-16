"""Plan Mode state machine and permission enforcement.

Implements the NORMAL → PLAN → EXEC → NORMAL lifecycle:
  - PLAN: Opus-locked, read-only tools + plan file write only
  - EXEC: Sonnet-locked, all tools allowed, plan loaded as context
  - NORMAL: no restrictions (default)
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class PermissionMode(str, Enum):
    """CLI permission modes."""

    NORMAL = "normal"
    PLAN = "plan"
    EXEC = "exec"


# Tools allowed in PLAN mode — read-only inspection
PLAN_READONLY_TOOLS = frozenset({
    "read_file",
    "list_directory",
    "grep_search",
    "web_fetch",
})

# Tools that MAY write, but only to the plan file itself
PLAN_WRITE_TOOLS = frozenset({
    "write_file",
    "edit_file",
})


@dataclass
class PlanState:
    """Tracks current plan mode state and enforces permissions."""

    mode: PermissionMode = PermissionMode.NORMAL
    plan_path: Optional[Path] = None
    plan_dir: Path = field(
        default_factory=lambda: Path.home() / ".config" / "claudex" / "plans"
    )

    # ---- lifecycle --------------------------------------------------------

    def enter_plan(self) -> Path:
        """Enter plan mode. Creates a timestamped plan file path.

        Returns:
            Path to the new plan file.
        """
        self.mode = PermissionMode.PLAN
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        self.plan_path = self.plan_dir / f"{ts}-plan.md"
        return self.plan_path

    def approve(self) -> str:
        """Approve plan → switch to EXEC mode.

        Returns:
            Plan file content.

        Raises:
            ValueError: If no plan file exists or is empty.
        """
        if not self.plan_path or not self.plan_path.exists():
            raise ValueError("No plan file found. Write a plan first.")
        content = self.plan_path.read_text().strip()
        if not content:
            raise ValueError("Plan file is empty. Write a plan first.")
        self.mode = PermissionMode.EXEC
        return content

    def deny(self):
        """Deny plan → stay in PLAN mode for refinement."""
        # Mode stays PLAN; plan_path preserved for editing
        pass

    def finish_exec(self):
        """Execution finished → back to NORMAL."""
        self.mode = PermissionMode.NORMAL
        self.plan_path = None

    def stop(self):
        """Force-exit any mode → NORMAL."""
        self.mode = PermissionMode.NORMAL
        self.plan_path = None

    # ---- permission checks ------------------------------------------------

    def is_tool_allowed(
        self, tool_name: str, tool_args: dict
    ) -> tuple[bool, str]:
        """Check if a tool call is permitted in the current mode.

        Args:
            tool_name: Name of the tool being invoked.
            tool_args: Arguments dict passed to the tool.

        Returns:
            (allowed, reason) — reason is empty string if allowed.
        """
        if self.mode in (PermissionMode.NORMAL, PermissionMode.EXEC):
            return True, ""

        # --- PLAN mode restrictions ---
        if tool_name in PLAN_READONLY_TOOLS:
            return True, ""

        if tool_name in PLAN_WRITE_TOOLS:
            target = tool_args.get("path", "")
            if not target:
                return False, "⚠ Plan mode: no file path provided."
            try:
                target_resolved = Path(target).expanduser().resolve()
            except Exception:
                return False, f"⚠ Plan mode: invalid path '{target}'."
            if self.plan_path and target_resolved == self.plan_path.resolve():
                return True, ""
            return (
                False,
                f"⚠ Plan mode: can only write to plan file "
                f"({self.plan_path}), not {target}",
            )

        if tool_name == "bash":
            return (
                False,
                "⚠ Plan mode: bash is disabled. Use /approve to execute.",
            )

        return False, f"⚠ Plan mode: tool '{tool_name}' is not allowed."

    def get_plan_content(self) -> Optional[str]:
        """Read current plan file content, if it exists."""
        if self.plan_path and self.plan_path.exists():
            return self.plan_path.read_text()
        return None
