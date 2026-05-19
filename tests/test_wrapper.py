"""Tests for amplifier_app_actions.wrapper — thin amplifier CLI wrapper."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


from amplifier_app_actions.wrapper import run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ISSUE_EVENT = {
    "action": "opened",
    "issue": {
        "number": 42,
        "title": "Login page throws 500 error",
        "body": "Steps to reproduce: ...",
        "user": {"login": "alice"},
        "labels": [],
    },
    "repository": {"name": "my-repo", "owner": {"login": "my-org"}},
}


def _mock_proc(returncode: int = 0) -> MagicMock:
    """Return a mock asyncio.Process with returncode and wait()."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.wait = AsyncMock(return_value=returncode)
    return proc


def _capture_argv(mock_exec: MagicMock) -> list[str]:
    """Extract positional argv from the first create_subprocess_exec call."""
    return list(mock_exec.call_args[0])


# ---------------------------------------------------------------------------
# 1. Prompt argv
# ---------------------------------------------------------------------------


async def test_prompt_argv(tmp_path):
    """Prompt mode builds: amplifier run --bundle <path> --mode single -- <prompt>."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="triage this issue",
            bundle="triage-safe",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    assert argv[0] == "amplifier"
    assert argv[1] == "run"
    assert "--bundle" in argv
    assert "--mode" in argv
    idx_mode = argv.index("--mode")
    assert argv[idx_mode + 1] == "single"
    assert "--" in argv
    assert "triage this issue" in argv[-1]


# ---------------------------------------------------------------------------
# 2. Context block before prompt
# ---------------------------------------------------------------------------


async def test_context_block_before_prompt(tmp_path):
    """With an event file, context block is prepended to the final argv element."""
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(_ISSUE_EVENT))

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="Please triage.",
            event_path=str(event_file),
            bundle="triage-safe",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    full_prompt = argv[-1]
    # Context block appears before the user prompt
    assert "my-org/my-repo" in full_prompt
    assert "Please triage." in full_prompt
    context_idx = full_prompt.index("my-org/my-repo")
    prompt_idx = full_prompt.index("Please triage.")
    assert context_idx < prompt_idx, "Context block must appear before user prompt"


# ---------------------------------------------------------------------------
# 3. Injection title inside final prompt argv element only
# ---------------------------------------------------------------------------


async def test_injection_title_in_single_argv_element(tmp_path):
    """Injection title in final argv element only — not split into extra argv tokens."""
    evil_title = "Fix bug]; import os; os.system('evil')"
    event = {
        **_ISSUE_EVENT,
        "issue": {**_ISSUE_EVENT["issue"], "title": evil_title},
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event))

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="Triage.",
            event_path=str(event_file),
            bundle="triage-safe",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    # The injection string must appear ONLY in the last element, as plain text
    # Searching all elements except the last must not contain it
    for i, arg in enumerate(argv[:-1]):
        assert evil_title not in arg, (
            f"Injection title found in argv[{i}]={arg!r}, should only be in final element"
        )
    assert evil_title in argv[-1], (
        "Injection title must appear (escaped) in final prompt element"
    )


# ---------------------------------------------------------------------------
# 4. Recipe argv
# ---------------------------------------------------------------------------


async def test_recipe_argv(tmp_path):
    """Recipe mode builds: amplifier tool invoke -b <bundle> recipes operation=execute recipe_path=... context=..."""
    recipe_file = tmp_path / "triage.yaml"
    recipe_file.write_text("steps: []")

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            recipe_source=str(recipe_file),
            bundle="triage-safe",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    assert argv[0] == "amplifier"
    assert argv[1] == "tool"
    assert argv[2] == "invoke"
    # -b <bundle_path> must appear before the tool name so recipe agents get the right bundle
    assert "-b" in argv
    b_idx = argv.index("-b")
    assert "triage-safe" in argv[b_idx + 1]
    assert argv[b_idx + 2] == "recipes"
    assert any(a.startswith("operation=execute") for a in argv)
    assert any(a.startswith("recipe_path=") for a in argv)
    assert any(a.startswith("context=") for a in argv)
    # Must NOT use 'run' or long-form '--bundle' (those are for prompt mode)
    assert "run" not in argv[1:3]
    assert "--bundle" not in argv


# ---------------------------------------------------------------------------
# 5. Recipe context data
# ---------------------------------------------------------------------------


async def test_recipe_context_data(tmp_path):
    """Recipe context contains event fields nested under 'context' key."""
    recipe_file = tmp_path / "triage.yaml"
    recipe_file.write_text("steps: []")

    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(_ISSUE_EVENT))

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            recipe_source=str(recipe_file),
            event_path=str(event_file),
            bundle="triage-safe",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    context_arg = next(a for a in argv if a.startswith("context="))
    context_json = context_arg[len("context=") :]
    context_data = json.loads(context_json)

    assert "context" in context_data, "Event fields must be nested under 'context' key"
    ctx = context_data["context"]
    assert ctx["number"] == 42
    assert ctx["owner"] == "my-org"
    assert ctx["repo"] == "my-repo"
    assert ctx["title"] == "Login page throws 500 error"
    assert ctx["author"] == "alice"
    assert isinstance(ctx["labels"], list)


# ---------------------------------------------------------------------------
# 6. Attractor argv
# ---------------------------------------------------------------------------


async def test_attractor_argv(tmp_path):
    """Attractor mode builds an amplifier run command with path in the prompt."""
    attractor_file = tmp_path / "triage.dot"
    attractor_file.write_text("digraph G { A -> B; }")

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            attractor_source=str(attractor_file),
            bundle="triage-safe",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    assert argv[0] == "amplifier"
    assert argv[1] == "run"
    # attractor path appears in the final prompt element
    assert str(attractor_file) in argv[-1]


# ---------------------------------------------------------------------------
# 7. Bundle alias resolution
# ---------------------------------------------------------------------------


async def test_bundle_alias_resolution(tmp_path):
    """Built-in alias 'triage-safe' resolves to action_path/bundles/triage-safe.bundle.md."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="test",
            bundle="triage-safe",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    bundle_idx = argv.index("--bundle")
    expected = str(tmp_path / "bundles" / "triage-safe.bundle.md")
    assert argv[bundle_idx + 1] == expected


