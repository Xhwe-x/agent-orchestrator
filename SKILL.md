---
name: agent-orchestrator
description: Use when software work has multiple independent workstreams, large-repository exploration, coordinated subagents, or write-scope conflicts; avoid for simple local edits.
---

# Agent Orchestrator

## Overview

Coordinate software work through one primary orchestrator and a small set of bounded workers.

**Core principle:** roles follow the repository and task. Never reshape a repository merely to justify a predefined agent role.

## Main Agent

The primary orchestrator owns requirements, repository inspection, decomposition, scheduling, review, integration, and final verification.

- Model: `gpt-5.6-sol`.
- Default reasoning effort: `medium`; only the orchestrator may move up the project/task ladder.
- Workers never replace the orchestrator's integration responsibility.

Use `references/models.md` for role defaults and effort guidance.

## Workflow

1. Read applicable `AGENTS.md` and inspect the real repository before assigning roles.
2. Classify the work and create only meaningful independent workstreams.
3. Use read-only exploration first when ownership, interfaces, or test commands are unclear.
4. Select workers from repository evidence, not from a fixed roster.
5. Dispatch explicit reader or writer contracts from `references/agent-contract.md`.
6. Parallelize read-heavy tasks and disjoint writes; serialize overlapping writes and shared contracts.
7. Review every worker result before accepting it.
8. Integrate centrally and run final verification in the orchestrator thread.

## Hard Rules

- Never invent a backend, service, directory, test layer, or documentation system because a worker name exists.
- `backend_worker` is only for an existing real server/API/persistence/backend service boundary.
- `generic_worker` may retry hard work that stays in scope; architecture or scope changes stop and report.
- Nested delegation is prohibited by default. Only the primary orchestrator may explicitly authorize a specific nested task; that authorization does not relax any scope, sandbox, or self-escalation rule.
- Never let a worker widen its own write scope.
- Never run concurrent writers on overlapping ownership regions.
- One worker per meaningful independent workstream, not per file or checklist item.
- Only the orchestrator controls `medium → high → xhigh → max`; workers return an escalation signal instead of self-escalating.
- The first investigation produces a compact Repository Digest for worker contracts; do not add a repository digest file.
- The primary handles trivial reviews; use `review_worker` only for elevated-risk changes with a documented rationale and effort.
- Shared interfaces, migrations, lockfiles, generated artifacts, and conflict resolution stay serialized or orchestrator-owned.
- Worker completion is evidence, not proof; final acceptance requires fresh integration verification.
- If subagents are unavailable, preserve the same boundaries and execute sequentially.

## Model Split

- Orchestrator: **Sol**, `medium` by default.
- Implementation workers: **Terra**, `medium` by default.
- Test/review workers: **Luna**, `high` by default; explorer/docs workers: **Luna**, `medium` by default.
- `max` is an exceptional escalation level, never a normal default.

## Final Report

Return: outcome, changed areas, verification commands/results, and unresolved risks or blockers.

## References

- `references/orchestration.md`
- `references/agent-contract.md`
- `references/models.md`
- `references/codex.md`
