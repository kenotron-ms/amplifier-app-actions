# Issue Reproduction with launch_dtu

## Two Modes

`launch_dtu` has two modes. Choose based on what you know about the issue:

### Goal mode (natural language)

Use when you understand what needs to be verified but don't know the exact
commands to run. Describe the goal in plain language — `launch_dtu` delegates
to `dtu-profile-builder`, which figures out the environment and steps.

```json
{
  "repos": ["microsoft/amplifier-core@v1.5.2", "microsoft/amplifier-bundle-routing-matrix"],
  "goal": "Verify whether child sessions created via session.spawn contain the full routing matrix fallback chain or only the first resolved model. Install both repos and write a minimal script that calls session.spawn and inspects the child config."
}
```

Use goal mode when:
- The issue is a logic or configuration bug where you need to probe behavior
- The exact repro script would require judgment (what to install, what to assert)
- The issue references a concept ("fallback chain not propagated") rather than a command

### Commands mode (concrete shell commands)

Use when the issue contains explicit steps that translate directly to shell
commands. Provide the exact commands to run.

```json
{
  "repos": ["microsoft/amplifier-core@v1.5.2"],
  "commands": [
    "cd /workspace/amplifier-core && pip install -e .",
    "python -c \"from amplifier_core import AmplifierSession; s = AmplifierSession({}); print(s)\" 2>&1"
  ]
}
```

Use commands mode when:
- The issue has explicit `pip install` + `python -c` or `pytest` commands
- The reporter included a minimal reproduction script
- You can construct the exact failing invocation from the issue body

## When to Use launch_dtu At All

Use it when **all three** conditions are true:

1. **Reproducible failure** — the issue includes enough detail to expect a
   consistent failure (error message, stack trace, unexpected output).
2. **Identifiable repos and versions** — the issue references repositories
   with enough version info (tag, branch, SHA, or "latest main").
3. **Can be verified in a container** — the failure can be triggered by
   installing packages and running code, without requiring live LLM calls,
   interactive prompts, or external service state.

Do **not** use `launch_dtu` for:
- Vague reports ("it doesn't work") with no repro steps
- Issues that require simulating model unavailability or provider behavior
- Documentation or configuration questions
- Issues where you already found the root cause via code analysis

## Repo Format

Repos are specified as strings in `"owner/repo"` or `"owner/repo@ref"` format:

| Format | Example | When |
|--------|---------|------|
| Tag | `"microsoft/amplifier-core@v1.5.2"` | Issue specifies a version |
| Branch | `"microsoft/amplifier-core@feat/my-branch"` | Issue references in-progress work |
| SHA | `"microsoft/amplifier-core@a1b2c3d"` | Issue pinpoints an exact commit |
| Default branch | `"microsoft/amplifier-core"` | Latest main |

Repos are cloned into `/workspace/{repo}` inside the container.

## Secrets — Automatic, Never Hard-Code

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | Private repo access and GitHub API calls |
| `ANTHROPIC_API_KEY` | Available if commands call the Anthropic API |

Both are passed through automatically. Do not include them in commands.

## Availability

`launch_dtu` is available in **all modes** — prompt, recipe, and attractor.
You do not need a special mode to call it.
