# Agent Contracts

Delegated work must be understandable without hidden parent-thread context.

## Core contract

Every worker receives:

```text
Role: <worker>
Goal: <one coherent outcome>
Context: <required facts and prior decisions>
Dependencies: <completed prerequisite or none>
Deliverables: <specific output>
Verification: <narrow checks when practical>
Stop Conditions: <conditions requiring escalation>
Return Format: status, summary, evidence/files, verification, blockers/risks
```

## Writer extension

Every write-capable worker also receives:

```text
Allowed Write Paths:
- <explicit path/glob>

Forbidden Write Paths:
- <adjacent or protected path/glob>
```

Rules:

- modify only Allowed Write Paths;
- confirm expected paths exist before editing;
- do not create architecture to satisfy a role name;
- do not modify another worker's ownership region;
- stop if a required change crosses scope or a shared contract requires parent ownership;
- do not spawn additional subagents.

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
- do not spawn additional subagents.

## Stop conditions

Stop and report when:

- an expected path/component does not exist;
- repository evidence contradicts the assignment;
- a required write is outside scope;
- another active writer owns the required file;
- an unapproved destructive/external action would be required.

A stop is an escalation boundary, not a failure.
