"""GitHub add label tool — POST a label to a GitHub issue or pull request."""

from __future__ import annotations

import os
from typing import Any

import httpx

from amplifier_core import ModuleCoordinator, ToolResult


class GitHubAddLabelTool:
    """Add a label to a GitHub issue or pull request via the GitHub REST API."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.github_token: str = config.get("github_token") or os.environ.get(
            "GITHUB_TOKEN", ""
        )
        self.base_url: str = os.environ.get("GITHUB_API_URL", "https://api.github.com")

    @property
    def name(self) -> str:
        return "github_add_label"

    @property
    def description(self) -> str:
        return (
            "Add a label to a GitHub issue or pull request. "
            "The label must already exist in the repository. "
            "Common label values: bug, feature-request, question, documentation, "
            "needs-investigation, high-priority. "
            "Required inputs: owner (str) — repository owner or org; "
            "repo (str) — repository name; "
            "issue_number (int) — issue or PR number; "
            "label (str) — name of the label to add."
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
                    "description": "The issue or pull request number to label.",
                },
                "label": {
                    "type": "string",
                    "description": (
                        "Name of the label to add. Common values: bug, feature-request, "
                        "question, documentation, needs-investigation, high-priority."
                    ),
                },
            },
            "required": ["owner", "repo", "issue_number", "label"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        """Add a label to an issue/PR and return a ToolResult on success."""
        owner: str = input_data["owner"]
        repo: str = input_data["repo"]
        issue_number: int = input_data["issue_number"]
        label: str = input_data["label"]

        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/labels"
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={"labels": [label]}, headers=headers)

        if response.status_code not in (200, 201):
            return ToolResult(
                success=False,
                output=f"Failed to add label: HTTP {response.status_code}",
                error={
                    "status_code": response.status_code,
                    "body": response.text,
                },
            )

        return ToolResult(
            success=True,
            output={
                "label": label,
                "url": url,
            },
        )


async def mount(
    coordinator: ModuleCoordinator,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Instantiate and register GitHubAddLabelTool with the coordinator."""
    tool = GitHubAddLabelTool(config or {})
    await coordinator.mount("tools", tool, name=tool.name)
    return {"tool": tool.name}
