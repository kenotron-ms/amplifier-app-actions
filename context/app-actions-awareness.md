# amplifier-app-actions Setup

You have access to `app-actions:app-actions-expert` — the authoritative expert for setting
up GitHub issue tracking and PR reviews using `amplifier-app-actions`.

## When to Delegate

**ALWAYS delegate to `app-actions:app-actions-expert` when the user:**

- Wants to add AI-powered issue triage to their GitHub repo
- Wants to set up automated PR reviews
- Asks how to configure `amplifier-app-actions` workflows
- Needs workflow YAML templates with sane default prompts
- Wants to know which bundle to use
- Asks about secrets, permissions, or the bot-comment guard
- Wants to understand `prompt` vs `attractor_source` vs `recipe_source`
- Wants the four-workflow pattern (triage, investigate, PR review, triage-continue)

## Do NOT DIY

Do not attempt to write workflow YAML or explain `amplifier-app-actions` inputs from memory.
The expert has the complete reference and ready-to-use templates.

```python
delegate(
    agent="app-actions:app-actions-expert",
    instruction="<what the user needs>",
    context_depth="recent",
    context_scope="conversation"
)
```

## What the Expert Provides

- Ready-to-use workflow YAML for all four workflow types
- Sane default inline prompts for issue triage and PR review
- Bundle selection guide (when to use `github-tools` vs `attractor-pipeline` vs external)
- Action input reference (`bundle`, `prompt`, `attractor_source`, `model`, `enable_reproduction`)
- Security patterns (bot-comment guard, slash-command auth gate, safe permissions)
- The complete four-workflow pattern setup checklist
