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
    {
        "github-tools",
        "github-tools-dtu",
        "github-tools-amplifier-dev",
        "attractor-pipeline",  # generic DOT pipeline runner (loop-pipeline as outer orchestrator)
    }
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


def _parse_goal(ctx_prefix: str) -> str:
    """Extract a one-line goal string from a GitHub event context prefix.

    Looks for the ``[issues: #N in owner/repo]`` header and ``Title:`` line
    that ``format_context_block`` produces.  Falls back to a generic string
    when the prefix is absent or unparseable.
    """
    import re as _re

    if not ctx_prefix:
        return "Run the pipeline."
    m = _re.search(
        r"\[(?P<type>issues|pull_request): #(?P<number>\d+) in (?P<owner>[^/\]]+)/(?P<repo>[^\]]+)\]",
        ctx_prefix,
    )
    t = _re.search(r"Title: (.+)", ctx_prefix)
    if m:
        title = t.group(1).strip() if t else "Pipeline run"
        return f"Issue #{m.group('number')} in {m.group('owner')}/{m.group('repo')}: {title}".replace(
            '"', "'"
        )
    return "Run the pipeline."


def _register_spawn_capability(session: Any, prepared: Any) -> None:
    """Register ``session.spawn`` so ``loop-pipeline`` selects AmplifierBackend.

    This is the required wiring step from the attractor APP-INTEGRATION-GUIDE
    (Path B).  Without it, ``_build_backend()`` in ``loop-pipeline`` does not
    find ``session.spawn`` and falls back to ``DirectProviderBackend`` — all
    nodes run inline in one session and ``nodes_completed`` stays 0.

    Must be called on the SESSION WHOSE ORCHESTRATOR IS ``loop-pipeline``, not
    on a parent session.  That is what makes the difference vs the earlier
    failed attempts that registered on the wrong (github-tools) session.

    Pattern from: amplifier-bundle-attractor/docs/APP-INTEGRATION-GUIDE.md
    """
    from amplifier_foundation import Bundle

    async def spawn_capability(
        agent_name: str,
        instruction: str,
        parent_session: Any,
        agent_configs: dict[str, Any],
        sub_session_id: str | None = None,
        orchestrator_config: dict[str, Any] | None = None,
        parent_messages: list[dict[str, Any]] | None = None,
        provider_preferences: list | None = None,
        self_delegation_depth: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        config: dict[str, Any] = {}
        if agent_name in agent_configs:
            config = agent_configs[agent_name]
        elif hasattr(prepared, "bundle") and agent_name in (
            prepared.bundle.agents or {}
        ):
            config = prepared.bundle.agents[agent_name]

        child_bundle = Bundle(
            name=agent_name or "pipeline-node",
            version="1.0.0",
            session=config.get("session", {}),
            providers=config.get("providers", []),
            tools=config.get("tools", []),
            hooks=config.get("hooks", []),
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
        # Attractor pipelines use a dedicated pipeline bundle (loop-pipeline as
        # outer orchestrator) regardless of INPUT_BUNDLE. The INPUT_BUNDLE
        # controls the tool session for prompt/recipe; the pipeline bundle
        # controls the DOT execution session.
        attractor_bundle = _resolve_bundle_path("attractor-pipeline", action_path)
        return await _run_attractor(
            content=content,
            ctx_prefix=ctx_prefix,
            bundle_path=attractor_bundle,
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


async def _run_attractor(
    content: str,
    ctx_prefix: str,
    bundle_path: str,
    cwd: str | None = None,
) -> int:
    """Run an Attractor DOT pipeline in-process via the Python API (Path B).

    Why in-process Python API (not ``amplifier run -B bundle``):
    - ``amplifier run`` ignores ``session.orchestrator.module`` from the bundle;
      it always drives the session with its own built-in agent loop regardless
      of what the bundle declares.  Every test showed flat-agent behaviour.
    - The Python API (``load_bundle`` → compose overlay → ``create_session``) IS
      the supported path for custom orchestrators, per APP-INTEGRATION-GUIDE.

    Why ``_register_spawn_capability`` must be called on THIS session:
    - ``create_initialized_session`` wires the CLI's standard ``session.spawn``
      (``register_session_spawning``), but that uses ``spawn_sub_session`` which
      does NOT install agent bundle modules.  When ``loop-pipeline`` tries to
      spawn per-node child sessions via that capability, the grandchildren
      succeed, but our earlier attempts registered on the wrong (outer) session.
    - Here we register AFTER ``create_initialized_session``, overriding with a
      ``prepared.spawn()``-based capability on the session whose orchestrator IS
      ``loop-pipeline``.  ``_build_backend()`` then finds ``session.spawn`` →
      ``AmplifierBackend`` → per-node child sessions → ``nodes_completed > 0``.
    """
    from amplifier_app_cli.console import console as cli_console
    from amplifier_app_cli.session_runner import (
        SessionConfig,
        create_initialized_session,
    )
    from amplifier_foundation import Bundle, load_bundle
    from rich.markdown import Markdown

    if not Path(content).exists():
        raise FileNotFoundError(
            f"Attractor DOT file not found: {content}. "
            "Ensure actions/checkout is present in your workflow."
        )

    goal = _parse_goal(ctx_prefix)
    dot_source = Path(content).read_text(encoding="utf-8")

    # --- Bundle preparation -------------------------------------------
    # Compose base pipeline bundle with a dot_source overlay, then prepare.
    # prepare() installs loop-pipeline and loop-agent in the Python env.
    prev_cwd = os.getcwd()
    if cwd:
        os.chdir(cwd)
    try:
        base_bundle = await load_bundle(bundle_path)
        overlay = Bundle(
            name="attractor-overlay",
            version="1.0.0",
            session={
                "orchestrator": {
                    "module": "loop-pipeline",
                    "config": {"dot_source": dot_source},
                }
            },
        )
        composed = base_bundle.compose(overlay)
        prepared = await composed.prepare()
    finally:
        if cwd:
            os.chdir(prev_cwd)

    # --- Session creation with full CLI wiring -----------------------
    session_config = SessionConfig(
        config={},
        search_paths=[Path(cwd) if cwd else Path.cwd()],
        verbose=False,
        prepared_bundle=prepared,
        bundle_name=bundle_path,
    )
    initialized = await create_initialized_session(session_config, cli_console)

    try:
        # Override the CLI's standard session.spawn with one backed by
        # prepared.spawn() so loop-pipeline's _build_backend() picks
        # AmplifierBackend and spawns per-node child sessions.
        _register_spawn_capability(initialized.session, prepared)

        response = await initialized.session.execute(goal)
        if response:
            cli_console.print(Markdown(response))
        return 0
    except Exception as exc:  # noqa: BLE001
        cli_console.print(f"[red]Error:[/red] {exc}")
        return 1
    finally:
        await initialized.cleanup()


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
