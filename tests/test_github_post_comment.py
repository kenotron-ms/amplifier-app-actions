"""Tests for amplifier_app_actions.tools.github_post_comment — GitHubPostCommentTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import respx

from amplifier_app_actions.tools.github_post_comment import (
    GitHubPostCommentTool,
    mount,
)

# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


def test_tool_name():
    """name property returns 'github_post_comment'."""
    tool = GitHubPostCommentTool({"github_token": "test-token"})
    assert tool.name == "github_post_comment"


def test_description_length_greater_than_10():
    """description property is a meaningful string (len > 10)."""
    tool = GitHubPostCommentTool({"github_token": "test-token"})
    assert len(tool.description) > 10


def test_input_schema_requires_4_fields():
    """input_schema.required contains exactly the 4 expected fields."""
    tool = GitHubPostCommentTool({"github_token": "test-token"})
    required = tool.input_schema.get("required", [])
    assert set(required) == {"owner", "repo", "issue_number", "body"}


# ---------------------------------------------------------------------------
# execute() — success path
# ---------------------------------------------------------------------------


async def test_201_returns_success_true_with_comment_id():
    """A 201 response returns ToolResult(success=True) with comment_id in output."""
    tool = GitHubPostCommentTool({"github_token": "test-token"})

    async with respx.mock:
        respx.post("https://api.github.com/repos/owner/repo/issues/1/comments").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 42,
                    "html_url": "https://github.com/owner/repo/issues/1#issuecomment-42",
                    "url": "https://api.github.com/repos/owner/repo/issues/comments/42",
                },
            )
        )

        result = await tool.execute(
            {"owner": "owner", "repo": "repo", "issue_number": 1, "body": "Hello"}
        )

    assert result.success is True
    assert result.output["comment_id"] == 42


async def test_authorization_bearer_header_sent():
    """execute() sends Authorization: Bearer <token> in the request headers."""
    tool = GitHubPostCommentTool({"github_token": "my-secret-token"})

    async with respx.mock:
        route = respx.post(
            "https://api.github.com/repos/owner/repo/issues/1/comments"
        ).mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 1,
                    "html_url": "https://github.com/owner/repo/issues/1#issuecomment-1",
                },
            )
        )

        await tool.execute(
            {"owner": "owner", "repo": "repo", "issue_number": 1, "body": "Hello"}
        )

    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer my-secret-token"


async def test_github_api_url_env_redirects_request(monkeypatch):
    """GITHUB_API_URL=http://localhost:3000/api/v1 redirects the POST to that base (DTU support)."""
    monkeypatch.setenv("GITHUB_API_URL", "http://localhost:3000/api/v1")
    # Instantiate AFTER setting the env var so base_url picks it up
    tool = GitHubPostCommentTool({"github_token": "test-token"})

    async with respx.mock:
        route = respx.post(
            "http://localhost:3000/api/v1/repos/owner/repo/issues/1/comments"
        ).mock(
            return_value=httpx.Response(
                201,
                json={"id": 7, "html_url": "http://localhost:3000/owner/repo/issues/1"},
            )
        )

        result = await tool.execute(
            {"owner": "owner", "repo": "repo", "issue_number": 1, "body": "Hello"}
        )

    assert route.called
    assert result.success is True


# ---------------------------------------------------------------------------
# execute() — failure path
# ---------------------------------------------------------------------------


async def test_401_returns_success_false_with_status_in_output():
    """A 401 response returns ToolResult(success=False) with '401' in output string."""
    tool = GitHubPostCommentTool({"github_token": "bad-token"})

    async with respx.mock:
        respx.post("https://api.github.com/repos/owner/repo/issues/1/comments").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        result = await tool.execute(
            {"owner": "owner", "repo": "repo", "issue_number": 1, "body": "Hello"}
        )

    assert result.success is False
    assert "401" in result.output


# ---------------------------------------------------------------------------
# mount()
# ---------------------------------------------------------------------------


async def test_mount_calls_coordinator_mount_with_tools_and_name():
    """mount() calls coordinator.mount('tools', tool, name='github_post_comment')."""
    coordinator = MagicMock()
    coordinator.mount = AsyncMock(return_value=None)

    await mount(coordinator, {"github_token": "test-token"})

    coordinator.mount.assert_called_once()
    args, kwargs = coordinator.mount.call_args
    assert args[0] == "tools"
    assert kwargs.get("name") == "github_post_comment"


async def test_mount_returns_dict_with_tool_name():
    """mount() returns a non-None dict containing the tool name."""
    coordinator = MagicMock()
    coordinator.mount = AsyncMock(return_value=None)

    result = await mount(coordinator, {"github_token": "test-token"})

    assert result is not None
    assert isinstance(result, dict)
    assert result.get("tool") == "github_post_comment"
