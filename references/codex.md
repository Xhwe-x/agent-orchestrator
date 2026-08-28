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

`templates/codex-agents/orchestrator.toml` pins `gpt-5.6-sol` but does not pin reasoning effort. Select the project/session effort using the matrix in `references/models.md`.

A static TOML cannot simultaneously encode four different project-specific effort levels; the reusable profile therefore leaves effort to the active project/session configuration.

## Worker models

The reusable worker TOMLs deliberately pin the requested split:

- Terra + `max`: implementation workers;
- Luna + `max`: test/review/explorer/docs workers.

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
