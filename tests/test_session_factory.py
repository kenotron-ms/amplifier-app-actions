"""Tests for amplifier_app_actions.session_factory — create_session."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from amplifier_app_actions.session_factory import create_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_chain():
    """Build a mock bundle → prepared → session chain."""
    mock_session = MagicMock()
    mock_session.coordinator = MagicMock()
    mock_session.coordinator.mount = AsyncMock()
    mock_session.coordinator.register_capability = MagicMock()

    mock_prepared = MagicMock()
    mock_prepared.create_session = AsyncMock(return_value=mock_session)
    mock_prepared.spawn = AsyncMock(return_value={"spawned": True})

    mock_bundle = MagicMock()
    mock_bundle.prepare = AsyncMock(return_value=mock_prepared)

    return mock_bundle, mock_prepared, mock_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_create_session_calls_load_bundle_with_bundle_path():
    """create_session passes bundle_path to load_bundle."""
    mock_bundle, _, _ = _make_mock_chain()
    bundle_path = Path("/some/bundle")
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(bundle_path, github_token="test-token")

    mock_load.assert_called_once_with(str(bundle_path))


async def test_create_session_chains_prepare_and_create_session():
    """create_session calls bundle.prepare() then prepared.create_session(session_cwd=...)."""
    mock_bundle, mock_prepared, _ = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="test-token")

    mock_bundle.prepare.assert_called_once()
    mock_prepared.create_session.assert_called_once()
    _, call_kwargs = mock_prepared.create_session.call_args
    assert "session_cwd" in call_kwargs


async def test_create_session_returns_session_object():
    """create_session returns the session object from prepared.create_session()."""
    mock_bundle, _, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        result = await create_session(Path("/some/bundle"), github_token="test-token")

    assert result is mock_session


async def test_create_session_does_not_mount_github_tools_programmatically():
    """GitHub tools are now registered via entry points and loaded by the bundle system.

    create_session() must NOT programmatically call coordinator.mount for any of
    the GitHub / DTU tool names — that is now done by the bundle loader during
    session.initialize(), which propagates to all child sessions automatically.
    """
    mock_bundle, _, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="test-token")

    mounted_names = [
        c.kwargs.get("name") for c in mock_session.coordinator.mount.call_args_list
    ]
    assert "github_post_comment" not in mounted_names
    assert "github_add_label" not in mounted_names
    assert "github_checkout_repo" not in mounted_names
    assert "launch_dtu" not in mounted_names


async def test_create_session_bundle_chain_and_spawn_without_tool_mounts():
    """create_session() calls the bundle chain and registers session.spawn; no tool mounts.

    Consolidates what was previously checked by the two tool-mount tests.  The
    bundle chain (load_bundle → prepare → create_session) must still run, and the
    session.spawn capability must still be registered — those responsibilities
    remain in session_factory.py.
    """
    mock_bundle, mock_prepared, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        result = await create_session(Path("/some/bundle"), github_token="test-token")

    # Bundle chain was invoked
    mock_load.assert_called_once_with(str(Path("/some/bundle")))
    mock_bundle.prepare.assert_called_once()
    mock_prepared.create_session.assert_called_once()

    # session.spawn capability is registered
    mock_session.coordinator.register_capability.assert_called_once()
    args, _ = mock_session.coordinator.register_capability.call_args
    assert args[0] == "session.spawn"
    assert callable(args[1])

    # Result is the session object
    assert result is mock_session

    # coordinator.mount was NOT called for any GitHub / DTU tool
    assert mock_session.coordinator.mount.call_count == 0


async def test_create_session_registers_session_spawn_capability():
    """create_session registers 'session.spawn' capability via coordinator.register_capability."""
    mock_bundle, _, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="test-token")

    mock_session.coordinator.register_capability.assert_called_once()
    args, _ = mock_session.coordinator.register_capability.call_args
    assert args[0] == "session.spawn"
    assert callable(args[1])


# ---------------------------------------------------------------------------
# Provider / model override tests
# ---------------------------------------------------------------------------


async def test_provider_override_sets_bundle_providers_before_prepare():
    """When provider='openai', bundle.providers is set to provider-openai before prepare()."""
    mock_bundle, mock_prepared, _ = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    providers_at_prepare_time: list = []

    async def _capture_prepare():
        providers_at_prepare_time.extend(mock_bundle.providers)
        return mock_prepared

    mock_bundle.prepare = AsyncMock(side_effect=_capture_prepare)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(
            Path("/some/bundle"), github_token="tok", provider="openai"
        )

    assert providers_at_prepare_time == [{"module": "provider-openai"}]


async def test_provider_and_model_override_include_model_config():
    """When provider='anthropic' and model='claude-opus-4-5', config includes model."""
    mock_bundle, mock_prepared, _ = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    providers_at_prepare_time: list = []

    async def _capture_prepare():
        providers_at_prepare_time.extend(mock_bundle.providers)
        return mock_prepared

    mock_bundle.prepare = AsyncMock(side_effect=_capture_prepare)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(
            Path("/some/bundle"),
            github_token="tok",
            provider="anthropic",
            model="claude-opus-4-5",
        )

    assert providers_at_prepare_time == [
        {"module": "provider-anthropic", "config": {"model": "claude-opus-4-5"}}
    ]


async def test_no_provider_skips_bundle_providers_override():
    """When provider='' (default), bundle.providers is not replaced before prepare()."""
    mock_bundle, mock_prepared, _ = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    providers_was_list_before_prepare: list[bool] = []

    async def _capture_prepare():
        # Record whether providers was set to a plain list (i.e., overridden)
        providers_was_list_before_prepare.append(
            isinstance(mock_bundle.providers, list)
        )
        return mock_prepared

    mock_bundle.prepare = AsyncMock(side_effect=_capture_prepare)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="tok")

    # providers should NOT have been replaced with a plain list when no provider given
    assert providers_was_list_before_prepare == [False]


# ---------------------------------------------------------------------------
# Token environment injection tests
# ---------------------------------------------------------------------------


async def test_create_session_injects_github_token_into_env_when_missing(monkeypatch):
    """create_session() sets GITHUB_TOKEN in os.environ when it is absent.

    This is the regression test for the 'Illegal header value b'Bearer ''
    bug: the github_token arg was accepted by create_session() but silently
    dropped, so tools that call os.environ.get('GITHUB_TOKEN') got '' and
    produced a bare 'Bearer ' header when running outside GitHub Actions.
    """
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    mock_bundle, _, _ = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="ghp_testtoken123")

    assert os.environ.get("GITHUB_TOKEN") == "ghp_testtoken123"


async def test_create_session_does_not_overwrite_existing_github_token(monkeypatch):
    """create_session() does not replace GITHUB_TOKEN when it is already set.

    In GitHub Actions the runner sets GITHUB_TOKEN automatically; the
    github_token arg should not override it (setdefault semantics).
    """
    monkeypatch.setenv("GITHUB_TOKEN", "existing-runner-token")

    mock_bundle, _, _ = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="different-token")

    assert os.environ.get("GITHUB_TOKEN") == "existing-runner-token"


async def test_create_session_does_not_set_env_when_token_is_empty(monkeypatch):
    """create_session() does not set GITHUB_TOKEN when github_token='' is given."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    mock_bundle, _, _ = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="")

    assert os.environ.get("GITHUB_TOKEN") is None


