# Attractor DOT Pipeline Setup

You have access to `app-actions:dot-setup-expert` — the authoritative expert for designing
and customizing attractor DOT pipelines and bundle configurations for `amplifier-app-actions`.

## When to Delegate

**ALWAYS delegate to `app-actions:dot-setup-expert` when the user:**

- Wants to create or customize a `.dot` attractor pipeline file
- Asks about DOT syntax for attractor (`goal`, `default_fidelity`, `thread_id`, etc.)
- Wants to design a manager-supervisor investigation loop
- Wants to configure the quality gate (`goal_gate`, `reasoning_effort`, `shape=diamond`)
- Asks about thread isolation (`thread_id="quality-thread"`, `fidelity="compact"`)
- Wants to understand the commenter node pattern (`llm_provider="anthropic-commenter"`)
- Is getting `nodes_completed: 0` or `DirectProviderBackend` errors
- Wants to customize the `attractor-pipeline` bundle for their use case
- Wants to add a third node (research, context-gathering, summarization) to an existing pipeline

## Do NOT DIY

Do not attempt to write DOT files or explain attractor syntax from memory.
The expert has the complete reference, the canonical `triage-review.dot` patterns,
and ready-to-use templates.

```python
delegate(
    agent="app-actions:dot-setup-expert",
    instruction="<what the user needs>",
    context_depth="recent",
    context_scope="conversation"
)
```

## What the Expert Provides

- Complete DOT syntax reference for attractor pipelines
- The manager-supervisor pattern (with `shape=house`, `manager.max_cycles`, `manager.stop_condition`)
- Quality gate design (`goal_gate=true`, `reasoning_effort=high`, conditional edges)
- Thread isolation for adversarial independence (`thread_id`, `fidelity="compact"`)
- The commenter node pattern that routes to `pipeline-agent-commenter`
- Subgraph design for investigation cycles
- Common mistake fixes (`nodes_completed: 0`, `DirectProviderBackend`, pipeline never exits)
- Customization guidance for non-Amplifier repos and different quality gate criteria
