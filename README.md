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
| `prompt` | Inline prompt text | — |
| `prompt_source` | Path or URL to a prompt file | — |
| `recipe_source` | Path or URL to an Amplifier recipe YAML | — |
| `attractor_source` | Path or URL to an attractor `.dot` file | — |
| `provider` | LLM provider: `anthropic`, `openai`, `azure`, `ollama` | `anthropic` |
| `model` | Model name override — falls back to provider default if omitted | — |
| `github_token` | GitHub token for API calls | `${{ github.token }}` |

Exactly one of `prompt`, `prompt_source`, `recipe_source`, or `attractor_source` must be set.

Provider API keys are passed as environment variables, not action inputs. Set the appropriate secret for your provider:

| Provider | Environment variable |
|----------|---------------------|
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` |
| Ollama | (no key needed) |

## Recipes and attractors (advanced)

For runs more involved than a single prompt, point the action at a recipe or attractor file. Each accepts a local workspace path or an HTTPS URL.

- **`recipe_source`** — a multi-step Amplifier recipe YAML. The action loads the recipe and runs it against the event context. Requires `actions/checkout` to be present when the source is a local path. Staged (approval-gated) recipes are not supported in CI and will fail with a clear error.
- **`attractor_source`** — a Graphviz `.dot` attractor file describing the shape of the desired outcome. The action loads it as additional context for the agent, useful for steering recipes or prompts toward a known-good structure.

## Local testing

You can run this action against a local Gitea sandbox or a Digital Twin Universe (DTU) instance instead of github.com. Override the API and clone endpoints via environment variables:

```yaml
env:
  GITHUB_API_URL: http://localhost:3000/api/v1   # point at Gitea
  GITHUB_CLONE_URL: http://localhost:3000         # redirect clones
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

This is useful for iterating on prompts, recipes, or the action itself without round-tripping through github.com — for example, when running inside a DTU profile or against an ephemeral Gitea container.

| Env var | Purpose |
|---------|---------|
| `GITHUB_API_URL` | Redirect GitHub REST API calls (e.g. to a local Gitea instance) |
| `GITHUB_CLONE_URL` | Redirect `git clone` calls (e.g. to a local Gitea instance) |

## Requirements

- A private GitHub repository
- An API key for your chosen LLM provider
- `actions/checkout@v4` in your workflow (required for PR review; recommended for issue triage)

## Security

This action is designed for private repositories. The agent's capability surface is intentionally bounded: it reads files, posts comments, and adds labels — nothing else. The workflow must not use `pull_request_target`; use `pull_request` only.
