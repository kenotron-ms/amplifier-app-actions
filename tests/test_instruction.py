"""Tests for amplifier_app_actions.instruction — resolve_instruction."""

import pytest

from amplifier_app_actions.instruction import InstructionType, resolve_instruction


# ---------------------------------------------------------------------------
# Validation error tests
# ---------------------------------------------------------------------------


def test_raises_value_error_none_when_nothing_set():
    """resolve_instruction raises ValueError mentioning 'none' when no fields provided."""
    with pytest.raises(ValueError, match="none"):
        resolve_instruction()


def test_raises_value_error_multiple_when_two_fields_set(tmp_path):
    """resolve_instruction raises ValueError mentioning 'multiple' when 2+ fields set."""
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("hello")
    with pytest.raises(ValueError, match="multiple"):
        resolve_instruction(prompt="hello", prompt_source=str(prompt_file))


# ---------------------------------------------------------------------------
# Whitespace handling
# ---------------------------------------------------------------------------


def test_whitespace_only_prompt_treated_as_not_set():
    """Whitespace-only prompt string is treated as unset (raises ValueError for none)."""
    with pytest.raises(ValueError, match="none"):
        resolve_instruction(prompt="   ")


# ---------------------------------------------------------------------------
# PROMPT type tests
# ---------------------------------------------------------------------------


def test_inline_prompt_returns_prompt_type_with_text():
    """resolve_instruction with inline prompt returns (PROMPT, text)."""
    result = resolve_instruction(prompt="Review this issue carefully.")
    assert result[0] is InstructionType.PROMPT
    assert result[1] == "Review this issue carefully."


# ---------------------------------------------------------------------------
# PROMPT_SOURCE type tests
# ---------------------------------------------------------------------------


def test_prompt_source_reads_file_contents(tmp_path):
    """resolve_instruction with prompt_source returns (PROMPT_SOURCE, file_contents)."""
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("You are a helpful triage assistant.\n")

    result = resolve_instruction(prompt_source=str(prompt_file))

    assert result[0] is InstructionType.PROMPT_SOURCE
    assert result[1] == "You are a helpful triage assistant.\n"


def test_prompt_source_missing_file_raises_file_not_found_with_checkout_hint(tmp_path):
    """resolve_instruction raises FileNotFoundError mentioning 'actions/checkout' for missing prompt_source."""
    missing = str(tmp_path / "nonexistent.md")
    with pytest.raises(FileNotFoundError, match="actions/checkout"):
        resolve_instruction(prompt_source=missing)


# ---------------------------------------------------------------------------
# RECIPE type tests
# ---------------------------------------------------------------------------


def test_recipe_source_returns_path_not_contents(tmp_path):
    """resolve_instruction with recipe_source returns (RECIPE, path_string), not file contents."""
    recipe_file = tmp_path / "triage.yaml"
    recipe_file.write_text("steps:\n  - agent: triage\n")

    result = resolve_instruction(recipe_source=str(recipe_file))

    assert result[0] is InstructionType.RECIPE
    assert result[1] == str(recipe_file)
    # Must return the PATH, not the file contents
    assert "steps:" not in result[1]


def test_recipe_source_missing_file_raises_file_not_found_with_checkout_hint(tmp_path):
    """resolve_instruction raises FileNotFoundError mentioning 'actions/checkout' for missing recipe_source."""
    missing = str(tmp_path / "nonexistent.yaml")
    with pytest.raises(FileNotFoundError, match="actions/checkout"):
        resolve_instruction(recipe_source=missing)


# ---------------------------------------------------------------------------
# ATTRACTOR type tests
# ---------------------------------------------------------------------------


def test_attractor_source_returns_path_not_contents(tmp_path):
    """resolve_instruction with attractor_source returns (ATTRACTOR, path_string), not file contents."""
    attractor_file = tmp_path / "attractor.md"
    attractor_file.write_text("# Attractor\nFocus on critical bugs.\n")

    result = resolve_instruction(attractor_source=str(attractor_file))

    assert result[0] is InstructionType.ATTRACTOR
    assert result[1] == str(attractor_file)
    # Must return the PATH, not the file contents
    assert "# Attractor" not in result[1]


def test_attractor_source_missing_file_raises_file_not_found_with_checkout_hint(
    tmp_path,
):
    """resolve_instruction raises FileNotFoundError mentioning 'actions/checkout' for missing attractor_source."""
    missing = str(tmp_path / "nonexistent.md")
    with pytest.raises(FileNotFoundError, match="actions/checkout"):
        resolve_instruction(attractor_source=missing)
