---
bundle:
  name: triage-repro
  version: 0.1.0

includes:
  # Compose the safe triage baseline.
  # Path is relative to the action root (wrapper.py sets cwd=action_path for the subprocess).
  - bundle: ./bundles/triage-safe.bundle.md
  # Add DTU infrastructure — dtu-profile-builder agent, amplifier-digital-twin CLI
  - bundle: git+https://github.com/microsoft/amplifier-bundle-digital-twin-universe@main
---

# triage-repro Bundle

Extends `triage-safe` with Digital Twin Universe support for isolated issue reproduction.

Use when `enable_reproduction: true` in the GitHub Actions workflow.

Requires an Ubuntu full-VM runner with Incus installed (see `action.yml`).

## Incus Requirements

The `enable_reproduction: true` action input installs Incus from the Zabbly stable
channel before this bundle is used.  Ubuntu 24.04's bundled Incus has an AppArmor
bug blocking dockerd; the Zabbly channel fixes this.
