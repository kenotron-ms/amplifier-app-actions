---
bundle:
  name: github-tools
  version: 0.1.0

includes:
  # Full foundation — registers the "foundation:" namespace so that
  # foundation:explorer, foundation:zen-architect, foundation:bug-hunter, etc.
  # are resolvable as delegate targets.
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main
  # Recipes tool — required for recipe execution.
  - bundle: git+https://github.com/microsoft/amplifier-bundle-recipes@main
  # Attractor pipeline runner — enables DOT pipeline execution via tool-pipeline-run
  - bundle: git+https://github.com/microsoft/amplifier-bundle-attractor@main

providers:
  # Anthropic provider declared directly (not via foundation:providers/anthropic-sonnet
  # shorthand) because the foundation: namespace shorthand isn't reliably resolved
  # in in-process bundle loading — the namespace registers from includes above,
  # but the shorthand reference races against that registration.
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
    config:
      default_model: claude-sonnet-4-6

tools:
  # These tools are registered via entry points in pyproject.toml, so no
  # source: path is needed — Amplifier discovers them through the installed
  # amplifier_app_actions package (uv run --project ensures it is installed).
  - module: tool-github-post-comment
  - module: tool-github-add-label
  - module: tool-github-checkout-repo
---

# github-tools Bundle

Foundation + GitHub API interaction tools. The base bundle for all
amplifier-app-actions workflows.

## Tools

| Tool | Description |
|------|-------------|
| `github_post_comment` | Post or update a comment on an issue or pull request |
| `github_add_label` | Add a label to an issue or pull request |
| `github_checkout_repo` | Shallow-clone the repository for file-level inspection |

## Bundle Tiers

- **github-tools** (this bundle): foundation + GitHub API tools + Attractor pipeline execution support
- **github-tools-dtu**: adds `digital-twin-universe` for containerized execution
- **github-tools-amplifier-dev**: adds Amplifier-ecosystem dev tooling
