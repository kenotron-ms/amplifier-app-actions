"""CLI module — library core for prompt/recipe/attractor dispatch and argparse entry point.

Serves as the single source of logic for both execution paths:
- GitHub Actions entrypoint (called from action.py)
- uv tool CLI (amplifier-triage command)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from amplifier_app_actions.events import format_context_block, parse_event
from amplifier_app_actions.instruction import InstructionType, resolve_instruction
from amplifier_app_actions.session_factory import create_session

logger = logging.getLogger(__name__)

_BUNDLE_MD = Path(__file__).parent.parent / "bundle.md"


async def run(
    prompt: str = "",
    prompt_source: str = "",
    recipe_source: str = "",
    attractor_source: str = "",
    provider: str = "",
    model: str = "",
    github_token: str = "",
    event_path: str = "",
) -> None:
    """Core execution logic — parses event, resolves instruction, and dispatches to session.

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
    provider:
        AI provider name (e.g. 'anthropic').
    model:
        Model name override (empty string means use bundle default).
    github_token:
        GitHub personal access token for API calls.
    event_path:
        Filesystem path to the GitHub event JSON payload file.
    """
    # 1. Parse event (optional)
    event: dict[str, Any] | None = None
    if event_path:
        event = parse_event(event_path)
        logger.info(
            "event_type=%s number=%s owner=%s repo=%s",
            event["event_type"],
            event["number"],
            event["owner"],
            event["repo"],
        )

    # 2. Resolve instruction — raises ValueError if nothing set
    itype, content = resolve_instruction(
        prompt=prompt,
        prompt_source=prompt_source,
        recipe_source=recipe_source,
        attractor_source=attractor_source,
    )
    logger.info("instruction_type=%s", itype.value)

    # 3. Create session
    session = await create_session(
        bundle_path=_BUNDLE_MD,
        github_token=github_token,
        provider=provider,
        model=model,
    )

    # 4. Dispatch based on instruction type
    if itype in (InstructionType.PROMPT, InstructionType.PROMPT_SOURCE):
        if event is not None:
            # Context block MUST come before user prompt
            full_prompt = f"{format_context_block(event)}\n\n{content}"
        else:
            full_prompt = content
        await session.execute(full_prompt)

    elif itype == InstructionType.RECIPE:
        tools: dict[str, Any] = session.coordinator.get("tools") or {}
        recipe_tool = tools.get("recipes")
        if recipe_tool is None:
            raise RuntimeError(
                f"Recipe tool not mounted on coordinator. Available tools: {list(tools.keys())}"
            )
        await recipe_tool.execute({"recipe_path": content, "context": event})

    elif itype == InstructionType.ATTRACTOR:
        tools = session.coordinator.get("tools") or {}
        attractor_tool = tools.get("attractors")
        if attractor_tool is None:
            raise RuntimeError(
                f"Attractor tool not mounted on coordinator. Available tools: {list(tools.keys())}"
            )
        await attractor_tool.execute({"attractor_path": content, "context": event})


def main() -> None:
    """uv tool entry point — parse CLI flags and call run() via asyncio.run()."""
    parser = argparse.ArgumentParser(prog="amplifier-triage")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prompt", default="")
    group.add_argument("--prompt-source", dest="prompt_source", default="")
    group.add_argument("--recipe-source", dest="recipe_source", default="")
    group.add_argument("--attractor-source", dest="attractor_source", default="")

    parser.add_argument("--provider", default="anthropic")
    parser.add_argument("--model", default="")
    parser.add_argument(
        "--github-token",
        dest="github_token",
        default=os.environ.get("GITHUB_TOKEN", ""),
    )
    parser.add_argument(
        "--event-path",
        dest="event_path",
        default=os.environ.get("GITHUB_EVENT_PATH", ""),
    )

    args = parser.parse_args()

    asyncio.run(
        run(
            prompt=args.prompt,
            prompt_source=args.prompt_source,
            recipe_source=args.recipe_source,
            attractor_source=args.attractor_source,
            provider=args.provider,
            model=args.model,
            github_token=args.github_token,
            event_path=args.event_path,
        )
    )