async def test_bundle_alias_triage_repro_resolution(tmp_path):
    """Built-in alias 'triage-repro' resolves to action_path/bundles/triage-repro.bundle.md."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="test",
            bundle="triage-repro",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    bundle_idx = argv.index("--bundle")
    expected = str(tmp_path / "bundles" / "triage-repro.bundle.md")
    assert argv[bundle_idx + 1] == expected


# ---------------------------------------------------------------------------
# 8. Unknown bundle passthrough
# ---------------------------------------------------------------------------


async def test_unknown_bundle_passthrough(tmp_path):
    """Unknown bundle values pass through to amplifier CLI unchanged."""
    custom_bundle = "/some/custom/path/my.bundle.md"

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="test",
            bundle=custom_bundle,
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    bundle_idx = argv.index("--bundle")
    assert argv[bundle_idx + 1] == custom_bundle


# ---------------------------------------------------------------------------
# 9. enable_reproduction promotes default bundle to triage-repro
# ---------------------------------------------------------------------------


async def test_enable_reproduction_promotes_default_bundle(tmp_path):
    """enable_reproduction=True upgrades default 'triage-safe' to 'triage-repro'."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="test",
            bundle="triage-safe",
            enable_reproduction=True,
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    bundle_idx = argv.index("--bundle")
    assert "triage-repro" in argv[bundle_idx + 1]


# ---------------------------------------------------------------------------
# 10. Explicit bundle not overridden by enable_reproduction
# ---------------------------------------------------------------------------


async def test_explicit_bundle_not_overridden_by_enable_reproduction(tmp_path):
    """An explicit non-default bundle is NOT promoted even when enable_reproduction=True."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="test",
            bundle="triage-amplifier",
            enable_reproduction=True,
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    bundle_idx = argv.index("--bundle")
    assert "triage-amplifier" in argv[bundle_idx + 1]
    assert "triage-repro" not in argv[bundle_idx + 1]


# ---------------------------------------------------------------------------
# 11. provider/model flags
# ---------------------------------------------------------------------------


async def test_provider_flag_included_when_set(tmp_path):
    """--provider flag is included when provider is set."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="test",
            provider="openai",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    assert "--provider" in argv
    provider_idx = argv.index("--provider")
    assert argv[provider_idx + 1] == "openai"


async def test_model_flag_included_when_set(tmp_path):
    """--model flag is included when model is set."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="test",
            provider="anthropic",
            model="claude-opus-4-7",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    assert "--model" in argv
    model_idx = argv.index("--model")
    assert argv[model_idx + 1] == "claude-opus-4-7"


# ---------------------------------------------------------------------------
# 12. Empty model omitted
# ---------------------------------------------------------------------------


async def test_empty_model_not_in_argv(tmp_path):
    """--model flag is NOT added when model is empty string."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="test",
            provider="anthropic",
            model="",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    assert "--model" not in argv


# ---------------------------------------------------------------------------
# 13. GITHUB_TOKEN setdefault
# ---------------------------------------------------------------------------


