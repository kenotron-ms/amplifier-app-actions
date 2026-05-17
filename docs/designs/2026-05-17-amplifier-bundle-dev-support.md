# amplifier-bundle-dev-support Design

**Date:** 2026-05-17

## Purpose

New bundle repo (`microsoft/amplifier-bundle-dev-support`) providing focused GitHub Actions
bundles for Amplifier project workflows. Any contributor can drop one of these bundles into
their workflow via the `bundle:` input on `microsoft/amplifier-app-actions`.

## Structure

```
amplifier-bundle-dev-support/
  bundle.md                     ← root; default = investigate
  bundles/
    issue-triage.bundle.md      ← classify + label + acknowledge new issues
    investigate.bundle.md       ← deep code investigation, post findings
    pr-review.bundle.md         ← structured diff review, post comment
  behaviors/
    issue-triage.yaml
    investigate.yaml
    pr-review.yaml
  context/
    issue-triage.md
    investigate.md
    pr-review.md
  README.md
```

## Bundle architecture

Each `bundles/*.bundle.md` uses `name: dev-support` (registers `dev-support:` namespace),
then composes two things:

1. `github-tools` from `amplifier-app-actions` — foundation + recipes + provider + GitHub API tools
2. A behavior YAML from the same repo — injects the context file for that workflow type

The context file is the agent's instruction surface; the prompt in the workflow YAML
provides the event-specific trigger.

## Changes to amplifier-app-actions

| File | Change |
|------|--------|
| `docs/examples/issue-triage-workflow.yml` | Add `bundle:` input → `bundles/issue-triage.bundle.md` |
| `docs/examples/pr-review-workflow.yml` | Add `bundle:` input → `bundles/pr-review.bundle.md` |
| `docs/examples/investigate-workflow.yml` | New; `issue_comment: /investigate` trigger |
