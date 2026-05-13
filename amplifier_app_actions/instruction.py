"""Instruction field resolution for amplifier-app-actions.

Resolves exactly one of: prompt, prompt_source, recipe_source, or attractor_source
into a typed (InstructionType, value) pair.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class InstructionType(Enum):
    """Identifies which instruction field was provided."""

    PROMPT = "prompt"
    PROMPT_SOURCE = "prompt_source"
    RECIPE = "recipe_source"
    ATTRACTOR = "attractor_source"


def resolve_instruction(
    prompt: str = "",
    prompt_source: str = "",
    recipe_source: str = "",
    attractor_source: str = "",
) -> tuple[InstructionType, str]:
    """Resolve exactly one instruction field into a typed value pair.

    Empty strings and whitespace-only values are treated as not set.

    Parameters
    ----------
    prompt:
        Inline prompt text to use directly.
    prompt_source:
        Filesystem path to a file whose contents are the prompt.
    recipe_source:
        Filesystem path to an Amplifier recipe YAML file.
    attractor_source:
        Filesystem path to an attractor (guidance) file.

    Returns
    -------
    tuple[InstructionType, str]
        - For PROMPT: (PROMPT, prompt_text)
        - For PROMPT_SOURCE: (PROMPT_SOURCE, file_contents)
        - For RECIPE: (RECIPE, path_string)
        - For ATTRACTOR: (ATTRACTOR, path_string)

    Raises
    ------
    ValueError
        If zero fields are set (message contains 'none') or multiple fields are
        set (message contains 'multiple' listing the field names).
    FileNotFoundError
        If a source path does not exist on the filesystem.  The error message
        includes an 'actions/checkout' reminder so users know to check out their
        repo before running this action.
    """
    _FIELD_NAMES = ("prompt", "prompt_source", "recipe_source", "attractor_source")

    fields = {
        "prompt": prompt,
        "prompt_source": prompt_source,
        "recipe_source": recipe_source,
        "attractor_source": attractor_source,
    }

    # Treat empty / whitespace-only as unset
    set_fields = [name for name, val in fields.items() if val and val.strip()]

    if len(set_fields) == 0:
        raise ValueError(f"Exactly one of {_FIELD_NAMES} must be set. Got none.")

    if len(set_fields) > 1:
        raise ValueError(
            f"Exactly one of {_FIELD_NAMES} must be set. Got multiple: {set_fields}."
        )

    (field_name,) = set_fields

    if field_name == "prompt":
        return (InstructionType.PROMPT, fields["prompt"])

    if field_name == "prompt_source":
        path = Path(prompt_source)
        if not path.exists():
            raise FileNotFoundError(
                f"prompt_source path not found: {prompt_source!r}. "
                "Make sure to use actions/checkout before running this action."
            )
        return (InstructionType.PROMPT_SOURCE, path.read_text())

    if field_name == "recipe_source":
        path = Path(recipe_source)
        if not path.exists():
            raise FileNotFoundError(
                f"recipe_source path not found: {recipe_source!r}. "
                "Make sure to use actions/checkout before running this action."
            )
        return (InstructionType.RECIPE, recipe_source)

    # field_name == "attractor_source"
    path = Path(attractor_source)
    if not path.exists():
        raise FileNotFoundError(
            f"attractor_source path not found: {attractor_source!r}. "
            "Make sure to use actions/checkout before running this action."
        )
    return (InstructionType.ATTRACTOR, attractor_source)
