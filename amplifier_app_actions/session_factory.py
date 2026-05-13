"""Session factory — create a configured Amplifier session with GitHub tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from amplifier_foundation import load_bundle

from amplifier_app_actions.tools.github_add_label import mount as mount_add_label
from amplifier_app_actions.tools.github_checkout_repo import (
    mount as mount_checkout_repo,
)
from amplifier_app_actions.tools.github_post_comment import (
    mount as mount_post_comment,
)


async def create_session(
    bundle_path: Path,
    github_token: str,
    session_cwd: Path | None = None,
    provider: str = "",
    model: str = "",
) -> Any:
    """Load bundle, prepare it, create a session, mount GitHub tools, register spawn.

    Args:
        bundle_path: Path to the bundle to load.
        github_token: GitHub personal access token for GitHub API calls.
        session_cwd: Working directory for the session (defaults to Path.cwd()).
        provider: AI provider name override (e.g. 'anthropic', 'openai').
            When set, replaces the bundle's providers list with a single entry
            using the module name ``provider-<provider>``.
        model: Model name override (empty string means use bundle/provider default).
            Only applied when ``provider`` is also set.

    Returns:
        Configured AmplifierSession with GitHub tools mounted.
    """
    if session_cwd is None:
        session_cwd = Path.cwd()

    bundle = await load_bundle(bundle_path)

    # Apply provider/model overrides before prepare() compiles the mount plan.
    if provider:
        entry: dict[str, Any] = {"module": f"provider-{provider}"}
        if model:
            entry["config"] = {"model": model}
        bundle.providers = [entry]

    prepared = await bundle.prepare()
    session = await prepared.create_session(session_cwd=session_cwd)

    async def _spawn_fn(**kwargs: Any) -> Any:
        return await prepared.spawn(**kwargs)

    session.coordinator.register_capability("session.spawn", _spawn_fn)

    tool_config: dict[str, Any] = {"github_token": github_token}
    await mount_post_comment(session.coordinator, tool_config)
    await mount_add_label(session.coordinator, tool_config)
    await mount_checkout_repo(session.coordinator, tool_config)

    return session
