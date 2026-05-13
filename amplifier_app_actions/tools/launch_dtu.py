"""Launch DTU tool — provision and interact with a Digital Twin Universe instance."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

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

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.github_token: str = config.get("github_token") or os.environ.get(
            "GITHUB_TOKEN", ""
        )

    @property
    def name(self) -> str:
        return "launch_dtu"

    @property
    def description(self) -> str:
        return (
            "Launch a Digital Twin Universe instance for integration testing. "
            "Clones one or more GitHub repositories into /workspace/<repo> and "
            "runs the provided commands inside an isolated Ubuntu 24.04 container. "
            "Each repo is specified as 'owner/repo' (default branch) or "
            "'owner/repo@ref' where ref is a branch, tag, or SHA."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of repositories to clone, each as 'owner/repo' or "
                        "'owner/repo@ref' (branch, tag, or SHA)."
                    ),
                },
                "commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Shell commands to run inside the container.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional description for the DTU session.",
                },
            },
            "required": ["repos", "commands"],
        }

    def _generate_profile(self, repos: list[str], commands: list[str]) -> str:
        """Generate a minimal DTU profile YAML using string formatting.

        Parameters
        ----------
        repos:
            List of repo specs in 'owner/repo' or 'owner/repo@ref' format.
        commands:
            Shell commands to run inside the container.

        Returns
        -------
        str
            A YAML string suitable for use as a DTU profile.
        """
        setup_cmds: list[str] = ["apt-get update -qq && apt-get install -y -q git"]

        for spec in repos:
            owner, repo, ref = _parse_repo(spec)
            url = f"https://x-access-token:${{GITHUB_TOKEN}}@github.com/{owner}/{repo}"
            dest = f"/workspace/{repo}"

            if ref is None:
                clone_cmd = f"git clone --depth 1 {url} {dest}"
            elif _is_sha(ref):
                clone_cmd = f"git clone {url} {dest} && git -C {dest} checkout {ref}"
            else:
                clone_cmd = f"git clone --depth 1 --branch {ref} {url} {dest}"

            setup_cmds.append(clone_cmd)

        setup_cmds_yaml = "\n".join(f"  - {cmd}" for cmd in setup_cmds)
        commands_yaml = "\n".join(f"  - {cmd}" for cmd in commands)

        return (
            "base_image: ubuntu:24.04\n"
            "allow_external: true\n"
            "env:\n"
            "  passthrough:\n"
            "    - GITHUB_TOKEN\n"
            "    - ANTHROPIC_API_KEY\n"
            "setup_cmds:\n"
            f"{setup_cmds_yaml}\n"
            "commands:\n"
            f"{commands_yaml}\n"
        )

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        repos: list[str] = input_data.get("repos", [])
        commands: list[str] = input_data.get("commands", [])

        profile_yaml = self._generate_profile(repos, commands)
        profile_path = f"/tmp/dtu-repro-{uuid4()}.yaml"
        Path(profile_path).write_text(profile_yaml)

        instance_id: str | None = None
        outputs: list[dict[str, Any]] = []

        try:
            # 1. Launch
            try:
                launch_result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "amplifier-digital-twin",
                        "launch",
                        profile_path,
                        "--format",
                        "json",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                safe_stderr = re.sub(
                    r"x-access-token:[^@]+@",
                    "x-access-token:***@",
                    exc.stderr or "",
                )
                return ToolResult(
                    success=False,
                    output=safe_stderr,
                    error={"returncode": exc.returncode, "stderr": safe_stderr},
                )

            instance_id = json.loads(launch_result.stdout)["instance_id"]

            # 2. Exec each command
            for cmd in commands:
                exec_result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "amplifier-digital-twin",
                        "exec",
                        instance_id,
                        "--",
                        "bash",
                        "-c",
                        cmd,
                    ],
                    capture_output=True,
                    text=True,
                )
                outputs.append(
                    {
                        "command": cmd,
                        "stdout": exec_result.stdout,
                        "stderr": exec_result.stderr,
                        "returncode": exec_result.returncode,
                    }
                )

            return ToolResult(
                success=all(o["returncode"] == 0 for o in outputs),
                output={"instance_id": instance_id, "outputs": outputs},
            )

        finally:
            if instance_id is not None:
                await asyncio.to_thread(
                    subprocess.run,
                    ["amplifier-digital-twin", "destroy", instance_id],
                    capture_output=True,
                    text=True,
                )
            Path(profile_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Mount
# ---------------------------------------------------------------------------


async def mount(
    coordinator: ModuleCoordinator,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Instantiate and register LaunchDTUTool with the coordinator."""
    tool = LaunchDTUTool(config or {})
    await coordinator.mount("tools", tool, name=tool.name)
    return {"tool": tool.name}
