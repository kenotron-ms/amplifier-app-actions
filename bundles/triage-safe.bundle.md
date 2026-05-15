---
bundle:
  name: triage-safe
  version: 0.1.0

includes:
  # Full foundation — registers the "foundation:" namespace so that
  # foundation:explorer, foundation:zen-architect, foundation:bug-hunter, etc.
  # are resolvable as delegate targets.
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main

tools:
  # GitHub-specific tools for issue triage — declared with local source paths
  # so they are available in all sessions without requiring the package to be
  # installed in the amplifier runtime environment.
  - module: tool-github-post-comment
    source: ../amplifier_app_actions/tools/github_post_comment
  - module: tool-github-add-label
    source: ../amplifier_app_actions/tools/github_add_label
  - module: tool-github-checkout-repo
    source: ../amplifier_app_actions/tools/github_checkout_repo
---

# triage-safe Bundle

Default bundle for automated GitHub issue and PR triage workflows.

Includes foundation (full namespace) plus the three GitHub interaction tools.

## Tools

| Tool | Description |
|------|-------------|
| `github_post_comment` | Post or update a comment on an issue or pull request |
| `github_add_label` | Add a label to an issue or pull request |
| `github_checkout_repo` | Shallow-clone the repository for file-level inspection |

## Bundle Tiers

- **triage-safe** (this bundle): automated triage, no DTU
- **triage-repro**: adds `digital-twin-universe` for Incus/DTU issue reproduction
- **triage-amplifier**: adds amplifier-dev tooling for Amplifier repo triaging
