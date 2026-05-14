"""Tests for amplifier_app_actions.cli — run() dispatch and main() argparse."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amplifier_app_actions.cli import run


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_mock_session(tools: dict | None = None):
    """Build a minimal mock session for cli.run() tests."""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()

    mock_coordinator = MagicMock()
    mock_coordinator.get = MagicMock(return_value=tools if tools is not None else {})
    mock_session.coordinator = mock_coordinator
    return mock_session


def _issue_event_payload(
    owner: str = "test-org",
    repo: str = "test-repo",
    number: int = 42,
    title: str = "Test issue",
    body: str = "Test body",
) -> dict:
    return {
        "action": "opened",
        "issue": {
            "number": number,
            "title": title,
            "body": body,
            "user": {"login": "alice"},
            "labels": [],
        },
        "repository": {"name": repo, "owner": {"login": owner}},
    }


def _pr_event_payload(
    owner: str = "acme",
    repo: str = "backend",
    number: int = 7,
) -> dict:
    return {
        "action": "opened",
        "pull_request": {
            "number": number,
            "title": "Add tests",
            "body": "Adding coverage",
            "user": {"login": "engineer"},
            "labels": [],
            "base": {"ref": "main"},
            "head": {"ref": "feature/tests"},
        },
        "repository": {"name": repo, "owner": {"login": owner}},
    }


# ---------------------------------------------------------------------------
# 1. Prompt mode calls session.execute with context+prompt
# ---------------------------------------------------------------------------


async def test_prompt_mode_with_event_calls_execute_with_context_and_prompt(tmp_path):
    """run() in PROMPT mode with an event prepends context block and calls session.execute."""
    event_file = tmp_path / "event.json"
    event_file.write_text(
        json.dumps(_issue_event_payload(owner="my-org", repo="my-repo"))
    )

    mock_session = _make_mock_session()

    with patch(
        "amplifier_app_actions.cli.create_session", AsyncMock(return_value=mock_session)
    ):
        await run(
            prompt="Please triage this issue.",
            event_path=str(event_file),
        )

    mock_session.execute.assert_called_once()
    called_with = mock_session.execute.call_args[0][0]
    assert "Please triage this issue." in called_with
    assert "my-org/my-repo" in called_with


# ---------------------------------------------------------------------------
# 2. Context appears before user prompt (string index comparison)
# ---------------------------------------------------------------------------


async def test_context_block_appears_before_user_prompt(tmp_path):
    """In PROMPT mode, the context block index must be less than the user prompt index."""
    event_file = tmp_path / "event.json"
    event_file.write_text(
        json.dumps(_issue_event_payload(owner="corp", repo="auth-service", number=5))
    )

    mock_session = _make_mock_session()

    with patch(
        "amplifier_app_actions.cli.create_session", AsyncMock(return_value=mock_session)
    ):
        await run(
            prompt="Analyze this carefully.",
            event_path=str(event_file),
        )

    full_prompt: str = mock_session.execute.call_args[0][0]
    context_idx = full_prompt.index("corp/auth-service")
    prompt_idx = full_prompt.index("Analyze this carefully.")
    assert context_idx < prompt_idx, "Context block must appear before the user prompt"


# ---------------------------------------------------------------------------
# 3. prompt_source reads file and uses as prompt
# ---------------------------------------------------------------------------


async def test_prompt_source_reads_file_and_uses_as_prompt(tmp_path):
    """run() in PROMPT_SOURCE mode reads the file and uses its contents as the prompt."""
    prompt_file = tmp_path / "instructions.md"
    prompt_file.write_text("You are a triage bot. Label the issue appropriately.")

    event_file = tmp_path / "event.json"
    event_file.write_text(
        json.dumps(_issue_event_payload(owner="company", repo="app", number=10))
    )

    mock_session = _make_mock_session()

    with patch(
        "amplifier_app_actions.cli.create_session", AsyncMock(return_value=mock_session)
    ):
        await run(
            prompt_source=str(prompt_file),
            event_path=str(event_file),
        )

    mock_session.execute.assert_called_once()
    called_with: str = mock_session.execute.call_args[0][0]
    assert "You are a triage bot." in called_with


# ---------------------------------------------------------------------------
# 4. Recipe mode calls 'recipes' tool with recipe_path
# ---------------------------------------------------------------------------


async def test_recipe_mode_calls_recipes_tool_with_recipe_path(tmp_path):
    """run() in RECIPE mode calls the 'recipes' tool execute with {'recipe_path': ...}."""
    recipe_file = tmp_path / "triage.yaml"
    recipe_file.write_text("steps:\n  - agent: triage\n")

    mock_recipe_tool = MagicMock()
    mock_recipe_tool.execute = AsyncMock()
    mock_session = _make_mock_session(tools={"recipes": mock_recipe_tool})

    with patch(
        "amplifier_app_actions.cli.create_session", AsyncMock(return_value=mock_session)
    ):
        await run(recipe_source=str(recipe_file))

    mock_recipe_tool.execute.assert_called_once()
    call_input = mock_recipe_tool.execute.call_args[0][0]
    assert call_input["recipe_path"] == str(recipe_file)


# ---------------------------------------------------------------------------
# 5. Recipe mode passes event vars as context dict (owner/repo/number)
# ---------------------------------------------------------------------------


async def test_recipe_mode_passes_event_vars_as_context_dict(tmp_path):
    """run() in RECIPE mode passes event owner/repo/number in the context dict."""
    recipe_file = tmp_path / "recipe.yaml"
    recipe_file.write_text("steps: []")

    event_file = tmp_path / "event.json"
    event_file.write_text(
        json.dumps(_pr_event_payload(owner="acme", repo="backend", number=7))
    )

    mock_recipe_tool = MagicMock()
    mock_recipe_tool.execute = AsyncMock()
    mock_session = _make_mock_session(tools={"recipes": mock_recipe_tool})

    with patch(
        "amplifier_app_actions.cli.create_session", AsyncMock(return_value=mock_session)
    ):
        await run(recipe_source=str(recipe_file), event_path=str(event_file))

    call_input = mock_recipe_tool.execute.call_args[0][0]
    context = call_input["context"]
    assert context["owner"] == "acme"
    assert context["repo"] == "backend"
    assert context["number"] == 7


# ---------------------------------------------------------------------------
# 6. ValueError raised when no instruction set
# ---------------------------------------------------------------------------


async def test_raises_value_error_when_no_instruction_set():
    """run() raises ValueError when called with no instruction source."""
    with pytest.raises(ValueError):
        await run()


# ---------------------------------------------------------------------------
# 7. CLI main parses --prompt and passes to run
# ---------------------------------------------------------------------------


def test_main_parses_prompt_and_passes_to_run():
    """main() with --prompt parses the value and passes it to run()."""
    from amplifier_app_actions.cli import main

    captured: dict = {}

    async def _mock_run(**kwargs):
        captured.update(kwargs)

    with (
        patch("amplifier_app_actions.cli.run", _mock_run),
        patch.object(sys, "argv", ["amplifier-triage", "--prompt", "Fix bug #123"]),
    ):
        main()

    assert captured.get("prompt") == "Fix bug #123"


# ---------------------------------------------------------------------------
# 8. CLI main parses --recipe-source and passes to run
# ---------------------------------------------------------------------------


def test_main_parses_recipe_source_and_passes_to_run():
    """main() with --recipe-source parses the value and passes it to run()."""
    from amplifier_app_actions.cli import main

    captured: dict = {}

    async def _mock_run(**kwargs):
        captured.update(kwargs)

    with (
        patch("amplifier_app_actions.cli.run", _mock_run),
        patch.object(
            sys, "argv", ["amplifier-triage", "--recipe-source", "triage.yaml"]
        ),
    ):
        main()

    assert captured.get("recipe_source") == "triage.yaml"


# ---------------------------------------------------------------------------
# 9. Prompt mode without event uses content directly (no context block prepended)
# ---------------------------------------------------------------------------


async def test_prompt_mode_without_event_uses_content_directly():
    """run() in PROMPT mode with no event_path passes content directly to session.execute."""
    mock_session = _make_mock_session()

    with patch(
        "amplifier_app_actions.cli.create_session", AsyncMock(return_value=mock_session)
    ):
        await run(prompt="Just do this task.")

    mock_session.execute.assert_called_once()
    called_with: str = mock_session.execute.call_args[0][0]
    assert called_with == "Just do this task."


# ---------------------------------------------------------------------------
# 10. Attractor mode calls attractor tool with attractor_path and context=None
# ---------------------------------------------------------------------------


async def test_attractor_mode_calls_attractor_tool_with_attractor_path(tmp_path):
    """run() in ATTRACTOR mode calls the 'attractors' tool execute with attractor_path and context=None."""
    attractor_file = tmp_path / "triage.dot"
    attractor_file.write_text("digraph G { A -> B; }")

    mock_attractor_tool = MagicMock()
    mock_attractor_tool.execute = AsyncMock()
    mock_session = _make_mock_session(tools={"attractors": mock_attractor_tool})

    with patch(
        "amplifier_app_actions.cli.create_session", AsyncMock(return_value=mock_session)
    ):
        await run(attractor_source=str(attractor_file), github_token="token")

    mock_attractor_tool.execute.assert_called_once()
    call_input = mock_attractor_tool.execute.call_args[0][0]
    assert call_input["attractor_path"] == str(attractor_file)
    assert call_input["context"] is None


# ---------------------------------------------------------------------------
# 11. Attractor mode raises RuntimeError when attractor tool is not mounted
# ---------------------------------------------------------------------------


async def test_attractor_mode_raises_when_attractor_tool_not_mounted(tmp_path):
    """run() in ATTRACTOR mode raises RuntimeError when no 'attractors' tool is in coordinator."""
    attractor_file = tmp_path / "triage.dot"
    attractor_file.write_text("digraph G { A -> B; }")

    mock_session = _make_mock_session(tools={})

    with (
        patch(
            "amplifier_app_actions.cli.create_session",
            AsyncMock(return_value=mock_session),
        ),
        pytest.raises(RuntimeError, match="Attractor tool not mounted"),
    ):
        await run(attractor_source=str(attractor_file))
