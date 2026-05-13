---
name: amplifier-app-actions
version: 0.1.0
includes:
  - git+https://github.com/microsoft/amplifier-foundation@main
  - git+https://github.com/microsoft/amplifier-bundle-recipes@main
  - bundle: git+https://github.com/microsoft/amplifier-bundle-digital-twin-universe@main

providers:
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
  - module: provider-openai
    source: git+https://github.com/microsoft/amplifier-module-provider-openai@main
  - module: provider-github-copilot
    source: git+https://github.com/microsoft/amplifier-module-provider-github-copilot@main
---

# amplifier-app-actions Bundle

This bundle composes three upstream bundles:

- **Foundation** — provides base Amplifier capabilities, core agents, and the
  standard tool palette.
- **Recipes bundle** — provides the Amplifier recipe engine and recipe-aware
  agents pulled from `microsoft/amplifier-bundle-recipes`.
- **Digital Twin Universe** — provides the `launch_dtu` tool and DTU-aware
  agents for spinning up isolated, containerised reproduction environments pulled
  from `microsoft/amplifier-bundle-digital-twin-universe`.

## GitHub-specific tools

The following tools are **not** declared in this bundle file. They are mounted
programmatically by `session_factory.py` at session-creation time, after the
bundle is loaded and prepared:

| Tool | Description |
|------|-------------|
| `github_post_comment` | Post or update a comment on an issue or pull request |
| `github_add_label` | Add a label to an issue or pull request |
| `github_checkout_repo` | Shallow-clone the repository for file-level inspection |
| `launch_dtu` | Launch an isolated Digital Twin Universe container to reproduce issues |

Mounting these tools in code (rather than in the bundle declaration) allows each
invocation to inject the `github_token` from the calling environment, avoiding
any credential leakage into bundle configuration.

@amplifier_app_actions:context/reproduction.md
