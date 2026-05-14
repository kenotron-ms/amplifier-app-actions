"""Tests for amplifier_app_actions.session_factory — create_session."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amplifier_app_actions.session_factory import create_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_cli_wiring(mocker=None):
    """Patch CLI wiring functions for every test in this module.

    register_mention_handling and register_session_spawning are external
    dependencies (amplifier_app_cli).  Unit tests for session_factory.py
    should not exercise real CLI internals — patch them everywhere.
    """
    with (
        patch("amplifier_app_actions.session_factory.register_mention_handling"),
        patch("amplifier_app_actions.session_factory.register_session_spawning"),
    ):
        yield


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
    """create_session() calls the bundle chain and wires standard CLI spawn; no tool mounts.

    The bundle chain (load_bundle → prepare → create_session) must still run, and
    the standard CLI spawn machinery (register_mention_handling + register_session_spawning)
    must be called so child sessions inherit the parent's restricted tool surface.
    """
    mock_bundle, mock_prepared, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with (
        patch("amplifier_app_actions.session_factory.load_bundle", mock_load),
        patch("amplifier_app_actions.session_factory.register_mention_handling") as mock_mention,
        patch("amplifier_app_actions.session_factory.register_session_spawning") as mock_spawn,
    ):
        result = await create_session(Path("/some/bundle"), github_token="test-token")

    # Bundle chain was invoked
    mock_load.assert_called_once_with(str(Path("/some/bundle")))
    mock_bundle.prepare.assert_called_once()
    mock_prepared.create_session.assert_called_once()

    # Standard CLI machinery wired up
    mock_mention.assert_called_once_with(mock_session)
    mock_spawn.assert_called_once_with(mock_session)

    # Result is the session object
    assert result is mock_session

    # coordinator.mount was NOT called for any GitHub / DTU tool
    assert mock_session.coordinator.mount.call_count == 0


async def test_create_session_registers_session_spawn_capability():
    """create_session delegates spawn registration to register_session_spawning."""
    mock_bundle, _, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with (
        patch("amplifier_app_actions.session_factory.load_bundle", mock_load),
        patch("amplifier_app_actions.session_factory.register_mention_handling"),
        patch("amplifier_app_actions.session_factory.register_session_spawning") as mock_spawn,
    ):
        await create_session(Path("/some/bundle"), github_token="test-token")

    mock_spawn.assert_called_once_with(mock_session)


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
# Spawn registration tests
# (Behaviour of spawn_sub_session itself is tested in amplifier_app_cli's own
#  test suite — session_factory.py's job is solely to call the right wiring
#  functions from the standard CLI machinery.)
# ---------------------------------------------------------------------------


async def test_create_session_calls_register_mention_handling():
    """create_session delegates mention handling to register_mention_handling."""
    mock_bundle, _, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with (
        patch("amplifier_app_actions.session_factory.load_bundle", mock_load),
        patch("amplifier_app_actions.session_factory.register_mention_handling") as mock_mention,
        patch("amplifier_app_actions.session_factory.register_session_spawning"),
    ):
        await create_session(Path("/some/bundle"), github_token="test-token")

    mock_mention.assert_called_once_with(mock_session)


async def test_create_session_calls_register_session_spawning():
    """create_session delegates spawn wiring to register_session_spawning."""
    mock_bundle, _, mock_session = _make_mock_chain()
    mock_load = AsyncMock(return_value=mock_bundle)

    with (
        patch("amplifier_app_actions.session_factory.load_bundle", mock_load),
        patch("amplifier_app_actions.session_factory.register_mention_handling"),
        patch("amplifier_app_actions.session_factory.register_session_spawning") as mock_spawn,
    ):
        await create_session(Path("/some/bundle"), github_token="test-token")

    mock_spawn.assert_called_once_with(mock_session)


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
