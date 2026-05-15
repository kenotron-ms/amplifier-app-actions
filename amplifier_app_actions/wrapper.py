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
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from amplifier_app_actions.events import format_context_block, parse_event
from amplifier_app_actions.instruction import InstructionType, resolve_instruction

# Matches Jinja2-style {{ var.path }} placeholders — with or without surrounding
# whitespace — and strips the spaces so the recipes engine's regex
# r"\{\{(\w+(?:\.\w+)*)\}\}" (which requires no spaces) can match them.
_JINJA_SPACE_RE = re.compile(r"\{\{\s*([\w]+(?:\.[\w]+)*)\s*\}\}")


def _normalize_recipe_path(recipe_path: str) -> tuple[str, Any]:
    """Return a recipe path whose {{var}} placeholders have no surrounding spaces.

    The recipes executor's substitution regex ``\\{\\{(\\w+(?:\\.\\w+)*)\\}\\}``
    requires no whitespace between ``{{`` and the variable name.  Recipe YAML
    files typically follow the Jinja2 convention ``{{ var }}`` (with spaces),
    so this function rewrites them to ``{{var}}`` in a temp file.

    Returns ``(path, tmp)`` where *tmp* is a NamedTemporaryFile that must be
    kept alive until the recipe finishes (or ``None`` if no rewriting was needed).
    """
    content = Path(recipe_path).read_text(encoding="utf-8")
    normalized = _JINJA_SPACE_RE.sub(r"{{\1}}", content)
    if normalized == content:
        return recipe_path, None  # nothing changed — use original
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    tmp.write(normalized)
    tmp.flush()
    return tmp.name, tmp


_BUILT_IN_BUNDLES: frozenset[str] = frozenset(
    {"github-tools", "github-tools-dtu", "github-tools-amplifier-dev"}
)
_DEFAULT_BUNDLE = "github-tools"


def _resolve_bundle_path(bundle: str, action_path: Path) -> str:
    """Resolve a built-in bundle alias to an absolute path.

    Built-in aliases (github-tools, github-tools-dtu, github-tools-amplifier-dev) resolve
    to ``action_path/bundles/<alias>.bundle.md``.  Any other value is returned
    unchanged so callers can pass arbitrary local or remote paths.
    """
    if bundle in _BUILT_IN_BUNDLES:
        return "file://" + str(action_path / "bundles" / f"{bundle}.bundle.md")
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
        Bundle alias ('github-tools', 'github-tools-dtu', 'github-tools-amplifier-dev') or
        any path/URL.  Aliases are resolved relative to action_path.
    github_token:
        GitHub token to inject into GITHUB_TOKEN env via setdefault.
    event_path:
        Path to the GitHub event JSON file.  When it exists the event is
        parsed and a context block is prepended to the prompt.
    enable_reproduction:
        When True and bundle is the default ('github-tools'), upgrade to
        'github-tools-dtu' (which includes digital-twin-universe).
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

    # Handle enable_reproduction: upgrade default bundle to github-tools-dtu
    effective_bundle = bundle
    if enable_reproduction and bundle == _DEFAULT_BUNDLE:
        effective_bundle = "github-tools-dtu"

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

    # Use action_path as the subprocess CWD so that relative paths inside
    # bundle files (includes, tool sources) resolve from the action root,
    # not from whatever directory the CLI was invoked from.
    action_cwd = str(action_path)

    if itype == InstructionType.RECIPE:
        return await _run_recipe(
            content=content,
            event=event,
            event_path=event_path,
            bundle_path=bundle_path,
            amplifier_bin=amplifier_bin,
            cwd=action_cwd,
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
            cwd=action_cwd,
        )


async def _run_prompt_or_attractor(
    itype: InstructionType,
    content: str,
    ctx_prefix: str,
    bundle_path: str,
    provider: str,
    model: str,
    amplifier_bin: str,
    cwd: str | None = None,
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

    # Pipe both stdout and stderr so we can detect known false-positive exit codes
    # while still streaming every line in real time (GHA sees live output).
    # The "Session not found" teardown error is emitted on stdout by the Amplifier
    # CLI, so we must tail stdout — not just stderr — to suppress it correctly.
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Keep only the tail of each stream for post-exit pattern matching.
    _stdout_tail: list[str] = []
    _stderr_tail: list[str] = []

    async def _drain_stdout() -> None:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace")
            sys.stdout.write(line)
            sys.stdout.flush()
            _stdout_tail.append(line)
            if len(_stdout_tail) > 20:
                _stdout_tail.pop(0)

    async def _drain_stderr() -> None:
        assert proc.stderr is not None
        async for raw in proc.stderr:
            line = raw.decode("utf-8", errors="replace")
            sys.stderr.write(line)
            sys.stderr.flush()
            _stderr_tail.append(line)
            if len(_stderr_tail) > 20:
                _stderr_tail.pop(0)

    await asyncio.gather(proc.wait(), _drain_stdout(), _drain_stderr())

    if proc.returncode:
        # Known false positive: Amplifier CLI session cleanup error that fires
        # after `--mode single` completes its work.  The agent finished, posted
        # its output, and the session teardown then failed to find the already-
        # cleaned-up session.  Treat this specific pattern as success.
        # Check both stdout and stderr — the CLI emits this on stdout.
        combined_tail = "".join(_stdout_tail + _stderr_tail)
        if re.search(r"Session '[0-9a-f-]+' not found", combined_tail):
            return 0

    return proc.returncode or 0


async def _run_recipe(
    content: str,
    event: dict[str, Any] | None,
    event_path: str,
    bundle_path: str,
    amplifier_bin: str,
    cwd: str | None = None,
) -> int:
    """Build and run: amplifier tool invoke -b <bundle> recipes operation=execute recipe_path=... context=..."""
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
            "base_ref": event.get("base_ref", ""),
            "head_ref": event.get("head_ref", ""),
        }
    if event_path:
        recipe_context["github_event_path"] = event_path

    # Normalize {{ var }} → {{var}}: the recipes engine regex requires no spaces
    # around variable names, but recipe YAMLs follow Jinja2 convention (with spaces).
    # _normalize_recipe_path writes a temp file with spaces stripped if needed.
    recipe_abs_raw = str(Path(content).resolve())
    recipe_abs, _tmp = _normalize_recipe_path(recipe_abs_raw)

    # Inline JSON as a single argv element — no shell quoting needed,
    # no @file CLI support required.  See module docstring for rationale.
    context_json = json.dumps(recipe_context)

    # Pass -b so recipe step agents inherit the correct bundle (e.g. github-tools-dtu
    # for DTU availability) rather than the user's ambient default bundle.
    argv = [
        amplifier_bin,
        "tool",
        "invoke",
        "-b",
        bundle_path,
        "recipes",
        "operation=execute",
        f"recipe_path={recipe_abs}",
        f"context={context_json}",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(*argv, cwd=cwd)
        await proc.wait()
        return proc.returncode or 0
    finally:
        if _tmp is not None:
            Path(_tmp.name).unlink(missing_ok=True)


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
