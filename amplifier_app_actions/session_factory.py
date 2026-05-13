"""Session factory — create a configured Amplifier session with GitHub tools."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx
from amplifier_foundation import load_bundle

from amplifier_app_actions.tools.github_add_label import mount as mount_add_label
from amplifier_app_actions.tools.github_checkout_repo import (
    mount as mount_checkout_repo,
)
from amplifier_app_actions.tools.github_post_comment import (
    mount as mount_post_comment,
)

_log = logging.getLogger(__name__)

_DEFAULT_CONTEXT_MAP_URL = (
    "https://raw.githubusercontent.com/microsoft/amplifier/main/MODULES.md"
)


async def _load_context_map() -> str:
    """Load the project workspace map from a local file or remote URL.

    If TRIAGE_CONTEXT_MAP_PATH env var is set, reads from disk.
    Otherwise fetches from _DEFAULT_CONTEXT_MAP_URL.
    Returns an empty string on any failure (non-fatal).
    """
    env_path = os.environ.get("TRIAGE_CONTEXT_MAP_PATH", "")
    if env_path:
        try:
            return Path(env_path).read_text(encoding="utf-8")
        except OSError as exc:
            _log.warning("Could not read TRIAGE_CONTEXT_MAP_PATH %r: %s", env_path, exc)
            return ""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_DEFAULT_CONTEXT_MAP_URL)
            response.raise_for_status()
            return response.text
    except Exception as exc:  # noqa: BLE001
        _log.debug(
            "Could not fetch context map from %r: %s", _DEFAULT_CONTEXT_MAP_URL, exc
        )
        return ""


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

    bundle = await load_bundle(str(bundle_path))

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

    context_map = await _load_context_map()
    if context_map:
        session.config["initial_context"] = (
            "# Project Workspace Map\n\n"
            "The following describes all known repos in this project's ecosystem. "
            "Use this to determine which repos are relevant when investigating "
            "cross-repo issues.\n\n" + context_map
        )
        _log.debug(
            "Injected context map into session config (%d chars)", len(context_map)
        )

    return session
