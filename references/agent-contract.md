# Agent Contracts

Delegated work must be understandable without hidden parent-thread context.

## Core contract

Every worker receives:

```text
Role: <worker>
Goal: <one coherent outcome>
Context: <required facts and prior decisions, including the Repository Digest>
Dependencies: <completed prerequisite or none>
Deliverables: <specific output>
Verification: <narrow checks when practical>
Stop Conditions: <conditions requiring escalation>
Allowed Write Paths: <explicit paths, or "read-only">
Forbidden Write Paths: <adjacent or protected paths>
```

Every worker returns this compact format. `ESCALATION` is included only when the orchestrator needs to make an escalation or scope decision:

```text
RESULT
<what was completed>

FILES
<files changed or inspected>

VERIFICATION
<commands executed and results>

RISKS
<remaining risks, blockers, or "none">

ESCALATION
<why the orchestrator must decide what happens next>
```

Do not return chain-of-thought-style narratives. Evidence and actionable status are sufficient.

## Reasoning and escalation

Workers never change their own model or reasoning effort. If a worker encounters a hard problem that remains fully inside its assigned scope, it may finish or return `ESCALATION` so the primary orchestrator can retry or re-dispatch it at the next ladder level. Only the orchestrator controls `medium → high → xhigh → max`.

If difficulty reveals missing ownership, an architecture change, a new cross-domain dependency, an additional write path, or an invalid assumption, the worker must stop before making out-of-scope edits and report the evidence and required decision.

## Generic-worker boundary

`generic_worker` handles existing non-frontend/non-backend implementation domains such as game logic, data transformation, build tooling, compiler/parser logic, automation scripts, or domain-specific modules. Hard work within that boundary may be retried at `high` by the orchestrator. A scope or architecture change is a stop-and-report condition, not a reason for the worker to self-escalate or widen its writes.

## Writer extension

Every write-capable worker also receives explicit `Allowed Write Paths` and `Forbidden Write Paths`.

Rules:

- modify only Allowed Write Paths;
- confirm expected paths exist before editing;
- do not create architecture to satisfy a role name;
- do not modify another worker's ownership region;
- stop if a required change crosses scope or a shared contract requires parent ownership;
- nested delegation is prohibited by default; only the primary orchestrator may explicitly authorize a specific nested task, and that authorization does not relax any scope, sandbox, or self-escalation rule.

## Reader extension

Every read-only worker receives:

```text
Investigation Scope:
- <path/domain/source>

Evidence Required:
- <paths, symbols, commands, docs, or version-specific facts>
```

Rules:

- stay read-only;
- distinguish confirmed facts from hypotheses;
- return only evidence needed by the orchestrator;
- do not drift into implementation;
- nested delegation is prohibited by default; only the primary orchestrator may explicitly authorize a specific nested task, and that authorization does not relax any scope, sandbox, or self-escalation rule.

## Stop conditions

Stop and report when:

- an expected path/component does not exist;
- repository evidence contradicts the assignment;
- a required write is outside scope;
- another active writer owns the required file;
- an unapproved destructive/external action would be required.

A stop is an escalation boundary, not a failure.
