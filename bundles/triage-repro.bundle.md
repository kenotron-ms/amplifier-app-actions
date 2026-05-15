---
bundle:
  name: triage-repro
  version: 0.1.0

includes:
  # Compose the safe triage baseline
  - bundle: ./triage-safe.bundle.md
  # Add DTU infrastructure — dtu-profile-builder agent, amplifier-digital-twin CLI
  - bundle: git+https://github.com/microsoft/amplifier-bundle-digital-twin-universe@main

tools:
  # GHA-specific reproduction tool: accepts repos (owner/repo@ref) + goal or commands,
  # clones into an Incus container using GITHUB_TOKEN, runs commands, returns output.
  # This is the primary tool for "clone relevant repos and run DTU validation in context".
  - module: tool-launch-dtu
    source: ../amplifier_app_actions/tools/launch_dtu
---

# triage-repro Bundle

Extends `triage-safe` with Digital Twin Universe support for isolated issue reproduction.

Use when `enable_reproduction: true` in the GitHub Actions workflow.

Requires an Ubuntu full-VM runner with Incus installed (see `action.yml`).

## Additional Capability

- `launch_dtu` tool — clone repos (by `owner/repo@ref`) into an Incus container using
  `GITHUB_TOKEN`, then either run exact commands or delegate to `dtu-profile-builder`
  for NL-driven reproduction. This is the primary tool for examining code in context.
- `digital-twin-universe` agents (`dtu-profile-builder`, `validator`) for DTU orchestration
- `amplifier-tester` (already included via foundation) for behaviour validation

## Incus Requirements

The `enable_reproduction: true` action input installs Incus from the Zabbly stable
channel before this bundle is used.  Ubuntu 24.04's bundled Incus has an AppArmor
bug blocking dockerd; the Zabbly channel fixes this.
