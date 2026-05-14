"""Session factory — create a configured Amplifier session with GitHub tools."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx
from amplifier_app_cli.session_runner import register_mention_handling
from amplifier_app_cli.session_runner import register_session_spawning
from amplifier_foundation import load_bundle

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
    launch_dtu) are now declared as entry points in pyproject.toml and listed in
    bundle.md.  The bundle loader mounts them during session.initialize(), so they
    propagate automatically to all child sessions spawned via session.spawn.

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

    # Propagate the token into the environment so GitHub tools can read it via
    # os.environ.get("GITHUB_TOKEN").  Tools are mounted by the bundle loader
    # and read credentials from the environment at call time; the github_token
    # argument never reaches them otherwise.  setdefault avoids overwriting a
    # token that was already set (e.g. by the GitHub Actions runner itself).
    if github_token:
        os.environ.setdefault("GITHUB_TOKEN", github_token)

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

    prepared = await bundle.prepare()
    session = await prepared.create_session(session_cwd=session_cwd)

    # Wire up the standard CLI spawn + mention machinery.
    # - register_mention_handling: wraps foundation's bundle resolver with app
    #   shortcuts (@user:, @project:, @~/) for @-mention resolution.
    # - register_session_spawning: registers session.spawn + session.resume using
    #   spawn_sub_session(), which creates child sessions as config overlays on the
    #   parent (not as separate bundle loads), so the parent's restricted tool
    #   surface is inherited by all delegated agents — tool-gating is preserved.
    register_mention_handling(session)
    register_session_spawning(session)

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
