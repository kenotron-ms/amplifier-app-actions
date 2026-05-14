"""GitHub checkout repo tool — shallow clone a GitHub repository into /tmp/workspace."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from amplifier_core import ModuleCoordinator, ToolResult


class GitHubCheckoutRepoTool:
    """Shallow clone a GitHub repository into /tmp/workspace/{repo}."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.github_token: str = config.get("github_token") or os.environ.get(
            "GITHUB_TOKEN", ""
        )
        self.clone_base_url: str = os.environ.get(
            "GITHUB_CLONE_URL", "https://github.com"
        )

    @property
    def name(self) -> str:
        return "github_checkout_repo"

    @property
    def description(self) -> str:
        return (
            "Shallow clone a GitHub repository into /tmp/workspace/{repo}. "
            "Reads the MODULES.md context block to understand repository layout. "
            "Use GITHUB_CLONE_URL env var to redirect clones to a Gitea DTU instance. "
            "Required inputs: owner (str) — repository owner or org; "
            "repo (str) — repository name. "
            "Optional inputs: ref (str) — branch, tag, or commit ref to clone (defaults to HEAD)."
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
                "ref": {
                    "type": "string",
                    "description": "Branch, tag, or commit ref to clone (defaults to HEAD).",
                },
            },
            "required": ["owner", "repo"],
        }

    def _build_clone_url(self, owner: str, repo: str) -> str:
        """Return the git clone URL, embedding a token for github.com when available."""
        if self.github_token and self.clone_base_url == "https://github.com":
            return (
                f"https://x-access-token:{self.github_token}@github.com/{owner}/{repo}"
            )
        return f"{self.clone_base_url}/{owner}/{repo}"

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        """Shallow clone the repository and return ToolResult with path metadata."""
        owner: str = input_data["owner"]
        repo: str = input_data["repo"]
        ref: str | None = input_data.get("ref")

        clone_url = self._build_clone_url(owner, repo)
        dest = Path(f"/tmp/workspace/{repo}")

        cmd: list[str] = ["git", "clone", "--depth", "1", "--filter=blob:none"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [clone_url, str(dest)]

        try:
            await asyncio.to_thread(
                subprocess.run, cmd, check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as exc:
            safe_stderr = re.sub(
                r"x-access-token:[^@]+@",
                "x-access-token:***@",
                exc.stderr,
            )
            return ToolResult(
                success=False,
                output=f"git clone failed (exit {exc.returncode}): {safe_stderr}",
                error={"returncode": exc.returncode, "stderr": safe_stderr},
            )

        return ToolResult(
            success=True,
            output={
                "path": str(dest),
                "owner": owner,
                "repo": repo,
                "ref": ref,
            },
        )


async def mount(
    coordinator: ModuleCoordinator,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Instantiate and register GitHubCheckoutRepoTool with the coordinator."""
    tool = GitHubCheckoutRepoTool(config or {})
    await coordinator.mount("tools", tool, name=tool.name)
    return {"tool": tool.name}