async def test_github_token_set_in_env_when_missing(tmp_path, monkeypatch):
    """GITHUB_TOKEN is set in env via setdefault when it was absent."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ):
        await run(
            prompt="test",
            github_token="ghp_testtoken",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    assert os.environ.get("GITHUB_TOKEN") == "ghp_testtoken"


async def test_github_token_not_overwritten_when_present(tmp_path, monkeypatch):
    """GITHUB_TOKEN already in env is NOT overwritten (setdefault semantics)."""
    monkeypatch.setenv("GITHUB_TOKEN", "existing-runner-token")

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ):
        await run(
            prompt="test",
            github_token="different-token",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    assert os.environ.get("GITHUB_TOKEN") == "existing-runner-token"


# ---------------------------------------------------------------------------
# 14. prompt_source inlines contents
# ---------------------------------------------------------------------------


async def test_prompt_source_inlines_file_contents(tmp_path):
    """prompt_source reads file and uses its contents as the prompt text."""
    prompt_file = tmp_path / "instructions.md"
    prompt_file.write_text("You are a helpful triage assistant. Label this bug.")

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt_source=str(prompt_file),
            bundle="triage-safe",
            action_path=tmp_path,
            amplifier_bin="amplifier",
        )

    argv = _capture_argv(mock_exec)
    assert "You are a helpful triage assistant. Label this bug." in argv[-1]


# ---------------------------------------------------------------------------
# 15. Return code
# ---------------------------------------------------------------------------


async def test_return_code_propagated(tmp_path):
    """wrapper.run() returns the subprocess exit code."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(returncode=2),
    ):
        returncode = await run(
            prompt="test", action_path=tmp_path, amplifier_bin="amplifier"
        )

    assert returncode == 2


