"""GitHub post comment tool — POST a comment to a GitHub issue or pull request."""

from __future__ import annotations

import os
from typing import Any

import httpx

from amplifier_core import ModuleCoordinator, ToolResult


class GitHubPostCommentTool:
    """Post a Markdown comment to a GitHub issue or pull request via the GitHub REST API."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.github_token: str = config.get("github_token") or os.environ.get(
            "GITHUB_TOKEN", ""
        )
        self.base_url: str = os.environ.get("GITHUB_API_URL", "https://api.github.com")

    @property
    def name(self) -> str:
        return "github_post_comment"

    @property
    def description(self) -> str:
        return (
            "Post a comment to a GitHub issue or pull request. "
            "Required inputs: owner (str) — repository owner or org; "
            "repo (str) — repository name; "
            "issue_number (int) — issue or PR number; "
            "body (str) — comment text (Markdown supported)."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner (user or organisation login).",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository name.",
                },
                "issue_number": {
                    "type": "integer",
                    "description": "The issue or pull request number to comment on.",
                },
                "body": {
                    "type": "string",
                    "description": "Comment body text. Markdown is supported.",
                },
            },
            "required": ["owner", "repo", "issue_number", "body"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        """Post a comment and return a ToolResult with comment_id and url on success."""
        owner: str = input_data["owner"]
        repo: str = input_data["repo"]
        issue_number: int = input_data["issue_number"]
        body: str = input_data["body"]

        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={"body": body}, headers=headers)

        if response.status_code not in (200, 201):
            return ToolResult(
                success=False,
                output=f"Failed to post comment: HTTP {response.status_code}",
                error={
                    "status_code": response.status_code,
                    "body": response.text,
                },
            )

        data: dict[str, Any] = response.json()
        return ToolResult(
            success=True,
            output={
                "comment_id": data.get("id"),
                "url": data.get("html_url"),
            },
        )


async def mount(
    coordinator: ModuleCoordinator,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Instantiate and register GitHubPostCommentTool with the coordinator."""
    tool = GitHubPostCommentTool(config or {})
    await coordinator.mount("tools", tool, name=tool.name)
    return {"tool": tool.name}
