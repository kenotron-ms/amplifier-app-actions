"""Thin wrapper around the amplifier CLI — builds argv and runs subprocess.

This module is the single dispatch point for all Amplifier CLI invocations.
It never uses shell=True; all arguments are passed as discrete elements to
asyncio.create_subprocess_exec so injection payloads in event fields cannot
break out of the final prompt argument.

Design choice recorded here:
  recipe context is passed as inline JSON in a single argv element
  (context=<json>), not via a @file reference.  The CLI's tool invoke
  command treats each positional argument as a key=value pair; inline JSON
  avoids the need for CLI support of @file syntax and keeps the argument
  list deterministic for tests.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from amplifier_app_actions.events import format_context_block, parse_event
from amplifier_app_actions.instruction import InstructionType, resolve_instruction

_BUILT_IN_BUNDLES: frozenset[str] = frozenset(
    {"triage-safe", "triage-repro", "triage-amplifier"}
)
_DEFAULT_BUNDLE = "triage-safe"


def _resolve_bundle_path(bundle: str, action_path: Path) -> str:
    """Resolve a built-in bundle alias to an absolute path.

    Built-in aliases (triage-safe, triage-repro, triage-amplifier) resolve
    to ``action_path/bundles/<alias>.bundle.md``.  Any other value is returned
    unchanged so callers can pass arbitrary local or remote paths.
    """
    if bundle in _BUILT_IN_BUNDLES:
        return str(action_path / "bundles" / f"{bundle}.bundle.md")
    return bundle


async def run(
    prompt: str = "",
    prompt_source: str = "",
    recipe_source: str = "",
    attractor_source: str = "",
    provider: str = "",
    model: str = "",
    bundle: str = _DEFAULT_BUNDLE,
    github_token: str = "",
    event_path: str = "",
    enable_reproduction: bool = False,
    action_path: Path | None = None,
    amplifier_bin: str = "amplifier",
) -> int:
    """Build argv and invoke the amplifier CLI.  Return the subprocess exit code.

    Parameters
    ----------
    prompt:
        Inline prompt text to pass directly.
    prompt_source:
        Path to a file whose contents become the prompt.
    recipe_source:
        Path to an Amplifier recipe YAML file.
    attractor_source:
        Path to an attractor/guidance DOT file.
    provider:
        AI provider override (e.g. 'anthropic', 'openai').  Empty = use bundle default.
    model:
        Model name override.  Empty = use provider default.
    bundle:
        Bundle alias ('triage-safe', 'triage-repro', 'triage-amplifier') or
        any path/URL.  Aliases are resolved relative to action_path.
    github_token:
        GitHub token to inject into GITHUB_TOKEN env via setdefault.
    event_path:
        Path to the GitHub event JSON file.  When it exists the event is
        parsed and a context block is prepended to the prompt.
    enable_reproduction:
        When True and bundle is the default ('triage-safe'), upgrade to
        'triage-repro' (which includes digital-twin-universe).
    action_path:
        Repository root for resolving built-in bundle aliases.  Defaults to
        the parent directory of this package.
    amplifier_bin:
        Name or path of the amplifier binary.

    Returns
    -------
    int
        Process exit code (0 on success).
    """
    # Resolve action_path to parent of package directory if not supplied
    if action_path is None:
        action_path = Path(__file__).parent.parent

    # Handle enable_reproduction: upgrade default bundle to triage-repro
    effective_bundle = bundle
    if enable_reproduction and bundle == _DEFAULT_BUNDLE:
        effective_bundle = "triage-repro"

    # Resolve built-in bundle aliases to absolute paths
    bundle_path = _resolve_bundle_path(effective_bundle, action_path)

    # Export GITHUB_TOKEN via setdefault only — don't overwrite the runner token
    if github_token:
        os.environ.setdefault("GITHUB_TOKEN", github_token)

    # Resolve instruction — raises ValueError/FileNotFoundError on bad input
    itype, content = resolve_instruction(
        prompt=prompt,
        prompt_source=prompt_source,
        recipe_source=recipe_source,
        attractor_source=attractor_source,
    )

    # Parse event and build context prefix (only when file actually exists)
    event: dict[str, Any] | None = None
    ctx_prefix = ""
    if event_path and Path(event_path).exists():
        event = parse_event(event_path)
        ctx_prefix = format_context_block(event) + "\n\n"

    if itype == InstructionType.RECIPE:
        return await _run_recipe(
            content=content,
            event=event,
            event_path=event_path,
            amplifier_bin=amplifier_bin,
        )
    else:
        return await _run_prompt_or_attractor(
            itype=itype,
            content=content,
            ctx_prefix=ctx_prefix,
            bundle_path=bundle_path,
            provider=provider,
            model=model,
            amplifier_bin=amplifier_bin,
        )


async def _run_prompt_or_attractor(
    itype: InstructionType,
    content: str,
    ctx_prefix: str,
    bundle_path: str,
    provider: str,
    model: str,
    amplifier_bin: str,
) -> int:
    """Build and run: amplifier run --bundle <path> [--provider P] [--model M] --mode single -- <prompt>"""
    if itype == InstructionType.ATTRACTOR:
        full_prompt = (
            f"{ctx_prefix}"
            f"Execute the attractor at: {content}\n\n"
            "Call the attractor tool to run it directly."
        )
    else:
        # PROMPT or PROMPT_SOURCE — content is already the text
        full_prompt = f"{ctx_prefix}{content}"

    argv = [amplifier_bin, "run", "--bundle", bundle_path]
    if provider:
        argv += ["--provider", provider]
    if model:
        argv += ["--model", model]
    argv += ["--mode", "single", "--", full_prompt]

    proc = await asyncio.create_subprocess_exec(*argv)
    await proc.wait()
    return proc.returncode or 0


async def _run_recipe(
    content: str,
    event: dict[str, Any] | None,
    event_path: str,
    amplifier_bin: str,
) -> int:
    """Build and run: amplifier tool invoke recipes operation=execute recipe_path=... context=..."""
    recipe_context: dict[str, Any] = {}
    if event is not None:
        recipe_context["context"] = {
            "number": event["number"],
            "owner": event["owner"],
            "repo": event["repo"],
            "title": event["title"],
            "body": event["body"],
            "author": event["author"],
            "labels": event["labels"],
            "event_type": event["event_type"],
        }
    if event_path:
        recipe_context["github_event_path"] = event_path

    # Inline JSON as a single argv element — no shell quoting needed,
    # no @file CLI support required.  See module docstring for rationale.
    context_json = json.dumps(recipe_context)
    recipe_abs = str(Path(content).resolve())

    argv = [
        amplifier_bin,
        "tool",
        "invoke",
        "recipes",
        "operation=execute",
        f"recipe_path={recipe_abs}",
        f"context={context_json}",
    ]

    proc = await asyncio.create_subprocess_exec(*argv)
    await proc.wait()
    return proc.returncode or 0


def cli_main() -> None:
    """CLI entry point for the ``amplifier-triage`` command.

    Parses command-line flags and dispatches to :func:`run` via asyncio.run.
    The return code from the amplifier subprocess is propagated via sys.exit.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="amplifier-triage")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prompt", default="")
    group.add_argument("--prompt-source", dest="prompt_source", default="")
    group.add_argument("--recipe-source", dest="recipe_source", default="")
    group.add_argument("--attractor-source", dest="attractor_source", default="")

    parser.add_argument("--provider", default="anthropic")
    parser.add_argument("--model", default="")
    parser.add_argument("--bundle", default=_DEFAULT_BUNDLE)
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

    returncode = asyncio.run(
        run(
            prompt=args.prompt,
            prompt_source=args.prompt_source,
            recipe_source=args.recipe_source,
            attractor_source=args.attractor_source,
            provider=args.provider,
            model=args.model,
            bundle=args.bundle,
            github_token=args.github_token,
            event_path=args.event_path,
        )
    )
    sys.exit(returncode)
