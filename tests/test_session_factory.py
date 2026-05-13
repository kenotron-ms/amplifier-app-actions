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


async def test_create_session_mounts_all_three_github_tools():
    """create_session mounts github_post_comment, github_add_label, github_checkout_repo.

    Verified by inspecting coordinator.mount.call_args_list for name kwargs.
    """
    mock_bundle, _, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with patch("amplifier_app_actions.session_factory.load_bundle", mock_load):
        await create_session(Path("/some/bundle"), github_token="test-token")

    mounted_names = [
        c.kwargs.get("name") for c in mock_session.coordinator.mount.call_args_list
    ]
    assert "github_post_comment" in mounted_names
    assert "github_add_label" in mounted_names
    assert "github_checkout_repo" in mounted_names


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
# Context map injection tests
# ---------------------------------------------------------------------------


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
