"""GitHub post/update comment tool.

Creates a new comment on a GitHub issue or PR, or updates an existing one.
Pass comment_id to update; omit it to create.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from amplifier_core import ModuleCoordinator, ToolResult


class GitHubPostCommentTool:
    """Post or update a Markdown comment on a GitHub issue or pull request.

    - Omit comment_id to CREATE a new comment (POST).
    - Pass comment_id to UPDATE an existing comment (PATCH).

    Always returns comment_id so callers can pass it back to update later.
    Use this to keep a single comment per run rather than creating noise.
    """

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
            "Post or update a comment on a GitHub issue or pull request. "
            "Omit comment_id to CREATE a new comment; pass comment_id to UPDATE "
            "an existing one. Always returns comment_id — pass it back on the "
            "next call to keep a single comment per run instead of creating noise. "
            "Required for create: owner, repo, issue_number, body. "
            "Required for update: owner, repo, comment_id, body "
            "(issue_number not needed when updating)."
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
                    "description": (
                        "The issue or pull request number. "
                        "Required when creating a new comment; ignored when updating."
                    ),
                },
                "body": {
                    "type": "string",
                    "description": "Comment body text. Markdown is supported.",
                },
                "comment_id": {
                    "type": "integer",
                    "description": (
                        "If provided, UPDATE this existing comment instead of "
                        "creating a new one. Use the comment_id returned by a "
                        "previous call to this tool."
                    ),
                },
            },
            "required": ["owner", "repo", "body"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        """Create or update a comment and return comment_id and url."""
        owner: str = input_data["owner"]
        repo: str = input_data["repo"]
        body: str = input_data["body"]
        comment_id: int | None = input_data.get("comment_id")
        issue_number: int | None = input_data.get("issue_number")

        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient() as client:
            if comment_id is not None:
                # UPDATE existing comment
                url = (
                    f"{self.base_url}/repos/{owner}/{repo}/issues/comments/{comment_id}"
                )
                response = await client.patch(url, json={"body": body}, headers=headers)
            else:
                # CREATE new comment
                if not issue_number:
                    return ToolResult(
                        success=False,
                        output="issue_number is required when creating a new comment.",
                    )
                url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"
                response = await client.post(url, json={"body": body}, headers=headers)

        if response.status_code not in (200, 201):
            return ToolResult(
                success=False,
                output=f"Failed: HTTP {response.status_code}",
                error={"status_code": response.status_code, "body": response.text},
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
