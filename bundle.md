---
bundle:
  name: amplifier-app-actions
  version: 0.1.0

includes:
  # Full foundation — required to register the "foundation:" namespace so that
  # foundation:explorer, foundation:zen-architect, foundation:bug-hunter, etc.
  # are resolvable as delegate targets. The three slim behavior includes
  # (sessions, streaming-ui, agents) and the recipes behavior are all subsumed
  # by this single include; listing them separately registered them under
  # "behavior-agents" / "behavior-recipes" namespaces, NOT "foundation".
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main
  # DTU for issue reproduction
  - bundle: git+https://github.com/microsoft/amplifier-bundle-digital-twin-universe@main

session:
  raw: true
  orchestrator:
    module: loop-streaming
    source: git+https://github.com/microsoft/amplifier-module-loop-streaming@main
    config:
      extended_thinking: true
  context:
    module: context-simple
    source: git+https://github.com/microsoft/amplifier-module-context-simple@main
    config:
      max_tokens: 200000
      compact_threshold: 0.8
      auto_compact: true

providers:
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
  - module: provider-openai
    source: git+https://github.com/microsoft/amplifier-module-provider-openai@main
  - module: provider-github-copilot
    source: git+https://github.com/microsoft/amplifier-module-provider-github-copilot@main

tools:
  # File operations — read, write, edit
  - module: tool-filesystem
    source: git+https://github.com/microsoft/amplifier-module-tool-filesystem@main
  # Code search — grep and glob (no web search)
  - module: tool-search
    source: git+https://github.com/microsoft/amplifier-module-tool-search@main
  # GitHub-specific tools for issue triage
  - module: tool-github-post-comment
  - module: tool-github-add-label
  - module: tool-github-checkout-repo
  - module: tool-launch-dtu
---

# amplifier-app-actions Bundle

This bundle composes two upstream bundles:

- **Foundation** (`microsoft/amplifier-foundation`) — registers the `foundation:`
  namespace so that `foundation:explorer`, `foundation:zen-architect`,
  `foundation:bug-hunter`, and all other standard agents are available as delegate
  targets. Also provides the delegate tool, sessions/streaming-ui behaviors, the
  recipes engine (via its own transitive include of `amplifier-bundle-recipes`),
  and the standard tool palette. This is the only way to register the `foundation:`
  namespace — the slim `#subdirectory=behaviors/agents.yaml` approach does NOT
  work because that nested bundle's name is `behavior-agents`, not `foundation`.
- **Digital Twin Universe** — provides the `launch_dtu` tool and DTU-aware
  agents for spinning up isolated, containerised reproduction environments pulled
  from `microsoft/amplifier-bundle-digital-twin-universe`.

## GitHub-specific tools

The following tools are declared with `git+https://...#subdirectory=...` sources
in `bundle.md` and listed under `tools:` in this bundle's frontmatter.  The
bundle loader fetches and mounts them during `prepare()`, so they are available in
**all** sessions — both the parent session and any child sessions spawned via
`session.spawn`:

| Tool | Description |
|------|-------------|
| `github_post_comment` | Post or update a comment on an issue or pull request |
| `github_add_label` | Add a label to an issue or pull request |
| `github_checkout_repo` | Shallow-clone the repository for file-level inspection |
| `launch_dtu` | Launch an isolated Digital Twin Universe container to reproduce issues |

Credentials are read from environment variables at call time; no token is passed
through bundle configuration.

@amplifier_app_actions:context/reproduction.md
