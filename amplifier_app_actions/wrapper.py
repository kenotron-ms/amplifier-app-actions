"""Amplifier session runner — creates and executes sessions in-process.

Uses amplifier_app_cli.session_runner.create_initialized_session as the
single entry point for all session creation, avoiding subprocess overhead
and the Session-not-found false-positive exit code that subprocess mode
triggered (amplifier-app-cli bug: execute_single calls store.get_metadata()
before store.save(), which raises FileNotFoundError for brand-new sessions).

Design notes:
  - Prompt/attractor: create_initialized_session → session.execute(prompt)
  - Recipe: create_initialized_session → coordinator.get("tools")["recipes"].execute(...)
  - Recipe YAML is normalised before execution (_normalize_recipe_path) because
    the recipes engine regex requires {{var}} without spaces.
"""

from __future__ import annotations

import asyncio
import os
import re
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
    """Resolve a built-in bundle alias to a file:// URI.

    Built-in aliases (triage-safe, triage-repro, triage-amplifier) resolve
    to ``action_path/bundles/<alias>.bundle.md``.  Any other value is returned
    unchanged so callers can pass arbitrary local or remote paths.
    """
    if bundle in _BUILT_IN_BUNDLES:
        return "file://" + str(action_path / "bundles" / f"{bundle}.bundle.md")
    return bundle


async def _create_session(
    bundle_path: str,
    cwd: str | None = None,
) -> tuple[Any, Any]:
    """Load bundle and create an initialised Amplifier session in-process.

    Uses create_initialized_session — the single canonical entry point for all
    session creation in amplifier-app-cli.  It wires up display system,
    session spawning, approval system, and all other capabilities in the
    correct order.

    Returns (InitializedSession, Console).
    """
    from amplifier_app_cli.console import console as cli_console  # Rich Console
    from amplifier_app_cli.session_runner import (
        SessionConfig,
        create_initialized_session,
    )
    from amplifier_foundation import load_bundle

    # Change directory so relative @mention paths and bundle source resolution
    # anchor correctly to the action root (mirrors what cwd= did for subprocesses).
    prev_cwd = os.getcwd()
    if cwd:
        os.chdir(cwd)
    try:
        bundle = await load_bundle(bundle_path)
        prepared = await bundle.prepare()
    finally:
        if cwd:
            os.chdir(prev_cwd)

    session_config = SessionConfig(
        config={},
        search_paths=[Path(cwd) if cwd else Path.cwd()],
        verbose=False,
        prepared_bundle=prepared,
        bundle_name=bundle_path,
    )

    initialized = await create_initialized_session(session_config, cli_console)
    return initialized, cli_console


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
    amplifier_bin: str = "amplifier",  # kept for API compat, unused in in-process mode
) -> int:
    """Create an Amplifier session in-process and execute the instruction.

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
        AI provider override (e.g. 'anthropic').  Currently informational —
        the bundle specifies the provider; explicit override support is a TODO.
    model:
        Model name override.  Currently informational — the bundle specifies the
        model; explicit override support is a TODO.
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
        Ignored — kept for backward-compatible call sites.

    Returns
    -------
    int
        0 on success, 1 on failure.
    """
    # Resolve action_path to parent of package directory if not supplied
    if action_path is None:
        action_path = Path(__file__).parent.parent

    # Handle enable_reproduction: upgrade default bundle to github-tools-dtu
    effective_bundle = bundle
    if enable_reproduction and bundle == _DEFAULT_BUNDLE:
        effective_bundle = "github-tools-dtu"

    # Resolve built-in bundle aliases to absolute file:// paths
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

    # Use action_path as the working directory for bundle-relative resolution.
    action_cwd = str(action_path)

    if itype == InstructionType.RECIPE:
        return await _run_recipe(
            content=content,
            event=event,
            event_path=event_path,
            bundle_path=bundle_path,
            cwd=action_cwd,
        )
    elif itype == InstructionType.ATTRACTOR:
        return await _run_attractor(
            content=content,
            ctx_prefix=ctx_prefix,
            bundle_path=bundle_path,
            cwd=action_cwd,
        )
    else:
        return await _run_prompt_or_attractor(
            itype=itype,
            content=content,
            ctx_prefix=ctx_prefix,
            bundle_path=bundle_path,
            cwd=action_cwd,
        )


