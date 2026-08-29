# Agent Contracts

Delegated work must be understandable without hidden parent-thread context. Workers never spawn or delegate to other workers.

## Core contract

Every worker receives:

```text
Contract ID: <unique task id>
Role: <worker>
Goal: <one coherent outcome>
Repository Digest: <compact relevant facts only>
Context: <task-specific facts and prior decisions>
Dependencies: <completed prerequisite or none>
Baseline: <relevant repository/worktree state>
Deliverables: <specific output>
Verification: <narrow checks when practical>
Stop Conditions: <scope/architecture/destructive/external blockers>
Allowed Write Paths: <explicit repo-relative paths or read-only>
Forbidden Write Paths: <protected paths>
Protected Existing Changes: <pre-existing modified/untracked paths relevant to this task>
```

The Repository Digest should normally stay around 10–20 lines and contain only ownership, entry points, shared contracts, verification commands, and constraints required by this worker.

## Worker return

Every worker returns a compact evidence report. Writers include `CHANGED_PATHS`; readers may use `EVIDENCE` instead.

```text
RESULT
<what was completed or found>

FILES
<files changed or inspected>

CHANGED_PATHS
<writer-only: paths actually changed by this task>

VERIFICATION
<commands/evidence and observed results>

RISKS
<remaining risks, blockers, or none>

ESCALATION
<only when the orchestrator must decide what happens next>
```

Do not return chain-of-thought-style narratives. Evidence and actionable status are sufficient.

## Reasoning and scope

Workers never change their own model or reasoning effort. A hard problem that remains fully in scope may return `ESCALATION`; only the primary orchestrator may retry or re-dispatch at the next `medium → high → xhigh → max` level.

If difficulty reveals missing ownership, architecture change, new dependency, extra write path, or an invalid assumption, stop before out-of-scope edits and report the evidence.

## Writer rules

- Modify only Allowed Write Paths.
- Preserve Protected Existing Changes.
- Confirm expected paths exist before editing.
- Do not create architecture merely to satisfy a role name.
- Do not modify another worker's ownership region.
- Stop if a required change crosses scope or a shared contract requires parent ownership.
- Do not spawn subagents or delegate further.
- Return `CHANGED_PATHS` so the orchestrator can compare actual changes with the baseline.

## Reader rules

Readers stay logically read-only, distinguish confirmed facts from hypotheses, return only evidence needed by the orchestrator, and do not drift into implementation or delegate further. The primary orchestrator verifies a post-reader no-mutation audit; sandbox defaults are defense in depth, not the sole proof of read-only behavior.

## Stop conditions

Stop and report when an expected component does not exist, repository evidence contradicts the assignment, a required write is outside scope, another active writer owns the file, or an unapproved destructive/external action would be required.

A stop is an orchestration boundary, not a failure.