async def test_return_code_zero_on_success(tmp_path):
    """wrapper.run() returns 0 on subprocess success."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(returncode=0),
    ):
        returncode = await run(
            prompt="test", action_path=tmp_path, amplifier_bin="amplifier"
        )

    assert returncode == 0


# ---------------------------------------------------------------------------
# 16. No shell subprocess
# ---------------------------------------------------------------------------


async def test_no_shell_in_subprocess(tmp_path):
    """asyncio.create_subprocess_exec is used (not shell=True via create_subprocess_shell)."""
    called_shell = []

    async def mock_shell(*args, **kwargs):
        called_shell.append(True)
        return _mock_proc()

    with (
        patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=_mock_proc(),
        ),
        patch("asyncio.create_subprocess_shell", side_effect=mock_shell),
    ):
        await run(prompt="test", action_path=tmp_path, amplifier_bin="amplifier")

    assert not called_shell, "create_subprocess_shell must never be called"


# ---------------------------------------------------------------------------
# 17. No event file — no context prefix
# ---------------------------------------------------------------------------


async def test_no_event_no_context_prefix(tmp_path):
    """Without event_path, prompt is passed unmodified to the final argv element."""
    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(
            prompt="Just do this task.", action_path=tmp_path, amplifier_bin="amplifier"
        )

    argv = _capture_argv(mock_exec)
    assert argv[-1] == "Just do this task."


# ---------------------------------------------------------------------------
# 18. action_path defaults to parent of package
# ---------------------------------------------------------------------------


async def test_action_path_defaults_correctly(tmp_path):
    """When action_path is None, it resolves to parent of amplifier_app_actions package."""
    from amplifier_app_actions import wrapper

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_proc(),
    ) as mock_exec:
        await run(prompt="test", amplifier_bin="amplifier")

    argv = _capture_argv(mock_exec)
    bundle_idx = argv.index("--bundle")
    # The bundle path should contain the actual repo directory
    actual_parent = str(Path(wrapper.__file__).parent.parent)
    assert actual_parent in argv[bundle_idx + 1]


# ---------------------------------------------------------------------------
# Path B Attractor — _register_spawn_capability
# ---------------------------------------------------------------------------


def test_register_spawn_capability_registers_on_coordinator():
    """_register_spawn_capability calls register_capability('session.spawn', ...) on coordinator."""
    import asyncio

    from amplifier_app_actions.wrapper import _register_spawn_capability

    mock_coordinator = MagicMock()
    mock_session = MagicMock()
    mock_session.coordinator = mock_coordinator

    mock_prepared = MagicMock()
    mock_prepared.bundle = MagicMock()
    mock_prepared.bundle.agents = {}

    _register_spawn_capability(mock_session, mock_prepared)

    mock_coordinator.register_capability.assert_called_once()
    name, fn = mock_coordinator.register_capability.call_args[0]
    assert name == "session.spawn"
    assert asyncio.iscoroutinefunction(fn)


# ---------------------------------------------------------------------------
# Path B Attractor — _run_attractor
# ---------------------------------------------------------------------------


async def test_run_attractor_reads_dot_and_configures_loop_pipeline(tmp_path):
    """_run_attractor reads DOT file and composes bundle with loop-pipeline orchestrator."""
    dot_file = tmp_path / "pipeline.dot"
    dot_source = "digraph G { A -> B; }"
    dot_file.write_text(dot_source)

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value="done")
    mock_session.cleanup = AsyncMock()
    mock_session.coordinator = MagicMock()
    mock_session.coordinator.register_capability = MagicMock()

    mock_prepared = MagicMock()
    mock_prepared.create_session = AsyncMock(return_value=mock_session)
    mock_prepared.bundle = MagicMock()
    mock_prepared.bundle.agents = {}

    mock_composed = MagicMock()
    mock_composed.prepare = AsyncMock(return_value=mock_prepared)

    mock_base_bundle = MagicMock()
    mock_base_bundle.compose = MagicMock(return_value=mock_composed)

    captured_bundle_calls: list = []

    def capture_bundle(**kwargs):
        captured_bundle_calls.append(kwargs)
        return MagicMock()

    with (
        patch(
            "amplifier_foundation.load_bundle",
            new_callable=AsyncMock,
            return_value=mock_base_bundle,
        ),
        patch("amplifier_foundation.Bundle", side_effect=capture_bundle),
        patch("amplifier_app_cli.console.console"),
        patch("rich.markdown.Markdown"),
    ):
        from amplifier_app_actions.wrapper import _run_attractor

        result = await _run_attractor(
            content=str(dot_file),
            ctx_prefix="",
            bundle_path="some-bundle",
            cwd=None,
        )

    assert result == 0
    # Exactly one Bundle() call — the loop-pipeline overlay
    assert len(captured_bundle_calls) == 1
    overlay_kwargs = captured_bundle_calls[0]
    session_cfg = overlay_kwargs.get("session", {})
    orchestrator = session_cfg.get("orchestrator", {})
    assert orchestrator.get("module") == "loop-pipeline"
    assert orchestrator.get("config", {}).get("dot_source") == dot_source


async def test_run_attractor_missing_dot_file_raises(tmp_path):
    """_run_attractor raises FileNotFoundError when the DOT file does not exist."""
    import pytest

    from amplifier_app_actions.wrapper import _run_attractor

    with pytest.raises(FileNotFoundError, match="Attractor DOT file not found"):
        await _run_attractor(
            content=str(tmp_path / "nonexistent.dot"),
            ctx_prefix="",
            bundle_path="some-bundle",
            cwd=None,
        )


async def test_run_attractor_returns_1_on_session_error(tmp_path):
    """_run_attractor returns 1 when session.execute raises an exception."""
    dot_file = tmp_path / "pipeline.dot"
    dot_file.write_text("digraph G { A -> B; }")

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(side_effect=RuntimeError("provider error"))
    mock_session.cleanup = AsyncMock()
    mock_session.coordinator = MagicMock()
    mock_session.coordinator.register_capability = MagicMock()

    mock_prepared = MagicMock()
    mock_prepared.create_session = AsyncMock(return_value=mock_session)
    mock_prepared.bundle = MagicMock()
    mock_prepared.bundle.agents = {}

    mock_composed = MagicMock()
    mock_composed.prepare = AsyncMock(return_value=mock_prepared)

    mock_base_bundle = MagicMock()
    mock_base_bundle.compose = MagicMock(return_value=mock_composed)

    with (
        patch(
            "amplifier_foundation.load_bundle",
            new_callable=AsyncMock,
            return_value=mock_base_bundle,
        ),
        patch("amplifier_foundation.Bundle", return_value=MagicMock()),
        patch("amplifier_app_cli.console.console"),
        patch("rich.markdown.Markdown"),
    ):
        from amplifier_app_actions.wrapper import _run_attractor

        result = await _run_attractor(
            content=str(dot_file),
            ctx_prefix="",
            bundle_path="some-bundle",
            cwd=None,
        )

    assert result == 1


# ---------------------------------------------------------------------------
# Path B Attractor — run() routing
# ---------------------------------------------------------------------------


async def test_run_routes_attractor_to_run_attractor(tmp_path):
    """run() with attractor_source dispatches to _run_attractor, not _run_prompt_or_attractor."""
    dot_file = tmp_path / "pipeline.dot"
    dot_file.write_text("digraph G { A -> B; }")

    with (
        patch(
            "amplifier_app_actions.wrapper._run_attractor",
            new_callable=AsyncMock,
            return_value=0,
        ) as mock_attractor,
        patch(
            "amplifier_app_actions.wrapper._run_prompt_or_attractor",
            new_callable=AsyncMock,
            return_value=0,
        ) as mock_prompt,
    ):
        result = await run(
            attractor_source=str(dot_file),
            action_path=tmp_path,
        )

    assert result == 0
    mock_attractor.assert_called_once()
    mock_prompt.assert_not_called()