def _register_spawn_capability(session: Any, prepared: Any) -> None:
    """Register session.spawn so loop-pipeline uses AmplifierBackend.

    Each DOT pipeline node gets its own child session with full tool access.
    Without this, loop-pipeline silently falls back to DirectProviderBackend
    (LLM-only calls, no tools).

    Reference: amplifier-bundle-attractor/docs/APP-INTEGRATION-GUIDE.md Path B
    """
    from amplifier_foundation import Bundle

    async def spawn_capability(
        agent_name: str,
        instruction: str,
        parent_session: Any,
        agent_configs: dict[str, dict[str, Any]],
        sub_session_id: str | None = None,
        orchestrator_config: dict[str, Any] | None = None,
        parent_messages: list[dict[str, Any]] | None = None,
        provider_preferences: list | None = None,
        self_delegation_depth: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if agent_name in agent_configs:
            config = agent_configs[agent_name]
        elif hasattr(prepared, "bundle") and agent_name in prepared.bundle.agents:
            config = prepared.bundle.agents[agent_name]
        else:
            available = list(agent_configs.keys())
            if hasattr(prepared, "bundle"):
                available += list(prepared.bundle.agents.keys())
            raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

        child_bundle = Bundle(
            name=agent_name,
            version="1.0.0",
            session=config.get("session", {}),
            providers=config.get("providers", []),
            tools=config.get("tools", []),
            hooks=config.get("hooks", []),
            instruction=(
                config.get("instruction") or config.get("system", {}).get("instruction")
            ),
        )

        return await prepared.spawn(
            child_bundle=child_bundle,
            instruction=instruction,
            session_id=sub_session_id,
            parent_session=parent_session,
            orchestrator_config=orchestrator_config,
            parent_messages=parent_messages,
            provider_preferences=provider_preferences,
            self_delegation_depth=self_delegation_depth,
        )

    session.coordinator.register_capability("session.spawn", spawn_capability)


async def _run_attractor(
    content: str,
    ctx_prefix: str,
    bundle_path: str,
    cwd: str | None = None,
) -> int:
    """Run an Attractor DOT pipeline via loop-pipeline with AmplifierBackend.

    Path B from the Attractor App Integration Guide:
    - Composes base bundle with loop-pipeline as the orchestrator
    - Registers session.spawn so each DOT node gets its own child session
    - GitHub tools flow to child sessions via Bundle.compose() inheritance

    Without register_spawn_capability, loop-pipeline falls back to
    DirectProviderBackend (no tools, no per-node isolation).
    """
    from rich.markdown import Markdown
    from amplifier_app_cli.console import console as cli_console
    from amplifier_foundation import Bundle, load_bundle

    # Read the DOT file content
    dot_path = Path(content)
    if not dot_path.exists():
        raise FileNotFoundError(
            f"Attractor DOT file not found: {content}. "
            "Ensure actions/checkout is present in your workflow."
        )
    dot_source = dot_path.read_text(encoding="utf-8")

    # Inject issue coordinates into the DOT goal so pipeline nodes can
    # reference owner/repo/number via $goal. We extract only the structured
    # header (single line) — injecting the full body breaks the DOT parser
    # because issue text contains words that look like DOT node identifiers.
    if ctx_prefix:
        import re as _re
        # ctx_prefix header: "[issues: #N in owner/repo]"
        header_match = _re.search(
            r"\[(?P<type>issues|pull_request): #(?P<number>\d+) in (?P<owner>[^/\]]+)/(?P<repo>[^\]]+)\]",
            ctx_prefix,
        )
        title_match = _re.search(r"Title: (.+)", ctx_prefix)
        if header_match:
            owner = header_match.group("owner")
            repo = header_match.group("repo")
            number = header_match.group("number")
            title = title_match.group(1).strip() if title_match else "Issue"
            # Short, safe single-line goal — no embedded newlines or special chars
            goal_text = (
                f"Issue #{number} in {owner}/{repo}: {title}"
            ).replace('"', "'")
            dot_source = _re.sub(
                r'goal\s*=\s*"[^"]*"',
                f'goal="{goal_text}"',
                dot_source,
                count=1,
            )

    # Change to cwd for bundle resolution (mirrors _create_session behaviour)
    prev_cwd = os.getcwd()
    if cwd:
        os.chdir(cwd)
    try:
        # Load base bundle (github-tools + GitHub tools + Attractor bundle)
        base_bundle = await load_bundle(bundle_path)

        # Compose with loop-pipeline as the session orchestrator.
        # Bundle.compose() merges parent tool list into child — GitHub tools
        # declared in the base bundle YAML flow to per-node child sessions.
        import uuid
        # Unique logs_root per run — loop-pipeline defaults to a fixed shared
        # /tmp/attractor-pipeline path which causes stale checkpoint reuse across runs.
        run_id = uuid.uuid4().hex[:8]
        logs_root = str(Path(tempfile.gettempdir()) / f"triage-pipeline-{run_id}")

        overlay = Bundle(
            name="triage-pipeline",
            version="1.0.0",
            session={
                "orchestrator": {
                    "module": "loop-pipeline",
                    # Explicit source so the module resolver uses the Attractor
                    # bundle's loop-pipeline, not a cached module with a similar name.
                    "source": (
                        "git+https://github.com/microsoft/amplifier-bundle-attractor"
                        "@main#subdirectory=modules/loop-pipeline"
                    ),
                    "config": {
                        "dot_source": dot_source,
                        "logs_root": logs_root,
                    },
                }
            },
        )
        composed = base_bundle.compose(overlay)
        prepared = await composed.prepare()
    finally:
        if cwd:
            os.chdir(prev_cwd)

    session = await prepared.create_session(
        session_cwd=Path(cwd) if cwd else Path.cwd()
    )

    # Register session.spawn — activates AmplifierBackend for per-node sessions
    _register_spawn_capability(session, prepared)

    try:
        # Issue context (GitHub event data) is the instruction preamble
        instruction = ctx_prefix + "\nRun the triage pipeline."
        response = await session.execute(instruction)
        if response:
            cli_console.print(Markdown(response))
        return 0
    except Exception as exc:  # noqa: BLE001
        cli_console.print(f"[red]Error:[/red] {exc}")
        return 1
    finally:
        await session.cleanup()


async def _run_prompt_or_attractor(
    itype: InstructionType,
    content: str,
    ctx_prefix: str,
    bundle_path: str,
    cwd: str | None = None,
) -> int:
    """Create an in-process session and execute a prompt or prompt_source."""
    from rich.markdown import Markdown

    full_prompt = f"{ctx_prefix}{content}"

    initialized, console = await _create_session(bundle_path, cwd)
    try:
        response = await initialized.session.execute(full_prompt)
        if response:
            console.print(Markdown(response))
        return 0
    except Exception as exc:  # noqa: BLE001
        # Bubble up — transient provider errors (500/overloaded) should fail the
        # GHA job and let GHA retry, not be masked by internal retry logic.
        # Only safe to retry if no github_post_comment has been called yet.
        console.print(f"[red]Error:[/red] {exc}")
        return 1
    finally:
        await initialized.cleanup()


async def _run_recipe(
    content: str,
    event: dict[str, Any] | None,
    event_path: str,
    bundle_path: str,
    cwd: str | None = None,
) -> int:
    """Create an in-process session and execute a recipe."""
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

    # Normalise {{ var }} → {{var}} before the recipes engine sees the file.
    recipe_abs_raw = str(Path(content).resolve())
    recipe_abs, _tmp = _normalize_recipe_path(recipe_abs_raw)

    initialized, console = await _create_session(bundle_path, cwd)
    try:
        coordinator = initialized.session.coordinator
        tools = coordinator.get("tools") or {}
        recipe_tool = tools.get("recipes")
        if recipe_tool is None:
            available = sorted(tools.keys())
            raise RuntimeError(
                f"Tool 'recipes' not found. Available: {', '.join(available)}"
            )
        await recipe_tool.execute(
            {
                "operation": "execute",
                "recipe_path": recipe_abs,
                "context": recipe_context,
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error:[/red] {exc}")
        return 1
    finally:
        if _tmp is not None:
            Path(_tmp.name).unlink(missing_ok=True)
        await initialized.cleanup()


def cli_main() -> None:
    """CLI entry point for the ``amplifier-triage`` command.

    Parses command-line flags and dispatches to :func:`run` via asyncio.run.
    The return code is propagated via sys.exit.
    """
    import sys
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
