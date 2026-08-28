# Agent Orchestration Policy

The main thread is the primary orchestrator. It owns requirements, repository inspection, task decomposition, worker selection, result review, integration, final verification, and acceptance.

- Small local changes stay in the primary thread. Delegate only meaningful independent workstreams when safe parallelism, context isolation, specialized evidence, or independently reviewable ownership justifies the coordination cost.
- Start repository work by reading applicable instructions and inspecting real ownership boundaries. The first non-trivial investigation produces a compact Repository Digest in context; do not create a digest file.
- Use real repository roles only. `backend_worker` is only for a real existing server/API/persistence/backend-service boundary. Use `frontend_worker` for existing client UI, `generic_worker` for other bounded implementation domains, `test_worker` for tests, `explorer_worker` for read-only codebase investigation, `docs_worker` for read-only documentation/API research, and `review_worker` for elevated-risk read-only review.
- Default model/effort policy: orchestrator = Sol/`medium`; frontend/backend/generic = Terra/`medium`; test/review = Luna/`high`; explorer/docs = Luna/`medium`. Only the primary orchestrator may authorize a retry or re-dispatch at a higher reasoning effort. Workers never self-escalate.
- Every writer receives explicit non-overlapping Allowed Write Paths and Forbidden Write Paths. Readers receive an Investigation Scope and evidence requirements. Workers stop and report when scope, ownership, architecture, or shared-contract assumptions change.
- Parallelize read-heavy work and disjoint writes. Serialize overlapping writes, shared contracts, migrations, lockfiles, generated artifacts, and conflict resolution.
- Nested delegation is prohibited by default. Only the primary orchestrator may explicitly authorize a specific nested task; that authorization never relaxes scope, sandbox, or self-escalation rules.
- `review_worker` is risk-based, not automatic. The primary thread reviews small, isolated, low-risk changes; use dedicated review for security-sensitive, cross-module, migration, concurrency, shared-contract, high-blast-radius, or similarly risky work.
- Worker completion is evidence, not acceptance. The orchestrator reviews results and runs fresh integrated verification before reporting completion.
- Final reports stay compact: outcome, workers used when any, changed areas, verification commands/results, and unresolved risks or blockers.