# ---------------------------------------------------------------------------
# Context map injection tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _spawn_fn shim tests
# ---------------------------------------------------------------------------


async def test_spawn_fn_resolves_namespace_agent_via_source_base_paths(tmp_path):
    """_spawn_fn resolves namespace:agent-path via bundle.source_base_paths.

    The delegate tool calls: spawn(agent="foundation:explorer", instruction="...", context_depth="recent")
    _spawn_fn should look up 'foundation' in bundle.source_base_paths, then load
    the agent .md file from {ns_base}/agents/explorer.md rather than passing the
    raw string "foundation:explorer" to load_bundle (which fails — "foundation:" is
    not a recognised URI scheme).
    """
    mock_bundle, mock_prepared, mock_session = _make_mock_chain()

    # Provide a real Path for the foundation namespace cache directory.
    foundation_base = tmp_path / "foundation-cache"
    (foundation_base / "agents").mkdir(parents=True)
    mock_bundle.source_base_paths = {"foundation": foundation_base}

    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="test-token")

    # Extract the registered _spawn_fn
    args, _ = mock_session.coordinator.register_capability.call_args
    spawn_fn = args[1]

    # Prepare a separate child bundle mock
    mock_child_bundle = MagicMock()
    mock_prepared.spawn.reset_mock()
    mock_prepared.spawn.return_value = {"spawned": True}

    mock_inner_load = AsyncMock(return_value=mock_child_bundle)

    with patch("amplifier_foundation.load_bundle", mock_inner_load):
        result = await spawn_fn(
            agent="foundation:explorer",
            instruction="investigate this issue",
            context_depth="recent",
        )

    # Should load the agent .md file from the namespace's local cache path.
    expected_agent_path = str(foundation_base / "agents" / "explorer.md")
    mock_inner_load.assert_called_once_with(expected_agent_path)

    # Should call prepared.spawn with the resolved child bundle.
    mock_prepared.spawn.assert_called_once_with(
        mock_child_bundle,
        "investigate this issue",
        parent_session=mock_session,
    )
    assert result == {"spawned": True}


