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

    def __init__(self, config: dict[str, Any], coordinator: Any = None) -> None:
        self.config = config
        self.coordinator = coordinator
        self.github_token: str = config.get("github_token") or os.environ.get(
            "GITHUB_TOKEN", ""
        )

    @property
    def name(self) -> str:
        return "launch_dtu"

    @property
    def description(self) -> str:
        return (
            "Launch a Digital Twin Universe instance to reproduce or validate a GitHub issue "
            "in an isolated Ubuntu 24.04 container. "
            "Two modes: "
            "(1) goal mode — provide a natural-language description of what to reproduce; "
            "the tool delegates to dtu-profile-builder which figures out the environment and steps. "
            "(2) commands mode — provide exact shell commands to run; the tool clones repos and "
            "runs them directly. "
            "Repos are specified as 'owner/repo' (default branch) or 'owner/repo@ref' "
            "where ref is a branch, tag, or SHA."
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
                        "Repositories to make available, each as 'owner/repo' or "
                        "'owner/repo@ref' (branch, tag, or SHA)."
                    ),
                },
                "goal": {
                    "type": "string",
                    "description": (
                        "Natural language description of what to reproduce or validate. "
                        "Use this when you know what needs to happen but not the exact commands. "
                        "The tool will delegate to dtu-profile-builder to construct and run "
                        "the appropriate environment. "
                        "Either goal or commands must be provided."
                    ),
                },
                "commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Exact shell commands to run inside the container. "
                        "Use this when you have concrete runnable commands. "
                        "Either goal or commands must be provided."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Optional label for logging.",
                },
            },
            "required": ["repos"],
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

    async def _execute_with_goal(
        self,
        goal: str,
        repos: list[str],
        description: str,
    ) -> ToolResult:
        """Delegate to dtu-profile-builder via session.spawn for NL-driven reproduction."""
        if self.coordinator is None:
            return ToolResult(
                success=False,
                output="goal mode requires coordinator — tool was mounted without coordinator reference",
            )

        spawn = None
        try:
            spawn = self.coordinator.get_capability("session.spawn")
        except Exception:  # noqa: BLE001
            pass

        if spawn is None:
            return ToolResult(
                success=False,
                output="goal mode requires session.spawn capability to be registered",
            )

        repos_str = "\n".join(f"  - {r}" for r in repos)
        instruction = (
            "You are being invoked headlessly to reproduce a software issue in an isolated "
            "Digital Twin Universe container. Do NOT ask interactive questions. "
            "Proceed directly using your best judgment.\n\n"
            f"Reproduction goal: {goal}\n\n"
            f"Repositories to make available (clone at the specified ref):\n{repos_str}\n\n"
            "Steps:\n"
            "1. Generate a minimal DTU profile that clones the repos at their refs, "
            "passing GITHUB_TOKEN and ANTHROPIC_API_KEY as env passthrough.\n"
            "2. Launch the DTU.\n"
            "3. Run the commands needed to reproduce or validate the goal.\n"
            "4. Capture all stdout, stderr, and exit codes.\n"
            "5. Destroy the DTU.\n"
            "6. Return a structured summary: what you ran, what happened, "
            "whether reproduction succeeded, and key output lines."
        )
        if description:
            instruction += f"\n\nContext: {description}"

        try:
            result = await spawn(
                agent="digital-twin-universe:dtu-profile-builder",
                instruction=instruction,
                context_depth="none",
            )
            return ToolResult(
                success=True,
                output={"mode": "goal", "goal": goal, "repos": repos, "result": result},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                success=False,
                output=f"dtu-profile-builder delegation failed: {exc}",
                error={"error": str(exc)},
            )

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        repos: list[str] = input_data.get("repos", [])
        goal: str = input_data.get("goal", "").strip()
        commands: list[str] = input_data.get("commands", [])
        description: str = input_data.get("description", "")

        if not goal and not commands:
            return ToolResult(
                success=False,
                output="Either 'goal' (natural language) or 'commands' (shell commands) must be provided.",
            )

        if goal:
            return await self._execute_with_goal(goal, repos, description)

        # existing commands path below — unchanged

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
    tool = LaunchDTUTool(config or {}, coordinator=coordinator)
    await coordinator.mount("tools", tool, name=tool.name)
    return {"tool": tool.name}
