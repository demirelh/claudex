"""Tests for Plan Mode state machine and permission enforcement."""

import tempfile
from pathlib import Path

import pytest

from claudex.plan_mode import PlanState, PermissionMode


@pytest.fixture
def tmp_plan_dir(tmp_path):
    """Provide a temporary directory for plan files."""
    return tmp_path / "plans"


@pytest.fixture
def state(tmp_plan_dir):
    """Fresh PlanState with tmp plan directory."""
    return PlanState(plan_dir=tmp_plan_dir)


# --------------- lifecycle transitions ----------------------


class TestLifecycle:
    def test_initial_mode_is_normal(self, state):
        assert state.mode == PermissionMode.NORMAL
        assert state.plan_path is None

    def test_enter_plan_creates_dir_and_path(self, state, tmp_plan_dir):
        plan_path = state.enter_plan()
        assert state.mode == PermissionMode.PLAN
        assert plan_path.parent == tmp_plan_dir
        assert plan_path.suffix == ".md"
        assert tmp_plan_dir.exists()

    def test_approve_transitions_to_exec(self, state):
        plan_path = state.enter_plan()
        plan_path.write_text("# My Plan\n- Step 1\n")
        content = state.approve()
        assert state.mode == PermissionMode.EXEC
        assert "Step 1" in content

    def test_approve_raises_if_no_file(self, state):
        state.enter_plan()
        with pytest.raises(ValueError, match="No plan file found"):
            state.approve()

    def test_approve_raises_if_empty(self, state):
        plan_path = state.enter_plan()
        plan_path.write_text("   ")
        with pytest.raises(ValueError, match="Plan file is empty"):
            state.approve()

    def test_deny_stays_in_plan(self, state):
        state.enter_plan()
        state.deny()
        assert state.mode == PermissionMode.PLAN

    def test_finish_exec_returns_to_normal(self, state):
        plan_path = state.enter_plan()
        plan_path.write_text("plan")
        state.approve()
        state.finish_exec()
        assert state.mode == PermissionMode.NORMAL
        assert state.plan_path is None

    def test_stop_from_plan(self, state):
        state.enter_plan()
        state.stop()
        assert state.mode == PermissionMode.NORMAL
        assert state.plan_path is None

    def test_stop_from_exec(self, state):
        plan_path = state.enter_plan()
        plan_path.write_text("plan")
        state.approve()
        state.stop()
        assert state.mode == PermissionMode.NORMAL

    def test_full_lifecycle(self, state):
        """NORMAL → PLAN → EXEC → NORMAL"""
        assert state.mode == PermissionMode.NORMAL
        plan_path = state.enter_plan()
        assert state.mode == PermissionMode.PLAN
        plan_path.write_text("# Plan\n- Do stuff\n")
        state.approve()
        assert state.mode == PermissionMode.EXEC
        state.finish_exec()
        assert state.mode == PermissionMode.NORMAL


# --------------- get_plan_content ----------------------------


class TestGetPlanContent:
    def test_returns_none_when_no_plan(self, state):
        assert state.get_plan_content() is None

    def test_returns_none_when_file_missing(self, state):
        state.enter_plan()
        assert state.get_plan_content() is None

    def test_returns_content(self, state):
        plan_path = state.enter_plan()
        plan_path.write_text("hello world")
        assert state.get_plan_content() == "hello world"


# --------------- tool permissions ----------------------------


class TestToolPermissions:
    """Test is_tool_allowed for each mode."""

    # --- NORMAL mode: everything allowed ---
    def test_normal_allows_everything(self, state):
        for tool in ["bash", "read_file", "write_file", "edit_file", "list_directory"]:
            allowed, reason = state.is_tool_allowed(tool, {})
            assert allowed, f"{tool} should be allowed in NORMAL"
            assert reason == ""

    # --- EXEC mode: everything allowed ---
    def test_exec_allows_everything(self, state):
        plan_path = state.enter_plan()
        plan_path.write_text("plan")
        state.approve()
        for tool in ["bash", "read_file", "write_file", "edit_file"]:
            allowed, reason = state.is_tool_allowed(tool, {})
            assert allowed, f"{tool} should be allowed in EXEC"

    # --- PLAN mode: read-only tools allowed ---
    def test_plan_allows_read_only(self, state):
        state.enter_plan()
        for tool in ["read_file", "list_directory", "grep_search", "web_fetch"]:
            allowed, reason = state.is_tool_allowed(tool, {})
            assert allowed, f"{tool} should be allowed in PLAN"

    # --- PLAN mode: bash blocked ---
    def test_plan_blocks_bash(self, state):
        state.enter_plan()
        allowed, reason = state.is_tool_allowed("bash", {"command": "ls"})
        assert not allowed
        assert "bash is disabled" in reason

    # --- PLAN mode: write to plan file allowed ---
    def test_plan_allows_write_to_plan_file(self, state):
        plan_path = state.enter_plan()
        allowed, reason = state.is_tool_allowed(
            "write_file", {"path": str(plan_path)}
        )
        assert allowed

    # --- PLAN mode: write to other file blocked ---
    def test_plan_blocks_write_to_other_file(self, state):
        state.enter_plan()
        allowed, reason = state.is_tool_allowed(
            "write_file", {"path": "/tmp/other.txt"}
        )
        assert not allowed
        assert "plan file" in reason

    # --- PLAN mode: edit to plan file allowed ---
    def test_plan_allows_edit_to_plan_file(self, state):
        plan_path = state.enter_plan()
        allowed, reason = state.is_tool_allowed(
            "edit_file", {"path": str(plan_path)}
        )
        assert allowed

    # --- PLAN mode: edit to other file blocked ---
    def test_plan_blocks_edit_to_other_file(self, state):
        state.enter_plan()
        allowed, reason = state.is_tool_allowed(
            "edit_file", {"path": "/tmp/other.py"}
        )
        assert not allowed

    # --- PLAN mode: write with no path blocked ---
    def test_plan_blocks_write_without_path(self, state):
        state.enter_plan()
        allowed, reason = state.is_tool_allowed("write_file", {})
        assert not allowed
        assert "no file path" in reason

    # --- PLAN mode: unknown tool blocked ---
    def test_plan_blocks_unknown_tool(self, state):
        state.enter_plan()
        allowed, reason = state.is_tool_allowed("some_new_tool", {})
        assert not allowed
        assert "not allowed" in reason


# --------------- tools.get_tools_for_mode ---------------------


class TestGetToolsForMode:
    def test_normal_returns_all_tools(self):
        from claudex.tools import get_tools_for_mode, TOOL_DEFINITIONS

        tools = get_tools_for_mode("normal")
        assert len(tools) == len(TOOL_DEFINITIONS)

    def test_exec_returns_all_tools(self):
        from claudex.tools import get_tools_for_mode, TOOL_DEFINITIONS

        tools = get_tools_for_mode("exec")
        assert len(tools) == len(TOOL_DEFINITIONS)

    def test_plan_returns_subset(self):
        from claudex.tools import get_tools_for_mode, TOOL_DEFINITIONS

        tools = get_tools_for_mode("plan")
        assert len(tools) < len(TOOL_DEFINITIONS)
        names = {t["function"]["name"] for t in tools}
        # Must include read-only + write/edit (for plan file)
        assert "read_file" in names
        assert "list_directory" in names
        assert "grep_search" in names
        assert "web_fetch" in names
        assert "write_file" in names
        assert "edit_file" in names
        # Must NOT include bash
        assert "bash" not in names
