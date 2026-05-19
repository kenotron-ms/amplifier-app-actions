---
bundle:
  name: attractor-pipeline
  version: 0.1.0
  description: >
    Generic DOT pipeline runner for amplifier-app-actions. Mounts loop-pipeline
    as the outer session orchestrator so the module is installed at bundle-prepare
    time. The DOT graph is injected at runtime via a wrapper-generated overlay
    bundle (dot_source in orchestrator config).

    Child agent sessions (pipeline-agent-anthropic) get filesystem, bash, search,
    AND GitHub API tools so pipeline nodes can check out repos, post comments, and
    add labels without extra configuration.

includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-attractor@main

providers:
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
    config:
      default_model: claude-sonnet-4-6

# loop-pipeline IS the outer orchestrator — installed at bundle-prepare time.
# dot_source or dot_file is provided by the wrapper overlay; do not hardcode here.
session:
  orchestrator:
    module: loop-pipeline
    source: git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=modules/loop-pipeline
    config:
      profiles:
        anthropic: pipeline-agent-anthropic
  context:
    module: context-simple
    source: git+https://github.com/microsoft/amplifier-module-context-simple@main

# Orchestrator-level tools (used for pipeline management, not child sessions)
tools:
  - module: tool-filesystem
    source: git+https://github.com/microsoft/amplifier-module-tool-filesystem@main
  - module: tool-bash
    source: git+https://github.com/microsoft/amplifier-module-tool-bash@main
    config:
      timeout: 120
  - module: tool-search
    source: git+https://github.com/microsoft/amplifier-module-tool-search@main

# Child agent spawned per DOT node by AmplifierBackend.
# Full tool set: base coding tools + GitHub API tools.
agents:
  pipeline-agent-anthropic:
    session:
      orchestrator:
        module: loop-agent
        source: git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=modules/loop-agent
        config:
          max_tool_rounds_per_input: 50
          default_command_timeout_ms: 120000
    providers:
      - module: provider-anthropic
        source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
        config:
          default_model: claude-sonnet-4-6
    tools:
      - module: tool-filesystem
        source: git+https://github.com/microsoft/amplifier-module-tool-filesystem@main
      - module: tool-bash
        source: git+https://github.com/microsoft/amplifier-module-tool-bash@main
        config:
          timeout: 120
      - module: tool-search
        source: git+https://github.com/microsoft/amplifier-module-tool-search@main
      # GitHub tools — no source: needed, discovered via entry points from
      # the installed amplifier_app_actions package (same Python environment).
      - module: tool-github-post-comment
      - module: tool-github-add-label
      - module: tool-github-checkout-repo
---

# attractor-pipeline Bundle

Generic DOT pipeline runner. Uses `loop-pipeline` as the outer session orchestrator
so the module is installed at bundle-prepare time — fixing the silent
`DirectProviderBackend` fallback that caused `nodes_completed: 0`.

## How the wrapper uses this bundle

1. `_run_attractor()` reads the DOT file from `attractor_source`
2. Generates a temp overlay bundle that `includes:` this bundle and adds
   `session.orchestrator.config.dot_source` with the DOT content inline
3. Runs `amplifier run -b <overlay> "<goal>"`

The outer `loop-pipeline` session then has AmplifierBackend available
(CLI registers `session.spawn`), spawning `pipeline-agent-anthropic` per node.

## Child agent tools

| Tool | Description |
|------|-------------|
| `tool-filesystem` | File read/write/list |
| `tool-bash` | Shell commands (120 s timeout) |
| `tool-search` | Web/code search |
| `github_post_comment` | Post or update issue/PR comments |
| `github_add_label` | Add labels to issues/PRs |
| `github_checkout_repo` | Shallow-clone repos for inspection |
