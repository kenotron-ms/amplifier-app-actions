"""Launch DTU tool — provision and interact with a Digital Twin Universe instance."""

from __future__ import annotations

import asyncio  # noqa: F401
import json  # noqa: F401
import os  # noqa: F401
import re
import subprocess  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any
from uuid import uuid4  # noqa: F401

from amplifier_core import ModuleCoordinator, ToolResult  # type: ignore[import]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_repo(spec: str) -> tuple[str, str, str | None]:
    """Parse an 'owner/repo[@ref]' specification into its components.

    Uses ``rsplit('@', 1)`` so branch names that contain '/' (e.g.
    ``feat/my-branch``) are handled correctly — only the *last* '@' is used
    as the delimiter.

    Parameters
    ----------
    spec:
        A string of the form ``owner/repo`` or ``owner/repo@ref`` where *ref*
        can be a tag (``v1.2.3``), branch (``main``), branch-with-slash
        (``feat/my-branch``), or SHA (``abc1234``).

    Returns
    -------
    tuple[str, str, str | None]
        ``(owner, repo, ref)`` where *ref* is ``None`` when no ``@`` suffix
        is present.
    """
    if "@" in spec:
        repo_part, ref = spec.rsplit("@", 1)
    else:
        repo_part, ref = spec, None

    owner, repo = repo_part.split("/", 1)
    return owner, repo, ref


def _is_sha(ref: str) -> bool:
    """Return True if *ref* looks like a Git commit SHA (hex string, ≥7 chars)."""
    return bool(re.fullmatch(r"[0-9a-f]{7,40}", ref or ""))


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class LaunchDTUTool:
    """Provision and interact with a Digital Twin Universe instance."""

    def __init__(self, config: dict[str, Any]) -> None:  # pragma: no cover
        self.config = config

    @property
    def name(self) -> str:  # pragma: no cover
        return "launch_dtu"

    @property
    def description(self) -> str:  # pragma: no cover
        return "Launch a Digital Twin Universe instance for integration testing."

    async def execute(
        self, input_data: dict[str, Any]
    ) -> ToolResult:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mount
# ---------------------------------------------------------------------------


async def mount(
    coordinator: ModuleCoordinator,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:  # pragma: no cover
    """Instantiate and register LaunchDTUTool with the coordinator."""
    tool = LaunchDTUTool(config or {})
    await coordinator.mount("tools", tool, name=tool.name)
    return {"tool": tool.name}
