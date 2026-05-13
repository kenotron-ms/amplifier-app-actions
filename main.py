"""GitHub Actions entrypoint — reads INPUT_* env vars and calls cli.run()."""

import asyncio
import os

from amplifier_app_actions import cli


def main() -> None:
    """Read INPUT_* env vars and dispatch to cli.run() via asyncio.run()."""
    prompt = os.getenv("INPUT_PROMPT", "")
    prompt_source = os.getenv("INPUT_PROMPT_SOURCE", "")
    recipe_source = os.getenv("INPUT_RECIPE_SOURCE", "")
    attractor_source = os.getenv("INPUT_ATTRACTOR_SOURCE", "")
    provider = os.getenv("INPUT_PROVIDER", "anthropic")
    model = os.getenv("INPUT_MODEL", "")
    github_token = os.getenv("INPUT_GITHUB_TOKEN", os.getenv("GITHUB_TOKEN", ""))
    event_path = os.getenv("GITHUB_EVENT_PATH", "")

    asyncio.run(
        cli.run(
            prompt=prompt,
            prompt_source=prompt_source,
            recipe_source=recipe_source,
            attractor_source=attractor_source,
            provider=provider,
            model=model,
            github_token=github_token,
            event_path=event_path,
        )
    )


if __name__ == "__main__":
    main()
