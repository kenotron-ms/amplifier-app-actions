# Recipe Template Variables

When using `recipe_source` with `amplifier-app-actions`, your recipe YAML
steps receive two categories of template variables:

1. **Context variables** — injected from the GitHub event before the recipe
   runs. Always available in every step.
2. **Step output variables** — produced by earlier steps and available in all
   subsequent steps.

---

## Context variables

These are injected automatically from the GitHub event that triggered the
workflow. Reference them in any step prompt as `{{ context.field }}`.

### Available for all events

| Variable | Type | Description |
|---|---|---|
| `{{ context.number }}` | `int` | Issue or PR number |
| `{{ context.owner }}` | `str` | Repository owner login (e.g. `microsoft`) |
| `{{ context.repo }}` | `str` | Repository name (e.g. `amplifier-core`) |
| `{{ context.title }}` | `str` | Issue or PR title |
| `{{ context.body }}` | `str` | Issue or PR body text (may be empty string) |
| `{{ context.author }}` | `str` | Login of the user who opened the issue or PR |
| `{{ context.labels }}` | `list[str]` | Label names currently on the issue or PR (e.g. `["bug", "high-priority"]`) |
| `{{ context.event_type }}` | `str` | `"issues"` or `"pull_request"` |

### Available for pull request events only

| Variable | Type | Description |
|---|---|---|
| `{{ context.base_ref }}` | `str` | Base branch name (e.g. `main`) |
| `{{ context.head_ref }}` | `str` | Head branch name (e.g. `feature/my-change`) |

### Example

```yaml
steps:
  - id: classify
    agent: foundation:zen-architect
    prompt: |
      Classify issue #{{ context.number }} in {{ context.owner }}/{{ context.repo }}.

      Title: {{ context.title }}
      Body:
      {{ context.body }}
      Author: {{ context.author }}
      Labels: {{ context.labels }}

      Respond with JSON: {"type": "bug|feature-request|question|documentation"}
    parse_json: true
```

---

## Step output variables

When a step has `parse_json: true`, its JSON output fields become available
to all subsequent steps as `{{ step_id.field }}`. The step's `id` is the
top-level key.

### How it works

```yaml
steps:
  - id: understand          # ← step id becomes the variable namespace
    agent: foundation:zen-architect
    prompt: |
      ...
      Respond with JSON: {"problem_statement": "...", "affected_repos": [...]}
    parse_json: true         # ← parse output as JSON and store in context

  - id: investigate
    agent: foundation:bug-hunter
    prompt: |
      Problem: {{ understand.problem_statement }}    # ← step id . field
      Repos:   {{ understand.affected_repos }}
```

The JSON fields from the `understand` step are flattened into the context
under the `understand` key. Any field in the JSON response is addressable.

---

## Full investigate-recipe variable reference

The following variables are used in the standard five-stage investigation
recipe (`understand → clone → investigate → reproduce → report`). Use this
as a reference when building compatible recipes.

### `understand` step outputs

| Variable | Type | Description |
|---|---|---|
| `{{ understand.problem_statement }}` | `str` | One-sentence observable problem |
| `{{ understand.affected_repos }}` | `list[str]` | Repos in `"owner/repo@ref"` format |
| `{{ understand.affected_components }}` | `list[str]` | Specific classes, functions, or modules named |
| `{{ understand.error_messages }}` | `list[str]` | Verbatim stack traces or error messages |
| `{{ understand.repro_steps_summary }}` | `str` | Literal commands or conceptual scenario |
| `{{ understand.has_concrete_repro }}` | `bool` | `true` if the issue contains runnable commands or scripts |
| `{{ understand.requires_live_llm }}` | `bool` | `true` if reproduction requires actual LLM API calls |
| `{{ understand.expected_behavior }}` | `str` | What the author expected |
| `{{ understand.actual_behavior }}` | `str` | What actually happened |

### `clone` step outputs

| Variable | Type | Description |
|---|---|---|
| `{{ clone.cloned }}` | `list[{repo, ref, path}]` | Repos cloned with their local paths |

### `investigate` step outputs

| Variable | Type | Description |
|---|---|---|
| `{{ investigate.hypothesis }}` | `str` | Specific code path that causes the observed behavior |
| `{{ investigate.evidence }}` | `list[{file, line, detail}]` | Supporting evidence with file:line citations |
| `{{ investigate.confidence }}` | `str` | `"high"`, `"medium"`, or `"low"` |
| `{{ investigate.testable_claim }}` | `str` | Falsifiable claim a reproduction could verify |

### `reproduce` step outputs

| Variable | Type | Description |
|---|---|---|
| `{{ reproduce.attempted }}` | `bool` | Whether `launch_dtu` was called |
| `{{ reproduce.reproduced }}` | `bool\|null` | Whether the issue was reproduced (`null` if not attempted) |
| `{{ reproduce.dtu_goal }}` | `str\|null` | Goal passed to the DTU |
| `{{ reproduce.output }}` | `str\|null` | Full raw output from the DTU run |
| `{{ reproduce.conclusion }}` | `str\|null` | Interpretation of whether the testable claim was confirmed |
| `{{ reproduce.skipped_reason }}` | `str\|null` | Why `launch_dtu` was not called (when `attempted` is `false`) |
| `{{ reproduce.what_would_enable_repro }}` | `str\|null` | What the author would need to provide to enable reproduction |

---

## Conditional rendering

Recipe step prompts support Jinja2 conditionals, which are useful for steps
that depend on whether a previous step ran:

```yaml
- id: report
  agent: foundation:git-ops
  prompt: |
    {% if reproduce.attempted %}
    **Reproduced**: {{ reproduce.reproduced }}
    **Conclusion**: {{ reproduce.conclusion }}
    {% else %}
    Reproduction was not attempted.
    **Reason**: {{ reproduce.skipped_reason }}
    **To enable reproduction**: {{ reproduce.what_would_enable_repro }}
    {% endif %}
```

Loop over list fields:

```yaml
prompt: |
  **Evidence**
  {% for e in investigate.evidence %}
  - `{{ e.file }}:{{ e.line }}` — {{ e.detail }}
  {% endfor %}
```

---

## Variable resolution rules

The recipes engine resolves `{{ a.b }}` by:

1. Looking up the key `"a"` in the flat execution context.
2. Then looking up the key `"b"` inside that value.

For context variables this means the GitHub event fields are stored under a
top-level `"context"` key, so `{{ context.number }}` resolves correctly.
For step outputs, each step's `id` is the top-level key.

**Do not** use a flat top-level name that collides with a step id — the step
output will shadow it.
