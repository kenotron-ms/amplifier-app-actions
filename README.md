# amplifier-app-actions

AI-powered issue triage and PR review for your GitHub repos.

## Quick start

1. Add `ANTHROPIC_API_KEY` as a repository secret (Settings → Secrets and variables → Actions).
2. Create one of the workflow files below in `.github/workflows/`.

### Issue triage

```yaml
# .github/workflows/issue-triage.yml
name: Issue Triage

on:
  issues:
    types: [opened]

permissions:
  issues: write
  contents: read

jobs:
  triage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: kenotron-ms/amplifier-app-actions@v1
        with:
          mode: prompt
          prompt: |
            You are triaging a new GitHub issue.

            Review the issue title and body. Then:
            1. Classify the issue type and add the appropriate label: bug, feature-request, question, or documentation
            2. Post a comment that acknowledges the issue, confirms its type, and briefly describes what happens next

            Be concise. Do not speculate about causes or promise timelines.
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

### PR review

```yaml
# .github/workflows/pr-review.yml
name: PR Review

on:
  pull_request:
    types: [opened]

permissions:
  pull-requests: write
  contents: read

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: kenotron-ms/amplifier-app-actions@v1
        with:
          mode: prompt
          prompt: |
            You are reviewing a new pull request.

            Review the changed files and the PR description. Post a comment that:
            1. Summarizes what this PR changes and why, in 2-3 sentences
            2. Lists any bugs, logic errors, or security concerns — be specific, cite file and line where possible
            3. Notes any improvements that would strengthen the PR

            Be direct. Focus detail on concerns. Do not block on style preferences.
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

## What it does

The action reads the GitHub event (issue or PR), runs an Amplifier agent session against it, and posts findings back as a comment and/or label. It can run a one-shot prompt or a multi-step recipe. The agent has a bounded capability surface: it can read repo files, post a comment, and add a label. Nothing else.

## Configuration

| Input | Description | Default |
|-------|-------------|---------| 
| `mode` | Execution mode: `prompt` or `recipe` | `prompt` |
| `prompt` | Prompt text for the agent (prompt mode) | — |
| `recipe_path` | Path to a recipe YAML file, relative to workspace root (recipe mode) | — |
| `provider` | LLM provider: `anthropic`, `openai`, `azure`, `ollama` | `anthropic` |
| `model` | Model name — falls back to provider default if omitted | — |
| `github_token` | GitHub token for posting results | `${{ github.token }}` |

Provider API keys are passed as environment variables, not action inputs. Set the appropriate secret for your provider:

| Provider | Environment variable |
|----------|---------------------|
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` |
| Ollama | (no key needed) |

## Recipe mode (advanced)

If `mode: recipe`, the action runs a multi-step Amplifier recipe instead of a single prompt. The `recipe_path` input points to a YAML recipe file checked into your repo. Requires `actions/checkout` to be present. Staged (approval-gated) recipes are not supported in CI and will fail with a clear error.

## Requirements

- A private GitHub repository
- An API key for your chosen LLM provider
- `actions/checkout@v4` in your workflow (required for PR review; recommended for issue triage)

## Security

This action is designed for private repositories. The agent's capability surface is intentionally bounded: it reads files, posts comments, and adds labels — nothing else. The workflow must not use `pull_request_target`; use `pull_request` only. See the [design document](docs/plans/2026-05-12-amplifier-app-actions-design.md) for the full security rationale.
