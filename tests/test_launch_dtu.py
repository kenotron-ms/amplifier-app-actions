"""Tests for amplifier_app_actions.tools.launch_dtu — _parse_repo helper."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from amplifier_app_actions.tools.launch_dtu import (
    LaunchDTUTool,  # noqa: F401
    _is_sha,  # noqa: F401
    _parse_repo,
    mount,  # noqa: F401
)


# ---------------------------------------------------------------------------
# _parse_repo tests
# ---------------------------------------------------------------------------


def test_parse_repo_owner_repo_and_tag():
    """'owner/repo@v1.2.3' → ('owner', 'repo', 'v1.2.3')."""
    owner, repo, ref = _parse_repo("myorg/myrepo@v1.2.3")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref == "v1.2.3"


def test_parse_repo_owner_repo_and_branch():
    """'owner/repo@main' → ('owner', 'repo', 'main')."""
    owner, repo, ref = _parse_repo("myorg/myrepo@main")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref == "main"


def test_parse_repo_branch_with_slash():
    """'owner/repo@feat/my-branch' → ('owner', 'repo', 'feat/my-branch').

    Uses rsplit('@', 1) so branch names containing '/' are handled correctly.
    """
    owner, repo, ref = _parse_repo("myorg/myrepo@feat/my-branch")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref == "feat/my-branch"


def test_parse_repo_no_ref_returns_none():
    """'owner/repo' with no '@' suffix returns ref=None."""
    owner, repo, ref = _parse_repo("myorg/myrepo")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref is None


def test_parse_repo_sha_ref():
    """'owner/repo@abc1234' → ('owner', 'repo', 'abc1234')."""
    owner, repo, ref = _parse_repo("myorg/myrepo@abc1234")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref == "abc1234"


# ---------------------------------------------------------------------------
# _is_sha tests
# ---------------------------------------------------------------------------


def test_is_sha_seven_char_hex():
    """Seven lowercase hex chars ('abc1234') → True."""
    assert _is_sha("abc1234") is True


def test_is_sha_forty_char_hex():
    """Forty lowercase hex chars → True (full SHA-1 length)."""
    assert _is_sha("a" * 40) is True


def test_is_sha_tag_is_not_sha():
    """Version tag ('v1.2.3') contains dots/uppercase → False."""
    assert _is_sha("v1.2.3") is False


def test_is_sha_branch_main_is_not_sha():
    """Branch name 'main' contains non-hex chars → False."""
    assert _is_sha("main") is False


# ---------------------------------------------------------------------------
# _generate_profile tests
# ---------------------------------------------------------------------------


def test_branch_or_tag_uses_depth_and_branch_flag():
    """Branch/tag ref: git clone --depth 1 --branch <ref> <url> <dest>."""
    tool = LaunchDTUTool({})
    profile = tool._generate_profile(
        repos=["microsoft/amplifier-core@v1.2.3"],
        commands=["echo hello"],
    )
    assert "--depth 1" in profile
    assert "--branch v1.2.3" in profile
    assert "ubuntu:24.04" in profile
    assert "GITHUB_TOKEN" in profile
    assert "ANTHROPIC_API_KEY" in profile
    assert "/workspace/amplifier-core" in profile


def test_sha_uses_full_clone_then_checkout():
    """SHA ref: git clone <url> <dest> && git -C <dest> checkout <sha> (no --depth, no --branch)."""
    sha = "abc1234"
    tool = LaunchDTUTool({})
    profile = tool._generate_profile(
        repos=[f"microsoft/amplifier-core@{sha}"],
        commands=["echo hello"],
    )
    assert f"checkout {sha}" in profile
    assert "--branch" not in profile


def test_no_ref_uses_depth_only():
    """No ref: git clone --depth 1 <url> <dest> (no --branch)."""
    tool = LaunchDTUTool({})
    profile = tool._generate_profile(
        repos=["microsoft/amplifier-core"],
        commands=["echo hello"],
    )
    assert "--depth 1" in profile
    assert "--branch" not in profile


# ---------------------------------------------------------------------------
# execute() tests — happy path
# ---------------------------------------------------------------------------


def _make_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    """Return a mock subprocess.CompletedProcess-like object."""
    p = MagicMock()
    p.stdout = stdout
    p.stderr = stderr
    p.returncode = returncode
    return p


@pytest.mark.asyncio
async def test_execute_lifecycle_ordering():
    """launch is called first, exec per command in the middle, destroy called last."""
    tool = LaunchDTUTool({})
    call_sequence: list[str] = []

    async def fake_to_thread(fn, cmd, **kwargs):
        subcommand = cmd[1]  # "launch" | "exec" | "destroy"
        call_sequence.append(subcommand)
        if subcommand == "launch":
            return _make_proc(stdout=json.dumps({"instance_id": "dtu-abc123"}))
        elif subcommand == "exec":
            return _make_proc(stdout="out\n")
        return _make_proc()

    with patch("asyncio.to_thread", side_effect=fake_to_thread):
        await tool.execute(
            {"repos": ["myorg/myrepo"], "commands": ["echo hello", "echo world"]}
        )

    assert call_sequence[0] == "launch"
    assert call_sequence[-1] == "destroy"
    # Both commands produced exactly one "exec" call each
    assert call_sequence.count("exec") == 2


@pytest.mark.asyncio
async def test_execute_launch_includes_format_json():
    """The launch command includes '--format' 'json' flags."""
    tool = LaunchDTUTool({})
    launch_cmd_captured: list[str] = []

    async def fake_to_thread(fn, cmd, **kwargs):
        if cmd[1] == "launch":
            launch_cmd_captured.extend(cmd)
            return _make_proc(stdout=json.dumps({"instance_id": "dtu-xyz"}))
        elif cmd[1] == "exec":
            return _make_proc()
        return _make_proc()

    with patch("asyncio.to_thread", side_effect=fake_to_thread):
        await tool.execute({"repos": ["myorg/myrepo"], "commands": ["echo hi"]})

    assert "--format" in launch_cmd_captured
    assert "json" in launch_cmd_captured


@pytest.mark.asyncio
async def test_execute_one_exec_per_command():
    """execute() dispatches exactly one exec call per command string."""
    tool = LaunchDTUTool({})
    exec_bash_args: list[str] = []

    async def fake_to_thread(fn, cmd, **kwargs):
        if cmd[1] == "launch":
            return _make_proc(stdout=json.dumps({"instance_id": "dtu-123"}))
        elif cmd[1] == "exec":
            # The bash -c argument is the last element
            exec_bash_args.append(cmd[-1])
            return _make_proc()
        return _make_proc()

    commands = ["ls /", "pwd", "whoami"]
    with patch("asyncio.to_thread", side_effect=fake_to_thread):
        await tool.execute({"repos": ["myorg/myrepo"], "commands": commands})

    assert len(exec_bash_args) == len(commands)
    assert exec_bash_args == commands


@pytest.mark.asyncio
async def test_execute_output_structure():
    """ToolResult.output contains instance_id and outputs list with correct keys."""
    tool = LaunchDTUTool({})
    expected_id = "dtu-output-test"

    async def fake_to_thread(fn, cmd, **kwargs):
        if cmd[1] == "launch":
            return _make_proc(stdout=json.dumps({"instance_id": expected_id}))
        elif cmd[1] == "exec":
            return _make_proc(stdout="hello\n", stderr="warn\n", returncode=0)
        return _make_proc()

    with patch("asyncio.to_thread", side_effect=fake_to_thread):
        result = await tool.execute(
            {"repos": ["myorg/myrepo"], "commands": ["echo hello"]}
        )

    assert result.success is True
    assert isinstance(result.output, dict)
    assert result.output["instance_id"] == expected_id
    assert isinstance(result.output["outputs"], list)
    assert len(result.output["outputs"]) == 1

    item = result.output["outputs"][0]
    assert item["command"] == "echo hello"
    assert item["stdout"] == "hello\n"
    assert item["stderr"] == "warn\n"
    assert item["returncode"] == 0


@pytest.mark.asyncio
async def test_execute_success_false_on_nonzero_returncode():
    """success=False when any exec command returns a non-zero returncode."""
    tool = LaunchDTUTool({})

    async def fake_to_thread(fn, cmd, **kwargs):
        if cmd[1] == "launch":
            return _make_proc(stdout=json.dumps({"instance_id": "dtu-fail"}))
        elif cmd[1] == "exec":
            return _make_proc(stderr="error output\n", returncode=1)
        return _make_proc()

    with patch("asyncio.to_thread", side_effect=fake_to_thread):
        result = await tool.execute(
            {"repos": ["myorg/myrepo"], "commands": ["failing-cmd"]}
        )

    assert result.success is False
    assert result.output["outputs"][0]["returncode"] == 1


# ---------------------------------------------------------------------------
# execute() tests — failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_destroy_called_when_exec_raises_unexpectedly():
    """OSError during exec: destroy is still called via finally and exception propagates."""
    tool = LaunchDTUTool({})
    destroyed: list[str] = []

    async def fake_to_thread(fn, cmd, **kwargs):
        subcommand = cmd[1]
        if subcommand == "launch":
            return _make_proc(stdout=json.dumps({"instance_id": "dtu-oserr"}))
        elif subcommand == "exec":
            raise OSError("binary not found")
        elif subcommand == "destroy":
            destroyed.append(cmd[2])  # cmd[2] is the instance_id argument
            return _make_proc()
        return _make_proc()

    with patch("asyncio.to_thread", side_effect=fake_to_thread):
        with pytest.raises(OSError, match="binary not found"):
            await tool.execute({"repos": ["myorg/myrepo"], "commands": ["echo hi"]})

    assert destroyed == ["dtu-oserr"]


@pytest.mark.asyncio
async def test_execute_launch_failure_scrubs_token_in_output():
    """CalledProcessError with token in stderr: token is scrubbed in result.output."""
    tool = LaunchDTUTool({})
    token = "ghp_secret_token_here"
    raw_stderr = (
        f"fatal: repository 'https://x-access-token:{token}@github.com/owner/repo'"
        " not found\n"
    )

    async def fake_to_thread(fn, cmd, **kwargs):
        if cmd[1] == "launch":
            raise subprocess.CalledProcessError(
                returncode=128, cmd=cmd, stderr=raw_stderr
            )
        return _make_proc()

    with patch("asyncio.to_thread", side_effect=fake_to_thread):
        result = await tool.execute(
            {"repos": ["myorg/myrepo"], "commands": ["echo hi"]}
        )

    assert result.success is False
    # Token must be scrubbed from both output and error
    assert token not in str(result.output), "Token found in output (not scrubbed)"
    assert token not in str(result.error), "Token found in error dict (not scrubbed)"
    assert "x-access-token:***@" in result.output


@pytest.mark.asyncio
async def test_execute_launch_failure_does_not_call_destroy():
    """If launch fails, instance_id is never set so destroy is never called."""
    tool = LaunchDTUTool({})
    destroy_called = False

    async def fake_to_thread(fn, cmd, **kwargs):
        nonlocal destroy_called
        if cmd[1] == "launch":
            raise subprocess.CalledProcessError(
                returncode=1, cmd=cmd, stderr="launch failed"
            )
        elif cmd[1] == "destroy":
            destroy_called = True
            return _make_proc()
        return _make_proc()

    with patch("asyncio.to_thread", side_effect=fake_to_thread):
        result = await tool.execute(
            {"repos": ["myorg/myrepo"], "commands": ["echo hi"]}
        )

    assert result.success is False
    assert destroy_called is False


# ---------------------------------------------------------------------------
# mount() tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mount_registers_tool_with_correct_name():
    """mount() calls coordinator.mount with args[0]=='tools' and kwargs['name']=='launch_dtu'."""
    coordinator = MagicMock()
    coordinator.mount = MagicMock(return_value=None)

    async def async_mount(*args, **kwargs):
        return None

    coordinator.mount = MagicMock(side_effect=async_mount)

    await mount(coordinator)

    coordinator.mount.assert_called_once()
    call_args = coordinator.mount.call_args
    assert call_args.args[0] == "tools"
    assert call_args.kwargs["name"] == "launch_dtu"


@pytest.mark.asyncio
async def test_mount_returns_dict_with_tool_name():
    """mount() returns {'tool': 'launch_dtu'}."""
    coordinator = MagicMock()

    async def async_mount(*args, **kwargs):
        return None

    coordinator.mount = MagicMock(side_effect=async_mount)

    result = await mount(coordinator)

    assert result == {"tool": "launch_dtu"}


@pytest.mark.asyncio
async def test_mount_with_none_config_uses_empty_dict():
    """mount(coordinator, None) does not raise and still registers the tool."""
    coordinator = MagicMock()

    async def async_mount(*args, **kwargs):
        return None

    coordinator.mount = MagicMock(side_effect=async_mount)

    result = await mount(coordinator, None)

    assert result == {"tool": "launch_dtu"}
    coordinator.mount.assert_called_once()
