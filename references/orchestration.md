# Orchestration Rules

## 1. Ownership

The orchestrator owns user intent, project instructions, repository reconnaissance, task decomposition, dependency ordering, worker selection, shared contracts, review, integration, final verification, and final reporting.

Workers own only the contract explicitly delegated to them.

## 2. Task classes

| Class | Shape | Orchestration |
|---|---|---|
| A | small/local, one ownership area | primary thread only |
| B | mostly local but uncertainty or independent verification helps | primary + 1-2 helpers |
| C | 2+ independent workstreams with clear boundaries | bounded parallel workers |
| D | cross-cutting, shared schemas/interfaces/migrations/lockfiles | parallel readers; writers mostly serialized |

## 3. Delegation budget

Spawn one worker per meaningful independent workstream, not per file, layer, or checklist item.

Add a worker only when it does at least one of these:

- enables safe parallelism;
- isolates noisy investigation context;
- produces specialized evidence;
- owns an independently reviewable result.

If coordination cost is likely to exceed the saved time or context, keep the work in the orchestrator thread. A typo, one local function, or a small README wording change normally needs no worker.

## 4. Role selection

| Repository work | Role | Access |
|---|---|---|
| ownership/dependency tracing | `explorer_worker` | read-only |
| existing UI/components/client state | `frontend_worker` | scoped write |
| existing real server/API/persistence/backend service | `backend_worker` | scoped write |
| existing non-frontend/non-backend implementation domain | `generic_worker` | scoped write |
| tests/fixtures/harnesses | `test_worker` | scoped write |
| framework/API/project docs research | `docs_worker` | read-only |
| correctness/regression audit | `review_worker` | read-only |

Repository evidence wins. A game with `game/`, `content/`, and `ui/` but no server does not need a backend role; use a bounded `generic_worker` or a project-defined domain worker. `generic_worker` may be retried at `high` for a hard problem that remains fully in scope. If the problem reveals an ownership, architecture, dependency, or write-scope change, it stops and reports for the orchestrator instead.

## 5. Reconnaissance gate

Before write delegation, establish:

1. real owning files/modules;
2. applicable instructions;
3. cross-boundary interfaces;
4. shared/high-conflict files;
5. relevant verification commands.

If ownership is unclear, explore read-only first.

## 6. Repository Digest

The first repository investigation should produce a compact shared digest in the orchestrator context, rather than a new repository file. Include only execution-relevant facts:

```text
Repository Digest

Project: <stack or confirmed project type>
Main ownership: <real frontend/backend/generic/test/docs paths>
Entry points: <relevant application and service entries>
Shared contracts: <types, schemas, APIs, or "none identified">
Verification: <project-provided commands>
Important constraints: <scope, generated-file, or serialization rules>
```

Pass the digest together with each worker's task contract and exact relevant paths. Workers should not rescan the full repository unless their task explicitly requires additional investigation.

## 7. Work graph

For non-trivial work, identify nodes with `goal`, `role`, `reads`, `writes`, `depends_on`, and `verification`.

A node starts only when dependencies are complete and its write region does not conflict with another active writer.

## 8. Parallelism

Parallelize:

- independent exploration;
- docs/API verification;
- log/test-result analysis;
- disjoint implementation with stable interfaces.

Serialize:

- same-file or same-ownership writes;
- shared schemas/types/public contracts;
- migrations and lockfiles;
- generated artifacts plus generators;
- shared initialization and integration glue.

When uncertain, use fewer writers. Read-heavy work may run in parallel, but overlapping writes and shared-contract edits remain serialized or orchestrator-owned.

## 9. Shared contracts

Use one of three patterns:

1. consume an existing contract unchanged;
2. let the orchestrator stabilize the shared contract first;
3. complete producer work before starting the consumer.

Never let independent writers invent both sides of the same new contract concurrently.

## 10. Reasoning escalation

Role defaults and model identities are defined in [model policy](models.md). The primary orchestrator alone controls one ladder:

```text
medium → high → xhigh → max
```

Start at the role default, move one level at a time, and do not jump directly to `max` without a documented reason. Workers never self-escalate reasoning effort. When a worker encounters unexpected complexity, it returns an `ESCALATION` signal; the orchestrator decides whether to retry at the next level, split the task, add read-only investigation, revise scope explicitly, or stop for human clarification. `max` is reserved for rare, tightly coupled or unusually costly failures after `high` and `xhigh` have proved insufficient.

## 11. Review policy and failure handling

The primary orchestrator reviews small, isolated, low-risk changes directly. Launch a `review_worker` only for elevated-risk changes such as authentication/authorization, security-sensitive logic, migrations, cross-module integration, shared API contracts, concurrency, core domain logic, high blast radius, or large refactors.

Before dispatching a review worker, record why primary-thread review is insufficient and select the effort: `high` by default, or `xhigh` for especially difficult security, migration, race-condition, or high-blast-radius review. The orchestrator remains responsible for resolving findings and accepting the integrated result; a worker completion is evidence, not acceptance.

A blocked worker reports evidence. The orchestrator decides whether to expand scope explicitly, reassign, resequence, or return the blocker. Workers never expand scope themselves.

## 12. Nested delegation

Nested delegation is prohibited by default. Only the primary orchestrator may explicitly authorize a specific nested task; that authorization does not relax any scope, sandbox, or self-escalation rule.

By default, keep the delegation graph one level deep:

```text
Primary Orchestrator
        │
 ┌──────┼──────┐
 ↓      ↓      ↓
Worker Worker Explorer
        │
        ↓
Primary Integration
```

An explicitly authorized nested task remains exceptional and must stay within its delegated scope.

## 13. Final verification

Run the smallest complete project-provided check set that proves the integrated result. Report what passed, what was not run, known failures, and remaining assumptions. The primary orchestrator owns final integration, conflict resolution, verification, and acceptance.
