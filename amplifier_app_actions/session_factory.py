"""Session factory — create a configured Amplifier session with GitHub tools."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx
import amplifier_app_actions.tools as _tools_pkg
from amplifier_foundation import load_bundle

_TOOLS_DIR = Path(_tools_pkg.__file__).parent

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
    """Load bundle, prepare it, create a session, and register spawn.

    GitHub tools (github_post_comment, github_add_label, github_checkout_repo,
    launch_dtu) are injected into bundle.tools before prepare() so the bundle
    loader mounts them during session.initialize().  They propagate automatically
    to all child sessions spawned via session.spawn without needing entry points.

    Args:
        bundle_path: Path to the bundle to load.
        github_token: GitHub personal access token (kept for backward-compatibility;
            tools now read credentials from environment variables at call time).
        session_cwd: Working directory for the session (defaults to Path.cwd()).
        provider: AI provider name override (e.g. 'anthropic', 'openai').
            When set, replaces the bundle's providers list with a single entry
            using the module name ``provider-<provider>``.
        model: Model name override (empty string means use bundle/provider default).
            Only applied when ``provider`` is also set.

    Returns:
        Configured AmplifierSession with session.spawn registered.
    """
    if session_cwd is None:
        session_cwd = Path.cwd()

    bundle = await load_bundle(str(bundle_path))

    # Apply provider/model overrides before prepare() compiles the mount plan.
    if provider:
        module_name = f"provider-{provider}"
        # Start from the full pre-configured bundle entry so source and any
        # default config (e.g. raw: true) survive when we replace the list.
        matching = next(
            (p for p in (bundle.providers or []) if p.get("module") == module_name),
            None,
        )
        entry: dict[str, Any] = dict(matching) if matching else {"module": module_name}
        if model:
            # Merge into config rather than replacing it wholesale so provider-specific
            # flags (e.g. raw: true) are not discarded.
            cfg = dict(entry.get("config") or {})
            cfg["model"] = model
            entry["config"] = cfg
        bundle.providers = [entry]

    # Add GitHub tools to the bundle mount plan BEFORE prepare()
    # This ensures they propagate to all child sessions (recipe sub-agents, etc.)
    _GITHUB_TOOLS = [
        "github_post_comment",
        "github_add_label",
        "github_checkout_repo",
        "launch_dtu",
    ]
    if bundle.tools is None:
        bundle.tools = []
    for tool_name in _GITHUB_TOOLS:
        module_name = f"tool-{tool_name.replace('_', '-')}"
        # Only add if not already in the list
        if not any(t.get("module") == module_name for t in bundle.tools):
            bundle.tools.append(
                {
                    "module": module_name,
                    "source": str(_TOOLS_DIR / tool_name),
                }
            )

    prepared = await bundle.prepare()
    session = await prepared.create_session(session_cwd=session_cwd)

    async def _spawn_fn(**kwargs: Any) -> Any:
        return await prepared.spawn(**kwargs)

    session.coordinator.register_capability("session.spawn", _spawn_fn)

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
