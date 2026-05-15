"""GitHub Actions entrypoint — reads INPUT_* env vars and calls wrapper.run()."""

import asyncio
import os
import sys

from amplifier_app_actions import wrapper


def main() -> None:
    """Read INPUT_* env vars and dispatch to wrapper.run() via asyncio.run()."""
    returncode = asyncio.run(
        wrapper.run(
            prompt=os.getenv("INPUT_PROMPT", ""),
            prompt_source=os.getenv("INPUT_PROMPT_SOURCE", ""),
            recipe_source=os.getenv("INPUT_RECIPE_SOURCE", ""),
            attractor_source=os.getenv("INPUT_ATTRACTOR_SOURCE", ""),
            provider=os.getenv("INPUT_PROVIDER", "anthropic"),
            model=os.getenv("INPUT_MODEL", ""),
            bundle=os.getenv("INPUT_BUNDLE", "triage-safe"),
            github_token=os.getenv("INPUT_GITHUB_TOKEN", os.getenv("GITHUB_TOKEN", "")),
            event_path=os.getenv("GITHUB_EVENT_PATH", ""),
            enable_reproduction=os.getenv("INPUT_ENABLE_REPRODUCTION", "").lower()
            == "true",
        )
    )
    sys.exit(returncode)


if __name__ == "__main__":
    main()
