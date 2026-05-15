---
bundle:
  name: triage-repro
  version: 0.1.0

includes:
  # Compose the safe triage baseline
  - bundle: ./triage-safe.bundle.md
  # Add DTU (Incus + amplifier-tester) for isolated issue reproduction
  # foundation already includes amplifier-tester; this adds launch_dtu and
  # DTU-aware agents for spinning up containerised reproduction environments.
  - bundle: git+https://github.com/microsoft/amplifier-bundle-digital-twin-universe@main
---

# triage-repro Bundle

Extends `triage-safe` with Digital Twin Universe support for isolated issue reproduction.

Use when `enable_reproduction: true` in the GitHub Actions workflow.

Requires an Ubuntu full-VM runner with Incus installed (see `action.yml`).

## Additional Capability

- `launch_dtu` tool (from digital-twin-universe) for Incus container management
- DTU-aware agents for reproductions inside isolated environments
- `amplifier-tester` (already included via foundation) for behaviour validation

## Incus Requirements

The `enable_reproduction: true` action input installs Incus from the Zabbly stable
channel before this bundle is used.  Ubuntu 24.04's bundled Incus has an AppArmor
bug blocking dockerd; the Zabbly channel fixes this.
