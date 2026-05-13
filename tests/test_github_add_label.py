"""Tests for amplifier_app_actions.tools.github_add_label — GitHubAddLabelTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import respx

from amplifier_app_actions.tools.github_add_label import (
    GitHubAddLabelTool,
    mount,
)

# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


def test_tool_name():
    """name property returns 'github_add_label'."""
    tool = GitHubAddLabelTool({"github_token": "test-token"})
    assert tool.name == "github_add_label"


def test_input_schema_requires_4_fields_including_label():
    """input_schema.required contains exactly the 4 expected fields including 'label'."""
    tool = GitHubAddLabelTool({"github_token": "test-token"})
    required = tool.input_schema.get("required", [])
    assert set(required) == {"owner", "repo", "issue_number", "label"}


# ---------------------------------------------------------------------------
# execute() — success path
# ---------------------------------------------------------------------------


async def test_posts_to_correct_labels_endpoint():
    """execute() POSTs to /repos/{owner}/{repo}/issues/{number}/labels endpoint."""
    tool = GitHubAddLabelTool({"github_token": "test-token"})

    async with respx.mock:
        route = respx.post(
            "https://api.github.com/repos/owner/repo/issues/42/labels"
        ).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "name": "bug",
                        "url": "https://api.github.com/repos/owner/repo/labels/bug",
                    }
                ],
            )
        )

        result = await tool.execute(
            {"owner": "owner", "repo": "repo", "issue_number": 42, "label": "bug"}
        )

    assert route.called
    assert result.success is True


async def test_github_api_url_override_respected(monkeypatch):
    """GITHUB_API_URL env var redirects the POST to the overridden base URL."""
    monkeypatch.setenv("GITHUB_API_URL", "http://localhost:3000/api/v1")
    tool = GitHubAddLabelTool({"github_token": "test-token"})

    async with respx.mock:
        route = respx.post(
            "http://localhost:3000/api/v1/repos/owner/repo/issues/7/labels"
        ).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "name": "feature-request",
                        "url": "http://localhost:3000/owner/repo/labels/feature-request",
                    }
                ],
            )
        )

        result = await tool.execute(
            {
                "owner": "owner",
                "repo": "repo",
                "issue_number": 7,
                "label": "feature-request",
            }
        )

    assert route.called
    assert result.success is True


async def test_success_returns_label_and_url():
    """On success, output contains 'label' and 'url' keys."""
    tool = GitHubAddLabelTool({"github_token": "test-token"})

    async with respx.mock:
        respx.post("https://api.github.com/repos/owner/repo/issues/1/labels").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "name": "bug",
                        "url": "https://api.github.com/repos/owner/repo/labels/bug",
                    }
                ],
            )
        )

        result = await tool.execute(
            {"owner": "owner", "repo": "repo", "issue_number": 1, "label": "bug"}
        )

    assert result.success is True
    assert result.output["label"] == "bug"
    assert "url" in result.output


# ---------------------------------------------------------------------------
# execute() — failure path
# ---------------------------------------------------------------------------


async def test_422_failure_returns_success_false_with_422_in_output():
    """A 422 response returns ToolResult(success=False) with '422' in output string."""
    tool = GitHubAddLabelTool({"github_token": "test-token"})

    async with respx.mock:
        respx.post("https://api.github.com/repos/owner/repo/issues/1/labels").mock(
            return_value=httpx.Response(422, text="Unprocessable Entity")
        )

        result = await tool.execute(
            {
                "owner": "owner",
                "repo": "repo",
                "issue_number": 1,
                "label": "nonexistent-label",
            }
        )

    assert result.success is False
    assert "422" in result.output


# ---------------------------------------------------------------------------
# mount()
# ---------------------------------------------------------------------------


async def test_mount_registers_tool_and_returns_dict():
    """mount() registers the tool with coordinator and returns {'tool': 'github_add_label'}."""
    coordinator = MagicMock()
    coordinator.mount = AsyncMock(return_value=None)

    result = await mount(coordinator, {"github_token": "test-token"})

    coordinator.mount.assert_called_once()
    args, kwargs = coordinator.mount.call_args
    assert args[0] == "tools"
    assert kwargs.get("name") == "github_add_label"
    assert result is not None
    assert isinstance(result, dict)
    assert result.get("tool") == "github_add_label"
