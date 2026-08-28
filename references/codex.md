# Codex Adaptation

Reviewed on 2026-08-28.

## Layout

User-level skill:

```text
$HOME/.agents/skills/agent-orchestrator/
```

Personal custom agents:

```text
$HOME/.codex/agents/
```

Project-scoped agents:

```text
<repo>/.codex/agents/
```

## Runtime package

The installer copies only runtime skill files (`SKILL.md`, `agents/`, `references/`) into the skill directory. GitHub-only material such as examples, tests, CI, and installer source is not copied into the runtime skill.

Agent TOMLs are copied separately to `$HOME/.codex/agents/`.

## Main orchestrator effort

`templates/codex-agents/orchestrator.toml` pins `gpt-5.6-sol` and uses `medium` as the default reasoning effort. The primary orchestrator alone may select the next level on the `medium → high → xhigh → max` ladder in `references/orchestration.md`; `max` is exceptional.

The reusable profile keeps this default explicit; higher effort is an orchestration-time decision, not a worker choice.

## Worker models

The reusable worker TOMLs pin the requested model split and role-based defaults:

- Terra + `medium`: frontend, backend, and generic implementation workers;
- Luna + `high`: test and review workers;
- Luna + `medium`: explorer and docs workers.

Workers never self-escalate. The orchestrator may retry or re-dispatch a worker at a higher level after reviewing its structured escalation signal.

## AGENTS.md layering

Keep global behavior concise in `~/.codex/AGENTS.md`. Put project paths, ownership rules, verification commands, and domain constraints in project-level `AGENTS.md` files.

## Invocation

```text
$agent-orchestrator
Analyze the repository, classify the task, delegate only independent workstreams, enforce explicit write scopes, review all results, then integrate and verify.
```

## Official references

- https://developers.openai.com/api/docs/guides/latest-model
- https://developers.openai.com/api/docs/models/gpt-5.6-sol
- https://developers.openai.com/api/docs/models/gpt-5.6-terra
- https://developers.openai.com/api/docs/models/gpt-5.6-luna
