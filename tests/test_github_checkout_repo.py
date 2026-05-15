"""Tests for amplifier_app_actions.tools.github_checkout_repo — GitHubCheckoutRepoTool."""

from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock

from amplifier_app_actions.tools.github_checkout_repo import (
    GitHubCheckoutRepoTool,
    mount,
)

# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


def test_tool_name():
    """name property returns 'github_checkout_repo'."""
    tool = GitHubCheckoutRepoTool({})
    assert tool.name == "github_checkout_repo"


def test_input_schema_requires_owner_and_repo_not_ref():
    """input_schema.required contains owner and repo; ref is optional (not required)."""
    tool = GitHubCheckoutRepoTool({})
    required = tool.input_schema.get("required", [])
    assert "owner" in required
    assert "repo" in required
    assert "ref" not in required


# ---------------------------------------------------------------------------
# execute() — success path
# ---------------------------------------------------------------------------


async def test_git_clone_called_with_correct_args(monkeypatch):
    """execute() runs git clone --depth 1 --filter=blob:none with correct URL and dest."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # ensure no token in URL
    tool = GitHubCheckoutRepoTool({})
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)

    monkeypatch.setattr("subprocess.run", fake_run)

    result = await tool.execute({"owner": "test-org", "repo": "test-repo"})

    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[0] == "git"
    assert "clone" in cmd
    assert "--depth" in cmd
    assert "1" in cmd
    assert "--filter=blob:none" in cmd
    assert "https://github.com/test-org/test-repo" in cmd
    assert "/tmp/workspace/test-repo" in cmd
    assert result.success is True


async def test_github_clone_url_override_redirects_clone(monkeypatch):
    """GITHUB_CLONE_URL=http://localhost:3000 redirects clone to localhost:3000/test-org/test-repo."""
    monkeypatch.setenv("GITHUB_CLONE_URL", "http://localhost:3000")
    tool = GitHubCheckoutRepoTool({})
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)

    monkeypatch.setattr("subprocess.run", fake_run)

    result = await tool.execute({"owner": "test-org", "repo": "test-repo"})

    assert len(captured) == 1
    cmd = captured[0]
    assert "http://localhost:3000/test-org/test-repo" in cmd
    assert result.success is True


async def test_branch_flag_added_when_ref_provided(monkeypatch):
    """execute() appends --branch <ref> to the git clone command when ref is given."""
    tool = GitHubCheckoutRepoTool({})
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)

    monkeypatch.setattr("subprocess.run", fake_run)

    await tool.execute({"owner": "test-org", "repo": "test-repo", "ref": "my-branch"})

    cmd = captured[0]
    assert "--branch" in cmd
    branch_idx = cmd.index("--branch")
    assert cmd[branch_idx + 1] == "my-branch"


async def test_success_result_contains_path_owner_repo_ref(monkeypatch):
    """On success, output contains 'path', 'owner', 'repo', and 'ref' keys."""
    tool = GitHubCheckoutRepoTool({})
    monkeypatch.setattr("subprocess.run", lambda cmd, **kwargs: None)

    result = await tool.execute(
        {"owner": "test-org", "repo": "test-repo", "ref": "main"}
    )

    assert result.success is True
    assert result.output["path"] == "/tmp/workspace/test-repo"
    assert result.output["owner"] == "test-org"
    assert result.output["repo"] == "test-repo"
    assert result.output["ref"] == "main"


# ---------------------------------------------------------------------------
# execute() — failure path
# ---------------------------------------------------------------------------


async def test_called_process_error_returns_success_false(monkeypatch):
    """CalledProcessError returns success=False with '128' or 'repository not found' in output."""
    tool = GitHubCheckoutRepoTool({})

    def fake_run_error(cmd, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=128,
            cmd=cmd,
            stderr="repository not found",
        )

    monkeypatch.setattr("subprocess.run", fake_run_error)

    result = await tool.execute({"owner": "test-org", "repo": "missing-repo"})

    assert result.success is False
    assert "128" in result.output or "repository not found" in result.output


# ---------------------------------------------------------------------------
# mount()
# ---------------------------------------------------------------------------


async def test_mount_registers_tool_returns_dict():
    """mount() registers the tool with coordinator and returns {'tool': 'github_checkout_repo'}."""
    coordinator = MagicMock()
    coordinator.mount = AsyncMock(return_value=None)

    result = await mount(coordinator, {})

    coordinator.mount.assert_called_once()
    args, kwargs = coordinator.mount.call_args
    assert args[0] == "tools"
    assert kwargs.get("name") == "github_checkout_repo"
    assert isinstance(result, dict)
    assert result.get("tool") == "github_checkout_repo"


# ---------------------------------------------------------------------------
# _build_clone_url() — token embedding logic
# ---------------------------------------------------------------------------


def test_build_clone_url_token_and_github_embeds_token():
    """Token present + default GitHub URL → x-access-token:{token}@ embedded in clone URL."""
    tool = GitHubCheckoutRepoTool({"github_token": "ghp_test123"})
    url = tool._build_clone_url("my-org", "my-repo")
    assert url == "https://x-access-token:ghp_test123@github.com/my-org/my-repo"


def test_build_clone_url_token_and_custom_url_no_token_embedded(monkeypatch):
    """Token present + custom Gitea/DTU URL → token NOT embedded in clone URL."""
    monkeypatch.setenv("GITHUB_CLONE_URL", "http://localhost:3000")
    tool = GitHubCheckoutRepoTool({"github_token": "ghp_test123"})
    url = tool._build_clone_url("my-org", "my-repo")
    assert url == "http://localhost:3000/my-org/my-repo"
    assert "ghp_test123" not in url


def test_build_clone_url_no_token_plain_github_url(monkeypatch):
    """No token + default GitHub URL → plain https://github.com/... (no auth prefix)."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    tool = GitHubCheckoutRepoTool({})
    url = tool._build_clone_url("my-org", "my-repo")
    assert url == "https://github.com/my-org/my-repo"


# ---------------------------------------------------------------------------
# execute() — security: token must not leak in error output
# ---------------------------------------------------------------------------


async def test_failed_clone_does_not_leak_token_in_output(monkeypatch):
    """Token must not appear in ToolResult when git clone fails."""
    monkeypatch.delenv("GITHUB_CLONE_URL", raising=False)
    tool = GitHubCheckoutRepoTool({"github_token": "ghp_secret"})

    def fake_run_error(cmd, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=128,
            cmd=cmd,
            stderr="fatal: repository 'https://x-access-token:ghp_secret@github.com/org/repo/' not found",
        )

    monkeypatch.setattr("subprocess.run", fake_run_error)

    result = await tool.execute({"owner": "org", "repo": "repo"})

    assert result.success is False
    assert "ghp_secret" not in result.output
    assert "ghp_secret" not in result.error["stderr"]
    assert "x-access-token:***@" in result.output
