# Issue Reproduction with launch_dtu

## When to Use

Use `launch_dtu` to reproduce a reported issue in an isolated, disposable
container when **all three** of the following conditions are met:

1. **Reproducible failure** — the issue includes enough detail to expect a
   consistent failure (error message, stack trace, unexpected output, or
   explicit steps that trigger it).
2. **Identifiable repos and versions** — the issue references one or more
   repositories with enough version information (tag, branch, commit SHA, or
   "latest main") to check out the code at the reported state.
3. **Repro steps as shell commands** — the steps can be expressed as a sequence
   of shell commands (install, configure, run, assert) that can be executed
   non-interactively inside a container.

Do **not** use `launch_dtu` for vague reports ("it doesn't work"), pure
documentation issues, or configuration questions where no code execution is
needed.

## How to Specify Repos

Pass a `repos` list to `launch_dtu`. Each entry is an object with a `url` and
an optional `ref`:

| Format | Example | Notes |
|--------|---------|-------|
| Tagged release | `{ "url": "https://github.com/org/repo", "ref": "v1.2.3" }` | Checks out the exact tag |
| Branch | `{ "url": "https://github.com/org/repo", "ref": "feature/my-branch" }` | Branch names may contain `/` |
| Commit SHA | `{ "url": "https://github.com/org/repo", "ref": "a1b2c3d" }` | Full or abbreviated SHA |
| No ref (default branch) | `{ "url": "https://github.com/org/repo" }` | Checks out the default branch (usually `main`) |

All repos are cloned into `/workspace/{repo-name}` inside the container, where
`repo-name` is the last path component of the URL (without `.git`).

## How to Write Commands

The `commands` field is a list of shell strings executed sequentially inside an
**Ubuntu 24.04** container. Write them as you would in a Bash script:

- Use absolute paths or `cd /workspace/{repo-name}` before relative operations.
- Commands are executed with `/bin/bash -c` and run as root.
- Each command runs in a fresh shell; use `&&` within a single string to chain
  dependent steps, or rely on the sequential list for ordering.
- Commands should be **non-interactive** — avoid prompts or TTY-only tools.

Example sequence:

```
"cd /workspace/my-service && pip install -e .",
"cd /workspace/my-service && python -m pytest tests/test_regression.py -v"
```

## Token Passthrough

Secrets are injected automatically — **do not hard-code credentials**:

| Variable | Source | Notes |
|----------|--------|-------|
| `GITHUB_TOKEN` | Calling environment | Injected automatically; used for private repo access and API calls |
| `ANTHROPIC_API_KEY` | Calling environment | Injected automatically; available for any commands that call the Anthropic API |

Both variables are available as standard environment variables inside every
command that runs in the container.

## Availability in All Modes

`launch_dtu` is available regardless of which triage mode is active
(`triage`, `reproduce`, `investigate`, etc.). You do not need to switch modes
to call it.

## Example JSON Call

```json
{
  "tool": "launch_dtu",
  "arguments": {
    "repos": [
      {
        "url": "https://github.com/microsoft/my-service",
        "ref": "v2.3.1"
      },
      {
        "url": "https://github.com/microsoft/my-client"
      }
    ],
    "commands": [
      "cd /workspace/my-service && pip install -e .",
      "cd /workspace/my-client && pip install -e .",
      "cd /workspace/my-client && python -m pytest tests/test_integration.py -v 2>&1"
    ]
  }
}
```

The tool returns the combined stdout/stderr of all commands along with exit
codes, allowing the agent to confirm whether the reported failure reproduces and
to report findings back to the issue thread.