async def test_spawn_fn_dtu_profile_builder_resolves_via_source_base_paths(tmp_path):
    """_spawn_fn resolves 'digital-twin-universe:dtu-profile-builder' correctly.

    This is the regression test for the bug:
        dtu-profile-builder delegation failed: No handler for URI: digital-twin-universe:dtu-profile-builder

    Previously _spawn_fn passed "digital-twin-universe:dtu-profile-builder" directly to
    load_bundle(), which tried to treat it as a URI.  The 'digital-twin-universe:' prefix
    is not a recognised URI scheme, so load_bundle raised BundleNotFoundError.

    The fix: detect namespace:agent-path format and resolve via source_base_paths.
    """
    mock_bundle, mock_prepared, mock_session = _make_mock_chain()

    dtu_base = tmp_path / "dtu-cache"
    (dtu_base / "agents").mkdir(parents=True)
    mock_bundle.source_base_paths = {"digital-twin-universe": dtu_base}

    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="test-token")

    args, _ = mock_session.coordinator.register_capability.call_args
    spawn_fn = args[1]

    mock_child_bundle = MagicMock()
    mock_inner_load = AsyncMock(return_value=mock_child_bundle)

    with patch("amplifier_foundation.load_bundle", mock_inner_load):
        await spawn_fn(
            agent="digital-twin-universe:dtu-profile-builder",
            instruction="build a DTU profile",
        )

    expected = str(dtu_base / "agents" / "dtu-profile-builder.md")
    mock_inner_load.assert_called_once_with(expected)


async def test_spawn_fn_git_uri_still_loads_directly():
    """_spawn_fn passes git+https:// URIs directly to load_bundle (no namespace lookup)."""
    mock_bundle, mock_prepared, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="test-token")

    args, _ = mock_session.coordinator.register_capability.call_args
    spawn_fn = args[1]

    mock_child_bundle = MagicMock()
    mock_inner_load = AsyncMock(return_value=mock_child_bundle)

    git_uri = "git+https://github.com/microsoft/amplifier-foundation@main"
    with patch("amplifier_foundation.load_bundle", mock_inner_load):
        await spawn_fn(agent=git_uri, instruction="use this bundle")

    # Must be passed verbatim — no source_base_paths lookup for real URIs.
    mock_inner_load.assert_called_once_with(git_uri)


async def test_spawn_fn_namespace_not_in_source_base_paths_falls_back_to_direct_load():
    """When namespace is absent from source_base_paths, fall back to direct load_bundle call."""
    mock_bundle, mock_prepared, mock_session = _make_mock_chain()
    mock_bundle.source_base_paths = {}  # empty — 'unknown-bundle' is not registered

    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="test-token")

    args, _ = mock_session.coordinator.register_capability.call_args
    spawn_fn = args[1]

    mock_child_bundle = MagicMock()
    mock_inner_load = AsyncMock(return_value=mock_child_bundle)

    with patch("amplifier_foundation.load_bundle", mock_inner_load):
        await spawn_fn(agent="unknown-bundle:some-agent", instruction="do something")

    # Falls back to direct load — will surface a clear error from the bundle loader.
    mock_inner_load.assert_called_once_with("unknown-bundle:some-agent")


async def test_spawn_fn_raises_when_no_agent_provided():
    """_spawn_fn raises ValueError if 'agent' is absent from kwargs."""
    mock_bundle, _, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="test-token")

    args, _ = mock_session.coordinator.register_capability.call_args
    spawn_fn = args[1]

    import pytest

    with pytest.raises(ValueError, match="session.spawn requires 'agent'"):
        await spawn_fn(instruction="missing agent kwarg")


async def test_create_session_injects_context_map_from_env_path(tmp_path):
    """TRIAGE_CONTEXT_MAP_PATH env var causes context map file to be injected into session config."""
    # Create a workspace map file
    map_file = tmp_path / "workspace-map.md"
    map_file.write_text(
        "# Test Workspace Map\n\n- service-api: REST API service\n- shared-lib: shared validation\n"
    )

    mock_bundle, _, mock_session = _make_mock_chain()
    # Give the session a real config dict so we can inspect it after injection
    mock_session.config = {}
    mock_load = AsyncMock(return_value=mock_bundle)

    with (
        patch("amplifier_app_actions.session_factory.load_bundle", mock_load),
        patch.dict(os.environ, {"TRIAGE_CONTEXT_MAP_PATH": str(map_file)}),
    ):
        result = await create_session(
            bundle_path=Path("/fake/bundle.md"), github_token="test-token"
        )

    assert (
        "Test Workspace Map" in str(result.config)
        or "service-api" in str(result.config).lower()
    )
