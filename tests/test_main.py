"""Tests for main.py — thin GitHub Actions entrypoint."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Ensure repo root is on sys.path so `import main` works
_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _reload_main():
    """Reload the main module to get a fresh copy (clears cached env vars)."""
    if "main" in sys.modules:
        del sys.modules["main"]
    return importlib.import_module("main")


# ---------------------------------------------------------------------------
# 1. INPUT_PROMPT passed as prompt to cli.run with token and event_path
# ---------------------------------------------------------------------------


def test_input_prompt_passed_as_prompt_to_cli_run(monkeypatch):
    """main() reads INPUT_PROMPT and passes it as prompt to cli.run."""
    monkeypatch.setenv("INPUT_PROMPT", "Please triage this issue")
    monkeypatch.setenv("INPUT_GITHUB_TOKEN", "ghp_testtoken")
    monkeypatch.setenv("GITHUB_EVENT_PATH", "/tmp/event.json")
    monkeypatch.delenv("INPUT_PROMPT_SOURCE", raising=False)
    monkeypatch.delenv("INPUT_RECIPE_SOURCE", raising=False)
    monkeypatch.delenv("INPUT_ATTRACTOR_SOURCE", raising=False)
    monkeypatch.delenv("INPUT_PROVIDER", raising=False)
    monkeypatch.delenv("INPUT_MODEL", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with patch("amplifier_app_actions.cli.run", new_callable=AsyncMock) as mock_run:
        mod = _reload_main()
        mod.main()

    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs["prompt"] == "Please triage this issue"
    assert kwargs["github_token"] == "ghp_testtoken"
    assert kwargs["event_path"] == "/tmp/event.json"


# ---------------------------------------------------------------------------
# 2. INPUT_RECIPE_SOURCE passed as recipe_source (prompt empty)
# ---------------------------------------------------------------------------


def test_input_recipe_source_passed_as_recipe_source(monkeypatch):
    """main() reads INPUT_RECIPE_SOURCE and passes it as recipe_source; prompt is empty."""
    monkeypatch.setenv("INPUT_RECIPE_SOURCE", "triage.yaml")
    monkeypatch.delenv("INPUT_PROMPT", raising=False)
    monkeypatch.delenv("INPUT_PROMPT_SOURCE", raising=False)
    monkeypatch.delenv("INPUT_ATTRACTOR_SOURCE", raising=False)
    monkeypatch.delenv("INPUT_PROVIDER", raising=False)
    monkeypatch.delenv("INPUT_MODEL", raising=False)
    monkeypatch.delenv("INPUT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    with patch("amplifier_app_actions.cli.run", new_callable=AsyncMock) as mock_run:
        mod = _reload_main()
        mod.main()

    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs["recipe_source"] == "triage.yaml"
    assert kwargs["prompt"] == ""


# ---------------------------------------------------------------------------
# 3. INPUT_PROVIDER defaults to 'anthropic' when unset
# ---------------------------------------------------------------------------


def test_input_provider_defaults_to_anthropic(monkeypatch):
    """main() defaults provider to 'anthropic' when INPUT_PROVIDER is not set."""
    monkeypatch.setenv("INPUT_PROMPT", "test prompt")
    monkeypatch.delenv("INPUT_PROVIDER", raising=False)
    monkeypatch.delenv("INPUT_PROMPT_SOURCE", raising=False)
    monkeypatch.delenv("INPUT_RECIPE_SOURCE", raising=False)
    monkeypatch.delenv("INPUT_ATTRACTOR_SOURCE", raising=False)
    monkeypatch.delenv("INPUT_MODEL", raising=False)
    monkeypatch.delenv("INPUT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    with patch("amplifier_app_actions.cli.run", new_callable=AsyncMock) as mock_run:
        mod = _reload_main()
        mod.main()

    kwargs = mock_run.call_args.kwargs
    assert kwargs["provider"] == "anthropic"


# ---------------------------------------------------------------------------
# 4. All four instruction fields forwarded including attractor_source
# ---------------------------------------------------------------------------


def test_all_instruction_fields_forwarded_including_attractor_source(monkeypatch):
    """main() forwards all four instruction fields plus provider, model, token, and event_path."""
    monkeypatch.setenv("INPUT_ATTRACTOR_SOURCE", "guide.md")
    monkeypatch.setenv("INPUT_PROVIDER", "openai")
    monkeypatch.setenv("INPUT_MODEL", "gpt-4o")
    monkeypatch.setenv("INPUT_GITHUB_TOKEN", "ghp_abc")
    monkeypatch.setenv("GITHUB_EVENT_PATH", "/event.json")
    monkeypatch.delenv("INPUT_PROMPT", raising=False)
    monkeypatch.delenv("INPUT_PROMPT_SOURCE", raising=False)
    monkeypatch.delenv("INPUT_RECIPE_SOURCE", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with patch("amplifier_app_actions.cli.run", new_callable=AsyncMock) as mock_run:
        mod = _reload_main()
        mod.main()

    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs["prompt"] == ""
    assert kwargs["prompt_source"] == ""
    assert kwargs["recipe_source"] == ""
    assert kwargs["attractor_source"] == "guide.md"
    assert kwargs["provider"] == "openai"
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["github_token"] == "ghp_abc"
    assert kwargs["event_path"] == "/event.json"
