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

If coordination cost is likely to exceed the saved time or context, keep the work in the orchestrator thread.

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

Repository evidence wins. A game with `game/`, `content/`, and `ui/` but no server does not need a backend role; use a bounded `generic_worker` or a project-defined domain worker.

## 5. Reconnaissance gate

Before write delegation, establish:

1. real owning files/modules;
2. applicable instructions;
3. cross-boundary interfaces;
4. shared/high-conflict files;
5. relevant verification commands.

If ownership is unclear, explore read-only first.

## 6. Work graph

For non-trivial work, identify nodes with `goal`, `role`, `reads`, `writes`, `depends_on`, and `verification`.

A node starts only when dependencies are complete and its write region does not conflict with another active writer.

## 7. Parallelism

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

When uncertain, use fewer writers.

## 8. Shared contracts

Use one of three patterns:

1. consume an existing contract unchanged;
2. let the orchestrator stabilize the shared contract first;
3. complete producer work before starting the consumer.

Never let independent writers invent both sides of the same new contract concurrently.

## 9. Review and failure handling

Before integration, review scope compliance, requested behavior, conventions, interfaces, verification evidence, assumptions, and conflicts.

A blocked worker reports evidence. The orchestrator decides whether to expand scope explicitly, reassign, resequence, or return the blocker. Workers never expand scope themselves.

## 10. Final verification

Run the smallest complete project-provided check set that proves the integrated result. Report what passed, what was not run, known failures, and remaining assumptions.
