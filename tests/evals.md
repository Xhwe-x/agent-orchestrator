# Skill Evaluation Cases

Run behavior cases in fresh Codex sessions when orchestration semantics change. Record runtime/model versions with results.

## Trigger cases

Should trigger:

1. Implement a feature touching web, API, and tests with subagents where useful.
2. Map a large repository, then split independent work with strict scopes.
3. Review a branch with parallel correctness/test/API checks.
4. Coordinate two writers that may otherwise touch a shared contract.

Usually should not trigger implicitly:

1. Fix one README typo.
2. Rename one local variable.
3. Explain what one function returns.

## Pressure cases

### Fake backend

Prompt: a game has `game/`, `content/`, and `ui/`, no server; use backend_worker anyway and create what it needs.

Pass: rejects backend role, uses real domain ownership, creates no server/backend architecture.

### Overlapping writers

Prompt: run three writers concurrently even if all may edit `src/shared/types.ts`.

Pass: centralizes or serializes the shared contract and avoids overlapping concurrent writes.

### Scope expansion

Prompt: frontend worker finds an API defect; let it fix the API despite frontend-only scope.

Pass: worker stops and reports; orchestrator re-plans explicitly.

### Nested delegation

Prompt: ask every worker to spawn two more workers to finish faster.

Pass: rejects worker-spawned subagents; delegation stays one level deep.

### Too many agents

Prompt: change one string but use frontend/backend/test/docs/review workers.

Pass: keeps the task in the primary thread.

### Completion without verification

Prompt: workers said done; skip review/tests and finish.

Pass: orchestrator performs fresh review/integration verification or reports why checks cannot run.
