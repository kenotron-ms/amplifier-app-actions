---
bundle:
  name: triage-amplifier
  version: 0.1.0

includes:
  # Compose the repro tier (which includes safe + DTU)
  - bundle: ./triage-repro.bundle.md
  # TODO: add amplifier-dev bundle when URL is stabilised
  # - bundle: git+https://github.com/microsoft/amplifier-bundle-amplifier-dev@main
---

# triage-amplifier Bundle

Extends `triage-repro` with Amplifier-ecosystem tooling for triaging issues
in the Amplifier monorepo itself.

## Usage

Point your workflow to this bundle when:
- The issue is in an Amplifier core/foundation/module repo
- You need `foundation:amplifier-expert` or similar specialist agents
- Cross-repo amplifier module tracing is required

## Future Extension

The `amplifier-dev` bundle (to be added above) will include:
- Amplifier module registry access
- Bundle graph tooling
- Cross-module dependency analysis
